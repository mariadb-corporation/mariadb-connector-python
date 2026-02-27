#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2012-2014 Monty Program Ab
# Copyright (c) 2015-2025 MariaDB Corporation Ab

"""
Async Benchmark: Batch INSERT
Benchmark async batch insert operations with 100 rows.
"""

import pytest
import random
import string


def random_string(length=100):
    """Generate a random string with emojis."""
    chars = list(string.ascii_letters + string.digits + "\\Z😎🌶🎤🥂")
    return ''.join(random.choice(chars) for _ in range(length))


@pytest.mark.usefixtures("setup_database")
def test_async_insert_batch(benchmark, async_connection, async_driver_name, event_loop, cursor_factory):
    """Benchmark async batch insert of 100 rows."""

    is_mariadb = 'mariadb' in async_driver_name
    placeholder = "?" if is_mariadb else "%s"

    async def insert_batch():
        s = random_string(100)
        data = [(s,) for _ in range(100)]
        cur = await cursor_factory(async_connection)
        await cur.executemany(
            f"INSERT INTO perfTestTextBatch(t0) VALUES ({placeholder})", data
        )
        await cur.close()
        # Clear table
        cur = await cursor_factory(async_connection)
        await cur.execute("DELETE FROM perfTestTextBatch")
        await cur.close()

    benchmark(lambda: event_loop.run_until_complete(insert_batch()))
