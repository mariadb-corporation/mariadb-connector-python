#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2012-2014 Monty Program Ab
# Copyright (c) 2015-2025 MariaDB Corporation Ab

"""
Async Benchmark: connection pool throughput
POOL_QUERIES tasks are started at once against a POOL_MIN..POOL_MAX
connection pool; each acquires a connection, runs an indexed point query and
releases it. Measures acquire/release cost and pool fairness under
contention. Same scenario as asyncmy's "connection pool" benchmark.
"""

import asyncio
from typing import Any, Awaitable, Callable, Coroutine, Iterator, List

import pytest

from asyncbench import AsyncPoolAdapter, placeholder

POOL_MIN = 5
POOL_MAX = 20
POOL_QUERIES = 500


@pytest.fixture(scope='function')
def async_pool(
    async_driver_name: str,
    event_loop: asyncio.AbstractEventLoop,
    pool_factory: Callable[[int, int], Awaitable[AsyncPoolAdapter]],
) -> Iterator[AsyncPoolAdapter]:
    pool = event_loop.run_until_complete(pool_factory(POOL_MIN, POOL_MAX))
    yield pool
    try:
        event_loop.run_until_complete(pool.close())
    except Exception:
        pass


@pytest.mark.usefixtures("setup_database")
@pytest.mark.benchmark(min_rounds=100)
def test_async_pool_queries(
    benchmark: Any,
    async_pool: AsyncPoolAdapter,
    async_driver_name: str,
    event_loop: asyncio.AbstractEventLoop,
    cursor_factory: Callable[[Any], Coroutine[Any, Any, Any]],
) -> None:
    """POOL_QUERIES concurrent point queries through a POOL_MIN..POOL_MAX pool."""
    sql = f"SELECT * FROM perfTestMixed WHERE user_id = {placeholder(async_driver_name)} LIMIT 5"

    async def query_with_pool(query_id: int) -> int:
        async with async_pool.acquire() as conn:
            cur = await cursor_factory(conn)
            await cur.execute(sql, (query_id % 1000,))
            rows = await cur.fetchall()
            await cur.close()
            return len(rows)

    async def run_all() -> int:
        results: List[int] = await asyncio.gather(
            *(query_with_pool(i) for i in range(POOL_QUERIES))
        )
        return len(results)

    # Warmup
    for _ in range(3):
        event_loop.run_until_complete(run_all())

    result = benchmark(lambda: event_loop.run_until_complete(run_all()))
    assert result == POOL_QUERIES
