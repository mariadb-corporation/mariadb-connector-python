#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2012-2014 Monty Program Ab
# Copyright (c) 2015-2025 MariaDB Corporation Ab

"""
Async Benchmark: DO 1
Simple async command execution benchmark.
"""

import asyncio
from typing import Any, Callable, Coroutine


def test_async_do_1(
    benchmark: Any,
    async_connection: Any,
    async_driver_name: str,
    event_loop: asyncio.AbstractEventLoop,
    cursor_factory: Callable[[Any], Coroutine[Any, Any, Any]],
) -> None:
    """Benchmark async DO 1 command execution."""

    async def do_1() -> None:
        cur = await cursor_factory(async_connection)
        await cur.execute("DO 1")
        await cur.close()

    benchmark(lambda: event_loop.run_until_complete(do_1()))
