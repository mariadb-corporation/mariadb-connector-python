#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2012-2014 Monty Program Ab
# Copyright (c) 2015-2025 MariaDB Corporation Ab

"""
Async Benchmark: DO 1
Simple async command execution benchmark.
"""


def test_async_do_1(benchmark, async_connection, async_driver_name, event_loop, cursor_factory):
    """Benchmark async DO 1 command execution."""

    async def do_1():
        cur = await cursor_factory(async_connection)
        await cur.execute("DO 1")
        await cur.close()

    benchmark(lambda: event_loop.run_until_complete(do_1()))
