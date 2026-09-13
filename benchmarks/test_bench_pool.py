#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2012-2014 Monty Program Ab
# Copyright (c) 2015-2025 MariaDB Corporation Ab

"""
Benchmark: POOL_QUERIES point queries from POOL_MAX worker threads through a
POOL_MIN..POOL_MAX connection pool. Sync counterpart of
async/test_bench_async_pool.py: measures acquire/release cost and fairness
under contention. Drivers without a pool (PyMySQL) are skipped.
"""

from concurrent.futures import ThreadPoolExecutor
from types import ModuleType
from typing import Any, Callable, Iterator, Tuple

import pytest

from conftest import DB_CONFIG, transport_args

POOL_MIN = 5
POOL_MAX = 20
POOL_QUERIES = 500


@pytest.fixture(scope='function')
def sync_pool(driver: ModuleType, driver_name: str) -> Iterator[Tuple[Callable[[], Any], Callable[[Any], None], Callable[[], None]]]:
    """(acquire, release, close) over the driver's own pool implementation."""
    cfg = {**DB_CONFIG, **transport_args(driver_name)}
    if driver_name in ('mariadb', 'mariadb_c'):
        pool = driver.create_pool(min_size=POOL_MIN, max_size=POOL_MAX, **cfg)
        # close() on a pooled connection returns it to the pool
        yield pool.acquire, (lambda conn: conn.close()), pool.close
    elif driver_name in ('mysql_connector', 'mysql_connector_pure'):
        from mysql.connector.pooling import MySQLConnectionPool  # pyright: ignore[reportMissingImports]
        if driver_name == 'mysql_connector_pure':
            cfg['use_pure'] = True
        # mysql-connector pools are fixed-size: POOL_MAX connections
        pool = MySQLConnectionPool(pool_name=f"bench_{driver_name}", pool_size=POOL_MAX, **cfg)
        yield pool.get_connection, (lambda conn: conn.close()), (lambda: None)
    else:
        pytest.skip(f"{driver_name} has no connection pool")


@pytest.mark.usefixtures("setup_database", "warmup_session")
@pytest.mark.benchmark(min_rounds=100)
def test_pool_queries(benchmark: Any, sync_pool: Tuple[Callable[[], Any], Callable[[Any], None], Callable[[], None]],
                      driver_name: str) -> None:
    """POOL_QUERIES point queries through the pool from POOL_MAX threads."""
    acquire, release, close = sync_pool
    p = "?" if driver_name in ('mariadb', 'mariadb_c') else "%s"
    sql = f"SELECT * FROM perfTestMixed WHERE user_id = {p} LIMIT 5"

    def query_with_pool(query_id: int) -> int:
        conn = acquire()
        try:
            cur = conn.cursor()
            cur.execute(sql, (query_id % 1000,))
            rows = cur.fetchall()
            cur.close()
            return len(rows)
        finally:
            release(conn)

    try:
        with ThreadPoolExecutor(max_workers=POOL_MAX) as workers:
            def run_all() -> int:
                return len(list(workers.map(query_with_pool, range(POOL_QUERIES))))

            # Warmup
            for _ in range(3):
                run_all()

            result = benchmark(run_all)
        assert result == POOL_QUERIES
    finally:
        close()
