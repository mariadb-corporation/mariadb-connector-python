#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2012-2014 Monty Program Ab
# Copyright (c) 2015-2025 MariaDB Corporation Ab

"""
Async benchmark configuration and fixtures.
Compares: mariadb async (pure Python), mariadb_c async (C extension), aiomysql, asyncmy.
"""

import asyncio
import os
import sys
import pytest


DB_CONFIG = {
    'host': os.environ.get('TEST_DB_HOST', '127.0.0.1'),
    'port': int(os.environ.get('TEST_DB_PORT', '3306')),
    'user': os.environ.get('TEST_DB_USER', 'root'),
    'password': os.environ.get('TEST_DB_PASSWORD', ''),
    'database': os.environ.get('TEST_DB_DATABASE', 'testp'),
}

ASYNC_DRIVERS = ['mariadb_async', 'mariadb_c_async', 'aiomysql', 'asyncmy']


async def _cursor(conn, driver_name):
    """Create a cursor — aiomysql requires await, others don't."""
    if driver_name == 'aiomysql':
        return await conn.cursor()
    return conn.cursor()


def _async_driver_available(name):
    """Check if an async driver is importable."""
    try:
        if name in ('mariadb_async', 'mariadb_c_async'):
            from mariadb import AsyncConnection
            return AsyncConnection is not None
        elif name == 'aiomysql':
            import aiomysql
            return True
        elif name == 'asyncmy':
            import asyncmy
            return True
    except Exception:
        pass
    return False


@pytest.fixture(scope='session')
def event_loop():
    """Session-scoped event loop for async benchmarks."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(
    scope='session',
    params=ASYNC_DRIVERS,
    ids=ASYNC_DRIVERS,
)
def async_driver_name(request):
    """Parametrize tests across async drivers."""
    name = request.param
    if not _async_driver_available(name):
        pytest.skip(f"{name} not installed")
    return name


def _make_async_connection(driver_name, loop):
    """Create an async connection for the given driver."""
    if driver_name == 'mariadb_async':
        os.environ['MARIADB_PYTHON_CONNECTOR'] = 'python'
        import mariadb
        return loop.run_until_complete(
            mariadb.AsyncConnection.connect(**DB_CONFIG)
        )
    elif driver_name == 'mariadb_c_async':
        os.environ['MARIADB_PYTHON_CONNECTOR'] = 'c'
        import mariadb
        return loop.run_until_complete(
            mariadb.AsyncConnection.connect(**DB_CONFIG)
        )
    elif driver_name == 'aiomysql':
        import aiomysql
        cfg = {**DB_CONFIG, 'db': DB_CONFIG['database']}
        cfg.pop('database')
        return loop.run_until_complete(aiomysql.connect(**cfg))
    elif driver_name == 'asyncmy':
        import asyncmy
        cfg = {**DB_CONFIG, 'db': DB_CONFIG['database']}
        cfg.pop('database')
        return loop.run_until_complete(asyncmy.connect(**cfg))
    else:
        raise ValueError(f"Unknown async driver: {driver_name}")


_warmed_up = {}


@pytest.fixture(scope='session', autouse=True)
def async_warmup(async_driver_name, event_loop):
    """Warm up async driver once per session."""
    if async_driver_name in _warmed_up:
        return
    conn = _make_async_connection(async_driver_name, event_loop)
    is_mariadb = 'mariadb' in async_driver_name

    async def _warmup():
        for _ in range(500):
            cur = await _cursor(conn, async_driver_name)
            await cur.execute("DO 1")
            await cur.close()
        for _ in range(500):
            cur = await _cursor(conn, async_driver_name)
            await cur.execute(
                "SELECT seq, 'abcdefghijabcdefghijabcdefghijaa' FROM seq_1_to_1000"
            )
            await cur.fetchall()
            await cur.close()

    event_loop.run_until_complete(_warmup())
    if is_mariadb:
        event_loop.run_until_complete(conn.close())
    else:
        conn.close()
    _warmed_up[async_driver_name] = True


@pytest.fixture(scope='function')
def async_connection(async_driver_name, event_loop):
    """Create an async connection for each test."""
    conn = _make_async_connection(async_driver_name, event_loop)
    yield conn
    try:
        if 'mariadb' in async_driver_name:
            event_loop.run_until_complete(conn.close())
        else:
            conn.close()
    except Exception:
        pass


@pytest.fixture(scope='session')
def cursor_factory(async_driver_name):
    """Return an async callable that creates a cursor for the current driver."""
    async def _factory(conn):
        return await _cursor(conn, async_driver_name)
    return _factory


@pytest.fixture(scope='session')
def setup_database(event_loop):
    """Setup test database tables once per session."""
    os.environ.setdefault('MARIADB_PYTHON_CONNECTOR', 'python')
    import mariadb

    conn = mariadb.connect(**DB_CONFIG)
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

        conn.commit()
    finally:
        cursor.close()
        conn.close()

    yield

    conn = mariadb.connect(**DB_CONFIG)
    cursor = conn.cursor()
    try:
        cursor.execute("DROP TABLE IF EXISTS test100")
        cursor.execute("DROP TABLE IF EXISTS perfTestTextBatch")
        conn.commit()
    finally:
        cursor.close()
        conn.close()
