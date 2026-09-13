#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2012-2014 Monty Program Ab
# Copyright (c) 2015-2025 MariaDB Corporation Ab

"""
Benchmark: CONCURRENT_COUNT threads, each doing connect + indexed single-row point query
+ close, all at once. Sync counterpart of async/test_bench_async_concurrent.py
(threads stand in for asyncio tasks): measures connection setup cost and how
the driver behaves with many connections opened in parallel.
"""

from concurrent.futures import ThreadPoolExecutor
from types import ModuleType
from typing import Any

import pytest

from conftest import DB_CONFIG, transport_args

CONCURRENT_COUNT = 50


def _connect(driver: ModuleType, driver_name: str) -> Any:
    if driver_name == 'mysql_connector_pure':
        return driver.connect(**DB_CONFIG, use_pure=True, **transport_args(driver_name))
    return driver.connect(**DB_CONFIG, **transport_args(driver_name))


@pytest.mark.usefixtures("setup_database", "warmup_session")
@pytest.mark.benchmark(min_rounds=100)
def test_concurrent_connections(benchmark: Any, driver: ModuleType, driver_name: str) -> None:
    """CONCURRENT_COUNT connect + point query + close, in parallel threads."""
    p = "?" if driver_name in ('mariadb', 'mariadb_c') else "%s"
    sql = f"SELECT * FROM perfTestMixed WHERE user_id = {p} LIMIT 1"

    def single_query(query_id: int) -> int:
        conn = _connect(driver, driver_name)
        try:
            cur = conn.cursor()
            cur.execute(sql, (query_id % 1000,))
            rows = cur.fetchall()
            cur.close()
            return len(rows)
        finally:
            conn.close()

    with ThreadPoolExecutor(max_workers=CONCURRENT_COUNT) as pool:
        def run_all() -> int:
            return len(list(pool.map(single_query, range(CONCURRENT_COUNT))))

        # Warmup
        for _ in range(3):
            run_all()

        result = benchmark(run_all)
    assert result == CONCURRENT_COUNT
