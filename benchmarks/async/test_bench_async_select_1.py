#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2012-2014 Monty Program Ab
# Copyright (c) 2015-2025 MariaDB Corporation Ab

"""
Async Benchmark: SELECT 1
Simple async SELECT query benchmark.
"""

import asyncio
from typing import Any, Callable, Coroutine


def test_async_select_1(
    benchmark: Any,
    async_connection: Any,
    async_driver_name: str,
    event_loop: asyncio.AbstractEventLoop,
    cursor_factory: Callable[[Any], Coroutine[Any, Any, Any]],
) -> None:
    """Benchmark async SELECT 1 query execution."""

    # Warmup
    async def _warmup() -> None:
        for _ in range(10):
            cur = await cursor_factory(async_connection)
            await cur.execute("SELECT 1")
            await cur.fetchone()
            await cur.close()

    event_loop.run_until_complete(_warmup())

    async def select_1() -> Any:
        cur = await cursor_factory(async_connection)
        await cur.execute("SELECT 1")
        result = await cur.fetchone()
        await cur.close()
        return result[0]

    result = benchmark(lambda: event_loop.run_until_complete(select_1()))
