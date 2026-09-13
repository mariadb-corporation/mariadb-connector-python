#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2012-2014 Monty Program Ab
# Copyright (c) 2015-2025 MariaDB Corporation Ab

"""
Async benchmark fixtures.
Compares: mariadb async (pure Python), mariadb_c async (C extension), aiomysql, asyncmy.
Driver plumbing lives in asyncbench.py rather than here: pytest imports the
parent benchmarks/conftest.py and this file under the same module name, so
test modules cannot reliably ``from conftest import`` shared helpers.
"""

import asyncio
import os
from typing import Any, Awaitable, Callable, Coroutine, Dict, Iterator

import pytest

from asyncbench import (
    ASYNC_DRIVERS,
    DB_CONFIG,
    MIXED_COLUMNS,
    MIXED_ROWS,
    AsyncPoolAdapter,
    async_close,
    async_connect,
    async_create_pool,
    _async_driver_available,
    async_cursor,
    supports_binary,
    transport_args,
)


@pytest.fixture(scope='session')
def event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    """Session-scoped event loop for async benchmarks."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture(
    scope='session',
    params=ASYNC_DRIVERS,
    ids=ASYNC_DRIVERS,
)
def async_driver_name(request: pytest.FixtureRequest) -> Any:
    """Parametrize tests across async drivers."""
    name = request.param
    if not _async_driver_available(name):
        pytest.skip(f"{name} not installed")
    return name


_warmed_up: Dict[str, bool] = {}


@pytest.fixture(scope='session', autouse=True)
def async_warmup(
    async_driver_name: str, event_loop: asyncio.AbstractEventLoop
) -> None:
    """Warm up async driver once per session."""
    if async_driver_name in _warmed_up:
        return

    async def _warmup() -> None:
        conn = await async_connect(async_driver_name)
        for _ in range(500):
            cur = await async_cursor(conn, async_driver_name)
            await cur.execute("DO 1")
            await cur.close()
        for _ in range(500):
            cur = await async_cursor(conn, async_driver_name)
            await cur.execute(
                "SELECT seq, 'abcdefghijabcdefghijabcdefghijaa' FROM seq_1_to_1000"
            )
            await cur.fetchall()
            await cur.close()
        await async_close(conn, async_driver_name)

    event_loop.run_until_complete(_warmup())
    _warmed_up[async_driver_name] = True


@pytest.fixture(scope='function')
def async_connection(
    async_driver_name: str, event_loop: asyncio.AbstractEventLoop
) -> Iterator[Any]:
    """Create an async connection (text protocol) for each test."""
    conn = event_loop.run_until_complete(async_connect(async_driver_name))
    yield conn
    try:
        event_loop.run_until_complete(async_close(conn, async_driver_name))
    except Exception:
        pass


@pytest.fixture(scope='function')
def async_binary_connection(
    async_driver_name: str, event_loop: asyncio.AbstractEventLoop
) -> Iterator[Any]:
    """Async connection set up for the binary protocol (skips drivers
    without one). Use together with binary_cursor_factory."""
    if not supports_binary(async_driver_name):
        pytest.skip(f"{async_driver_name} does not support the binary protocol")
    conn = event_loop.run_until_complete(
        async_connect(async_driver_name, binary=True)
    )
    yield conn
    try:
        event_loop.run_until_complete(async_close(conn, async_driver_name))
    except Exception:
        pass


@pytest.fixture(scope='session')
def cursor_factory(
    async_driver_name: str,
) -> Callable[[Any], Coroutine[Any, Any, Any]]:
    """Return an async callable that creates a text-protocol cursor."""
    async def _factory(conn: Any) -> Any:
        return await async_cursor(conn, async_driver_name)
    return _factory


@pytest.fixture(scope='session')
def binary_cursor_factory(
    async_driver_name: str,
) -> Callable[[Any], Coroutine[Any, Any, Any]]:
    """Return an async callable that creates a binary-protocol cursor."""
    async def _factory(conn: Any) -> Any:
        return await async_cursor(conn, async_driver_name, binary=True)
    return _factory


@pytest.fixture(scope='session')
def connect_factory(
    async_driver_name: str,
) -> Callable[[], Coroutine[Any, Any, Any]]:
    """Return an async callable opening a new connection for the driver."""
    async def _factory() -> Any:
        return await async_connect(async_driver_name)
    return _factory


@pytest.fixture(scope='session')
def close_connection(
    async_driver_name: str,
) -> Callable[[Any], Coroutine[Any, Any, None]]:
    """Return an async callable closing a connection of the driver."""
    async def _close(conn: Any) -> None:
        await async_close(conn, async_driver_name)
    return _close


@pytest.fixture(scope='session')
def pool_factory(
    async_driver_name: str,
) -> Callable[[int, int], Awaitable[AsyncPoolAdapter]]:
    """Return an async callable creating a pool for the driver."""
    async def _factory(min_size: int, max_size: int) -> AsyncPoolAdapter:
        return await async_create_pool(async_driver_name, min_size, max_size)
    return _factory


@pytest.fixture(scope='session')
def setup_database(event_loop: asyncio.AbstractEventLoop) -> Iterator[None]:
    """Setup test database tables once per session."""
    # Plain DDL over the sync API; leave MARIADB_PYTHON_CONNECTOR alone so the
    # implementation selected for the driver under test is not overridden.
    import mariadb

    conn = mariadb.connect(**DB_CONFIG, **transport_args('mariadb_async'))
    cursor = conn.cursor()

    try:
        try:
            cursor.execute("INSTALL SONAME 'ha_blackhole'")
        except Exception:
            pass

        cursor.execute("DROP TABLE IF EXISTS test100")
        cols = ",".join([f"i{i} int" for i in range(1, 101)])
        table_sql = f"CREATE TABLE test100 ({cols})"
        try:
            cursor.execute(table_sql + " ENGINE = MEMORY")
        except Exception:
            cursor.execute(table_sql)
        vals = ",".join([str(i) for i in range(1, 101)])
        cursor.execute(f"INSERT INTO test100 VALUES ({vals})")

        cursor.execute("DROP TABLE IF EXISTS perfTestTextBatch")
        create_table = (
            "CREATE TABLE perfTestTextBatch ("
            "id MEDIUMINT NOT NULL AUTO_INCREMENT, "
            "t0 text, "
            "PRIMARY KEY (id)"
            ") COLLATE='utf8mb4_unicode_ci'"
        )
        try:
            cursor.execute(create_table + " ENGINE = BLACKHOLE")
        except Exception:
            cursor.execute(create_table)

        # Mixed-type table (int / varchar / datetime / decimal / tinyint /
        # text) with a secondary index, populated with MIXED_ROWS rows. Used
        # by the large-result-set, concurrent and pool benchmarks.
        cursor.execute("DROP TABLE IF EXISTS perfTestMixed")
        cursor.execute(
            f"CREATE TABLE perfTestMixed ({MIXED_COLUMNS}, INDEX idx_user_id (user_id)) "
            "DEFAULT CHARSET=utf8mb4"
        )
        cursor.execute(
            "INSERT INTO perfTestMixed "
            "(user_id, username, email, created_at, updated_at, score, is_active, data) "
            "SELECT seq % 1000, CONCAT('user_', seq), CONCAT('user_', seq, '@example.com'), "
            "'2024-01-01 00:00:00' + INTERVAL seq SECOND, "
            "'2024-01-01 00:00:00' + INTERVAL seq MINUTE, "
            "seq * 1.23, seq % 2, CONCAT('Test data for row ', seq) "
            f"FROM seq_1_to_{MIXED_ROWS}"
        )

        # Same schema, BLACKHOLE engine: measures the driver's batch-insert
        # cost without server-side storage work.
        cursor.execute("DROP TABLE IF EXISTS perfTestMixedBatch")
        create_batch = f"CREATE TABLE perfTestMixedBatch ({MIXED_COLUMNS}) DEFAULT CHARSET=utf8mb4"
        try:
            cursor.execute(create_batch + " ENGINE = BLACKHOLE")
        except Exception:
            cursor.execute(create_batch)

        conn.commit()
    finally:
        cursor.close()
        conn.close()

    yield

    conn = mariadb.connect(**DB_CONFIG, **transport_args('mariadb_async'))
    cursor = conn.cursor()
    try:
        cursor.execute("DROP TABLE IF EXISTS test100")
        cursor.execute("DROP TABLE IF EXISTS perfTestTextBatch")
        cursor.execute("DROP TABLE IF EXISTS perfTestMixed")
        cursor.execute("DROP TABLE IF EXISTS perfTestMixedBatch")
        conn.commit()
    finally:
        cursor.close()
        conn.close()
