#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2012-2014 Monty Program Ab
# Copyright (c) 2015-2025 MariaDB Corporation Ab

"""
Async Benchmark: concurrent queries
CONCURRENT_COUNT tasks run at once; each opens its own connection, runs an
indexed single-row point query and closes. Measures connection setup cost and how well
the driver interleaves I/O on one event loop. Same scenario as asyncmy's
"concurrent queries" benchmark.
"""

import asyncio
from typing import Any, Callable, Coroutine, List

import pytest

from asyncbench import placeholder

CONCURRENT_COUNT = 50


@pytest.mark.usefixtures("setup_database")
@pytest.mark.benchmark(min_rounds=100)
def test_async_concurrent_connections(
    benchmark: Any,
    async_driver_name: str,
    event_loop: asyncio.AbstractEventLoop,
    connect_factory: Callable[[], Coroutine[Any, Any, Any]],
    close_connection: Callable[[Any], Coroutine[Any, Any, None]],
    cursor_factory: Callable[[Any], Coroutine[Any, Any, Any]],
) -> None:
    """CONCURRENT_COUNT connect + point query + close, all concurrently."""
    sql = f"SELECT * FROM perfTestMixed WHERE user_id = {placeholder(async_driver_name)} LIMIT 1"

    async def single_query(query_id: int) -> int:
        conn = await connect_factory()
        try:
            cur = await cursor_factory(conn)
            await cur.execute(sql, (query_id % 1000,))
            rows = await cur.fetchall()
            await cur.close()
            return len(rows)
        finally:
            await close_connection(conn)

    async def run_all() -> int:
        results: List[int] = await asyncio.gather(
            *(single_query(i) for i in range(CONCURRENT_COUNT))
        )
        return len(results)

    # Warmup
    for _ in range(3):
        event_loop.run_until_complete(run_all())

    result = benchmark(lambda: event_loop.run_until_complete(run_all()))
    assert result == CONCURRENT_COUNT
