#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2012-2014 Monty Program Ab
# Copyright (c) 2015-2025 MariaDB Corporation Ab

"""
Per-column-type cost of the pure-Python row parsers (text and binary protocol).

For each column type, a 10,000-row single-column SELECT is run once to capture
the raw row packets, then BaseClient._decode_row_packet (text / binary) is timed alone over those packets (no network, no
cursor overhead). This isolates the decoding cost of one field type so a
change to one parser branch can be measured and compared against a saved run.

    python parser_field_bench.py --save before.json
    ... edit mariadb/impl/client/base_client.py ...
    python parser_field_bench.py --save after.json --compare before.json

Connection settings come from the TEST_DB_* variables used by the other
benchmarks. The table it creates (parserFieldBench) is dropped on exit.
"""

import argparse
import functools
import json
import os
import sys
import time
from typing import Any, Callable, Dict, List, Tuple

os.environ['MARIADB_PYTHON_CONNECTOR'] = 'python'

import mariadb  # noqa: E402
from mariadb.impl.client import base_client  # noqa: E402

DB_CONFIG: Dict[str, Any] = {
    'host': os.environ.get('TEST_DB_HOST', '127.0.0.1'),
    'port': int(os.environ.get('TEST_DB_PORT', '3306')),
    'user': os.environ.get('TEST_DB_USER', 'root'),
    'password': os.environ.get('TEST_DB_PASSWORD', ''),
    'database': os.environ.get('TEST_DB_DATABASE', 'testp'),
    'ssl': False,
}
TABLE = 'parserFieldBench'
ROWS = 10000

# (label, column definition, value expression from the seq_1_to_N table)
COLUMNS: List[Tuple[str, str, str]] = [
    ('int', 'i INT', 'seq'),
    ('bigint', 'bi BIGINT', 'seq * 1000000007'),
    ('tinyint', 'ti TINYINT', 'seq % 100'),
    ('int_unsigned', 'iu INT UNSIGNED', 'seq'),
    ('float', 'f FLOAT', 'seq / 7'),
    ('double', 'd DOUBLE', 'seq / 7'),
    ('decimal', 'de DECIMAL(10,2)', 'seq * 1.23'),
    ('varchar', 'vc VARCHAR(50)', "CONCAT('user_', seq)"),
    ('text', 'tx TEXT', "CONCAT('Test data for row ', seq)"),
    ('varbinary', 'vb VARBINARY(32)', "CONCAT('bin_', seq)"),
    ('date', 'dt DATE', "'2024-01-01' + INTERVAL seq DAY"),
    ('datetime', 'dtm DATETIME', "'2024-01-01' + INTERVAL seq SECOND"),
    ('datetime6', 'dtm6 DATETIME(6)', "'2024-01-01 00:00:00.123456' + INTERVAL seq SECOND"),
    ('time', 'tm TIME', 'SEC_TO_TIME(seq)'),
    ('time6', 'tm6 TIME(6)', 'SEC_TO_TIME(seq + 0.123456)'),
    ('json', 'js JSON', "JSON_OBJECT('k', seq)"),
    ('null', 'nu INT', 'NULL'),
]

Captured = List[Tuple[memoryview, Any, Any, int]]


