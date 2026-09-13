#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2012-2014 Monty Program Ab
# Copyright (c) 2015-2025 MariaDB Corporation Ab

"""
Async Benchmark: batch INSERT of 10,000 mixed-type rows
executemany() of BATCH_ROWS 8-column rows into a BLACKHOLE table, so the
number reflects the driver's statement building / bulk protocol cost rather
than storage-engine work. Same scenario (and row shape) as asyncmy's
"batch insert" benchmark.
"""

import asyncio
from typing import Any, Callable, Coroutine, List, Tuple

import pytest

from asyncbench import placeholder

BATCH_ROWS = 10000


def generate_rows(count: int = BATCH_ROWS) -> List[Tuple[Any, ...]]:
    return [
        (
            i + 200000,
            f"batch_user_{i}",
            f"batch_{i}@example.com",
            "2024-02-01 00:00:00",
            "2024-02-01 00:00:00",
            round(i * 1.23, 2),
            1,
            f"Batch test data {i}",
        )
        for i in range(count)
    ]


@pytest.mark.usefixtures("setup_database")
@pytest.mark.benchmark(min_rounds=50)
def test_async_insert_batch_10k(
    benchmark: Any,
    async_connection: Any,
    async_driver_name: str,
    event_loop: asyncio.AbstractEventLoop,
    cursor_factory: Callable[[Any], Coroutine[Any, Any, Any]],
) -> None:
    """executemany() of BATCH_ROWS mixed-type rows."""
    p = placeholder(async_driver_name)
    sql = (
        "INSERT INTO perfTestMixedBatch "
        "(user_id, username, email, created_at, updated_at, score, is_active, data) "
        f"VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})"
    )
    data = generate_rows()

    async def insert_batch() -> None:
        cur = await cursor_factory(async_connection)
        await cur.executemany(sql, data)
        await cur.close()

    # Warmup
    for _ in range(3):
        event_loop.run_until_complete(insert_batch())

    benchmark(lambda: event_loop.run_until_complete(insert_batch()))
