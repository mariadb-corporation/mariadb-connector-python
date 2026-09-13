#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2012-2014 Monty Program Ab
# Copyright (c) 2015-2025 MariaDB Corporation Ab

"""
Benchmark: batch INSERT of 10,000 mixed-type rows
executemany() of BATCH_ROWS 8-column rows into a BLACKHOLE table, so the
number reflects the driver's statement building / bulk protocol cost rather
than storage-engine work. Sync counterpart of async/test_bench_async_insert_batch_10k.py.
"""

from typing import Any, List, Tuple

import pytest

BATCH_ROWS = 10000


def generate_rows(count: int = BATCH_ROWS) -> List[Tuple[Any, ...]]:
    return [
        (
            i + 200000,
            f"batch_user_{i}",
            f"batch_{i}@example.com",
            "2024-02-01 00:00:00",
            "2024-02-01 00:00:00",
            round(i * 1.23, 2),
            1,
            f"Batch test data {i}",
        )
        for i in range(count)
    ]


@pytest.mark.usefixtures("setup_database")
@pytest.mark.benchmark(min_rounds=50)
def test_insert_batch_10k(benchmark: Any, connection: Any, driver_name: str) -> None:
    """executemany() of BATCH_ROWS mixed-type rows."""
    p = "?" if driver_name in ('mariadb', 'mariadb_c') else "%s"
    sql = (
        "INSERT INTO perfTestMixedBatch "
        "(user_id, username, email, created_at, updated_at, score, is_active, data) "
        f"VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})"
    )
    data = generate_rows()

    def insert_batch() -> None:
        cursor = connection.cursor()
        cursor.executemany(sql, data)
        cursor.close()

    # Warmup
    for _ in range(3):
        insert_batch()

    result = benchmark(insert_batch)
    print(f"\n{driver_name}: {result}")
