#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2012-2014 Monty Program Ab
# Copyright (c) 2015-2025 MariaDB Corporation Ab

"""
Async Benchmark: DO with 1000 parameters
Benchmark async parameter binding with many parameters.
"""


SQL_Q = "DO " + ",".join(["?" for _ in range(1000)])
SQL_P = "DO " + ",".join(["%s" for _ in range(1000)])


def test_async_do_1000_params(benchmark, async_connection, async_driver_name, event_loop, cursor_factory):
    """Benchmark async DO with 1000 parameters."""

    is_mariadb = 'mariadb' in async_driver_name
    sql = SQL_Q if is_mariadb else SQL_P
    params = list(range(1, 1001))

    async def do_1000():
        cur = await cursor_factory(async_connection)
        await cur.execute(sql, params)
        await cur.close()

    benchmark(lambda: event_loop.run_until_complete(do_1000()))
