#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2012-2014 Monty Program Ab
# Copyright (c) 2015-2025 MariaDB Corporation Ab

"""
Async Benchmark: SELECT 1
Simple async SELECT query benchmark.
"""


def test_async_select_1(benchmark, async_connection, async_driver_name, event_loop, cursor_factory):
    """Benchmark async SELECT 1 query execution."""

    # Warmup
    async def _warmup():
        for _ in range(10):
            cur = await cursor_factory(async_connection)
            await cur.execute("SELECT 1")
            await cur.fetchone()
            await cur.close()

    event_loop.run_until_complete(_warmup())

    async def select_1():
        cur = await cursor_factory(async_connection)
        await cur.execute("SELECT 1")
        result = await cur.fetchone()
        await cur.close()
        return result[0]

    result = benchmark(lambda: event_loop.run_until_complete(select_1()))
