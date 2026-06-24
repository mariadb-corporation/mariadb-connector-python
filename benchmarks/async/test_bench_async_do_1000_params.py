#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2012-2014 Monty Program Ab
# Copyright (c) 2015-2025 MariaDB Corporation Ab

"""
Async Benchmark: DO with 1000 parameters
Benchmark async parameter binding with many parameters.
"""


import asyncio
from typing import Any, Callable, Coroutine

SQL_Q = "DO " + ",".join(["?" for _ in range(1000)])
SQL_P = "DO " + ",".join(["%s" for _ in range(1000)])


def test_async_do_1000_params(
    benchmark: Any,
    async_connection: Any,
    async_driver_name: str,
    event_loop: asyncio.AbstractEventLoop,
    cursor_factory: Callable[[Any], Coroutine[Any, Any, Any]],
) -> None:
    """Benchmark async DO with 1000 parameters."""

    is_mariadb = 'mariadb' in async_driver_name
    sql = SQL_Q if is_mariadb else SQL_P
    params = list(range(1, 1001))

    async def do_1000() -> None:
        cur = await cursor_factory(async_connection)
        await cur.execute(sql, params)
        await cur.close()

    benchmark(lambda: event_loop.run_until_complete(do_1000()))
