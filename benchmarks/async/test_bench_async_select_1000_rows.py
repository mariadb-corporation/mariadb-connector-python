#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2012-2014 Monty Program Ab
# Copyright (c) 2015-2025 MariaDB Corporation Ab

"""
Async Benchmark: SELECT 1000 rows
Benchmark async fetching of 1000 rows.
"""


import asyncio
from typing import Any, Callable, Coroutine

SQL = "SELECT seq, 'abcdefghijabcdefghijabcdefghijaa' FROM seq_1_to_1000"


def test_async_select_1000_rows(
    benchmark: Any,
    async_connection: Any,
    async_driver_name: str,
    event_loop: asyncio.AbstractEventLoop,
    cursor_factory: Callable[[Any], Coroutine[Any, Any, Any]],
) -> None:
    """Benchmark async SELECT 1000 rows."""

    is_mariadb = 'mariadb' in async_driver_name
    sql = SQL + (" WHERE 1 = ?" if is_mariadb else " WHERE 1 = %s")

    # Warmup
    async def _warmup() -> None:
        for _ in range(100):
            cur = await cursor_factory(async_connection)
            await cur.execute(sql, (1,))
            await cur.fetchall()
            await cur.close()

    event_loop.run_until_complete(_warmup())

    async def select_1000() -> int:
        cur = await cursor_factory(async_connection)
        await cur.execute(sql, (1,))
        rows = await cur.fetchall()
        await cur.close()
        return len(rows)

    result = benchmark(lambda: event_loop.run_until_complete(select_1000()))
