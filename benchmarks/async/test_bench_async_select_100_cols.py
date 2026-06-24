#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2012-2014 Monty Program Ab
# Copyright (c) 2015-2025 MariaDB Corporation Ab

"""
Async Benchmark: SELECT 100 columns
Benchmark async fetching of a row with 100 integer columns.
"""

import asyncio
from typing import Any, Callable, Coroutine

import pytest


@pytest.mark.usefixtures("setup_database")
def test_async_select_100_cols(
    benchmark: Any,
    async_connection: Any,
    async_driver_name: str,
    event_loop: asyncio.AbstractEventLoop,
    cursor_factory: Callable[[Any], Coroutine[Any, Any, Any]],
) -> None:
    """Benchmark async SELECT 100 columns."""

    is_mariadb = 'mariadb' in async_driver_name
    sql = "SELECT * FROM test100 WHERE 1 = ?" if is_mariadb else "SELECT * FROM test100 WHERE 1 = %s"

    async def select_100() -> Any:
        cur = await cursor_factory(async_connection)
        await cur.execute(sql, (1,))
        row = await cur.fetchone()
        await cur.close()
        return sum(row)

    result = benchmark(lambda: event_loop.run_until_complete(select_100()))
