#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2012-2014 Monty Program Ab
# Copyright (c) 2015-2025 MariaDB Corporation Ab

"""
Shared helpers for the async benchmarks (driver abstraction, transport,
pools, schema). Imported by conftest.py and the test modules.

Every driver is connected over the SAME transport (see transport_args) with
TLS disabled, so the numbers compare protocol/parsing cost only.
"""

import os
from typing import Any, Dict, Optional


# Connection transport selection (same rules as the sync conftest).
# Set TEST_DB_UNIX_SOCKET (e.g. /run/mysqld/mysqld.sock) to force every driver
# onto that unix socket; leave it unset to connect over TCP/IP.
_UNIX_SOCKET: Optional[str] = os.environ.get('TEST_DB_UNIX_SOCKET') or None
_HOST_ENV: str = os.environ.get('TEST_DB_HOST', '127.0.0.1')
# libmariadb only selects the unix socket when host is 'localhost'; an IP host
# forces TCP. So use 'localhost' in socket mode, and an IP to force TCP otherwise.
_HOST: str = 'localhost' if _UNIX_SOCKET else ('127.0.0.1' if _HOST_ENV == 'localhost' else _HOST_ENV)

DB_CONFIG: Dict[str, Any] = {
    'host': _HOST,
    'port': int(os.environ.get('TEST_DB_PORT', '3306')),
    'user': os.environ.get('TEST_DB_USER', 'root'),
    'password': os.environ.get('TEST_DB_PASSWORD', ''),
    'database': os.environ.get('TEST_DB_DATABASE', 'testp'),
}

ASYNC_DRIVERS = ['mariadb_async', 'mariadb_c_async', 'aiomysql', 'asyncmy']

# Rows in the mixed-type table used by the "large result set", "concurrent"
# and "pool" benchmarks (asyncmy's suite uses the same schema).
MIXED_ROWS = 10000


def is_mariadb_driver(driver_name: str) -> bool:
    return 'mariadb' in driver_name


def placeholder(driver_name: str) -> str:
    """Parameter marker for the driver ('?' for mariadb, '%s' for the others)."""
    return '?' if is_mariadb_driver(driver_name) else '%s'


def transport_args(driver_name: str) -> Dict[str, Any]:
    """Per-driver kwargs so every driver uses the SAME transport with TLS
    disabled. mariadb negotiates TLS by default when the server offers it;
    aiomysql/asyncmy never do unless asked, so the flag matters for fairness."""
    args: Dict[str, Any] = {}
    if is_mariadb_driver(driver_name):
        args['ssl'] = False
    if _UNIX_SOCKET:
        args['unix_socket'] = _UNIX_SOCKET
    return args


def connection_kwargs(driver_name: str, binary: bool = False) -> Dict[str, Any]:
    """Full connect() kwargs for a driver. ``binary=True`` asks for the
    binary (prepared statement) protocol where the driver selects it at
    connection level (asyncmy's stmt_cache_size); mariadb selects it per
    cursor instead (see binary_cursor_factory)."""
    cfg: Dict[str, Any] = {**DB_CONFIG, **transport_args(driver_name)}
    if not is_mariadb_driver(driver_name):
        cfg['db'] = cfg.pop('database')
    if driver_name == 'asyncmy':
        cfg['stmt_cache_size'] = 16 if binary else 0
    return cfg


def _select_impl(driver_name: str) -> None:
    if driver_name == 'mariadb_async':
        os.environ['MARIADB_PYTHON_CONNECTOR'] = 'python'
    elif driver_name == 'mariadb_c_async':
        os.environ['MARIADB_PYTHON_CONNECTOR'] = 'c'


async def async_connect(driver_name: str, binary: bool = False) -> Any:
    """Open one connection for the given driver."""
    cfg = connection_kwargs(driver_name, binary)
    if is_mariadb_driver(driver_name):
        _select_impl(driver_name)
        import mariadb
        return await mariadb.AsyncConnection.connect(**cfg)
    elif driver_name == 'aiomysql':
        import aiomysql
        return await aiomysql.connect(**cfg)
    elif driver_name == 'asyncmy':
        import asyncmy
        return await asyncmy.connect(**cfg)
    raise ValueError(f"Unknown async driver: {driver_name}")


async def async_close(conn: Any, driver_name: str) -> None:
    """Close a connection (mariadb: await close(); others: ensure_closed())."""
    if is_mariadb_driver(driver_name):
        await conn.close()
    else:
        await conn.ensure_closed()


async def async_cursor(conn: Any, driver_name: str, binary: bool = False) -> Any:
    """Create a cursor - aiomysql requires await, others don't.
    ``binary=True`` selects the binary protocol for mariadb; for asyncmy the
    connection decides (stmt_cache_size) and aiomysql has no binary path."""
    if driver_name == 'aiomysql':
        return await conn.cursor()
    if binary and is_mariadb_driver(driver_name):
        return conn.cursor(binary=True)
    return conn.cursor()


def supports_binary(driver_name: str) -> bool:
    return driver_name != 'aiomysql'


def _async_driver_available(name: str) -> bool:
    """Check if an async driver is importable."""
    try:
        if is_mariadb_driver(name):
            from mariadb import AsyncConnection
            return AsyncConnection is not None
        elif name == 'aiomysql':
            import aiomysql  # noqa: F401
            return True
        elif name == 'asyncmy':
            import asyncmy  # noqa: F401
            return True
    except Exception:
        pass
    return False


class AsyncPoolAdapter:
    """Uniform facade over the three drivers' connection pools."""

    def __init__(self, driver_name: str, pool: Any) -> None:
        self.driver_name = driver_name
        self.pool = pool

    def acquire(self) -> Any:
        """Async context manager yielding a connection."""
        if is_mariadb_driver(self.driver_name):
            return self.pool.connection()
        return self.pool.acquire()

    async def close(self) -> None:
        if is_mariadb_driver(self.driver_name):
            await self.pool.close()
        else:
            self.pool.close()
            await self.pool.wait_closed()


async def async_create_pool(driver_name: str, min_size: int, max_size: int) -> AsyncPoolAdapter:
    """Create a pre-filled connection pool for the driver."""
    cfg = connection_kwargs(driver_name)
    if is_mariadb_driver(driver_name):
        _select_impl(driver_name)
        import mariadb
        pool = await mariadb.create_async_pool(min_size=min_size, max_size=max_size, **cfg)
    elif driver_name == 'aiomysql':
        import aiomysql
        pool = await aiomysql.create_pool(minsize=min_size, maxsize=max_size, **cfg)
    elif driver_name == 'asyncmy':
        from asyncmy.pool import create_pool
        pool = await create_pool(minsize=min_size, maxsize=max_size, **cfg)
    else:
        raise ValueError(f"Unknown async driver: {driver_name}")
    return AsyncPoolAdapter(driver_name, pool)


MIXED_COLUMNS = (
    "id INT NOT NULL AUTO_INCREMENT, "
    "user_id INT NOT NULL, "
    "username VARCHAR(50) NOT NULL, "
    "email VARCHAR(100) NOT NULL, "
    "created_at DATETIME NOT NULL, "
    "updated_at DATETIME NOT NULL, "
    "score DECIMAL(10,2) NOT NULL, "
    "is_active TINYINT NOT NULL, "
    "data TEXT, "
    "PRIMARY KEY (id)"
)