def capture(conn: Any, sql: str, binary: bool) -> Tuple[Captured, Callable[..., Any]]:
    """Run sql once and return the row payloads it produced plus the decoder to time.

    Buffered and streaming results normally decode rows in bulk straight from the
    receive buffer; to get one payload per row the bulk decoders are stubbed out
    for the capture so every row goes through _decode_row_packet().
    """
    client = conn._client  # pyright: ignore[reportPrivateUsage]
    captured: List[Tuple[bytes, Any, Any, int]] = []
    orig_decode = base_client.BaseClient._decode_row_packet  # pyright: ignore[reportPrivateUsage]
    orig_bulk = (base_client.BaseClient._parse_text_rows, base_client.BaseClient._parse_binary_rows)  # pyright: ignore[reportPrivateUsage]

    def spy(self: Any, data: memoryview, columns: Any, config: Any, num_cols: int, is_binary: bool) -> Any:
        captured.append((bytes(data), columns, config, num_cols))
        # decode with the real bulk functions (they are stubbed out below only
        # so that the client hands every row to this entry point)
        base_client.BaseClient._parse_text_rows, base_client.BaseClient._parse_binary_rows = orig_bulk  # type: ignore[method-assign, assignment]
        try:
            return orig_decode(self, data, columns, config, num_cols, is_binary)
        finally:
            base_client.BaseClient._parse_text_rows = no_bulk  # type: ignore[method-assign, assignment]
            base_client.BaseClient._parse_binary_rows = no_bulk  # type: ignore[method-assign, assignment]

    def no_bulk(self: Any, buf: Any, pos: int, end: int, *args: Any) -> Tuple[int, bool]:
        return pos, False   # "not a row here": the generic path decodes packet by packet

    base_client.BaseClient._decode_row_packet = spy  # type: ignore[method-assign]
    base_client.BaseClient._parse_text_rows = no_bulk  # type: ignore[method-assign, assignment]
    base_client.BaseClient._parse_binary_rows = no_bulk  # type: ignore[method-assign, assignment]
    try:
        cur = conn.cursor(binary=True) if binary else conn.cursor()
        cur.execute(sql + " WHERE id > ?", (0,))
        cur.fetchall()
        cur.close()
    finally:
        base_client.BaseClient._decode_row_packet = orig_decode  # type: ignore[method-assign]
        base_client.BaseClient._parse_text_rows, base_client.BaseClient._parse_binary_rows = orig_bulk  # type: ignore[method-assign, assignment]
    fn = functools.partial(client._decode_row_packet, is_binary=binary)  # pyright: ignore[reportPrivateUsage]
    return [(memoryview(d), c, cfg, n) for d, c, cfg, n in captured], fn


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--save', help='write results (ns per row) to this JSON file')
    parser.add_argument('--compare', help='JSON file of a previous --save to show the difference against')
    parser.add_argument('--rounds', type=int, default=15, help='timing rounds per type, the best one is kept')
    parser.add_argument('--only', help='comma-separated list of type labels to run')
    args = parser.parse_args()
    selected = set(args.only.split(',')) if args.only else None

    conn = mariadb.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute(f"DROP TABLE IF EXISTS {TABLE}")
    cur.execute(f"CREATE TABLE {TABLE} (id INT AUTO_INCREMENT PRIMARY KEY, "
                + ", ".join(ddl for _, ddl, _ in COLUMNS) + ")")
    cur.execute(f"INSERT INTO {TABLE} (" + ", ".join(ddl.split()[0] for _, ddl, _ in COLUMNS) + ") SELECT "
                + ", ".join(expr for _, _, expr in COLUMNS) + f" FROM seq_1_to_{ROWS}")
    conn.commit()

    results: Dict[str, float] = {}
    try:
        for label, ddl, _ in COLUMNS:
            if selected and label not in selected:
                continue
            column = ddl.split()[0]
            for proto in ('text', 'binary'):
                packets, fn = capture(conn, f"SELECT {column} FROM {TABLE}", proto == 'binary')
                best = float('inf')
                for _ in range(args.rounds):
                    start = time.perf_counter()
                    for packet in packets:
                        fn(*packet)
                    best = min(best, time.perf_counter() - start)
                results[f"{label}/{proto}"] = best * 1e9 / len(packets)
    finally:
        cur.execute(f"DROP TABLE IF EXISTS {TABLE}")
        cur.close()
        conn.close()

    if args.save:
        with open(args.save, 'w') as f:
            json.dump(results, f, indent=1)
    base: Dict[str, float] = {}
    if args.compare:
        with open(args.compare) as f:
            base = json.load(f)

    print(f"{'ns / row (1 col)':<16} {'text':>9} {'binary':>9}" + ("      vs compare (text / binary)" if base else ""))
    for label, _, _ in COLUMNS:
        if selected and label not in selected:
            continue
        t, b = results[f"{label}/text"], results[f"{label}/binary"]
        line = f"{label:<16} {t:9.0f} {b:9.0f}"
        if base:
            line += f"      {t / base[f'{label}/text'] * 100 - 100:+6.1f}% / {b / base[f'{label}/binary'] * 100 - 100:+6.1f}%"
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
