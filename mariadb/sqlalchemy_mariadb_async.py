# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
SQLAlchemy Async Dialect for MariaDB Connector/Python

Provides async support for SQLAlchemy using mariadb-connector-python's
native AsyncConnection implementation.

Uses lightweight wrapper objects that adapt the async DBAPI cursor/connection
to SQLAlchemy's sync-style interface via await_only(). Works with both the
pure Python (mariadb) and C extension (mariadb_c) async backends.

Optimizations over a naive wrapper:
  - No __getattr__: explicit slots/properties for all accessed attributes
  - No double-buffering: execute + fetchall combined in a single await_only
  - list + index instead of deque for row storage
"""

from typing import Any, List, Optional, Sequence, Tuple

from sqlalchemy.dialects.mysql.mariadbconnector import (
    MySQLDialect_mariadbconnector,
    MySQLExecutionContext_mariadbconnector,
)
from sqlalchemy import pool
from sqlalchemy.util.concurrency import await_only
from sqlalchemy.engine import AdaptedConnection


async def _execute_and_buffer(cursor: Any, query: str, params: Any) -> Optional[List[Any]]:
    """Execute query and fetch all rows in a single async call.

    Combines execute + fetchall into one coroutine so that SQLAlchemy
    only needs a single greenlet switch (await_only) instead of two.
    """
    if params is not None:
        await cursor.execute(query, params)
    else:
        await cursor.execute(query)

    if cursor.field_count > 0:
        return await cursor.fetchall()  # type: ignore[no-any-return]
    return None


class AsyncAdapt_mariadb_cursor:
    """Sync-style cursor wrapper for SQLAlchemy.

    Wraps an async cursor from either mariadb or mariadb_c backend.
    Uses explicit __slots__ and properties instead of __getattr__.
    Rows are stored as a flat list with an integer index (no deque).
    """

    __slots__ = ("_cursor", "_rows", "_row_idx", "server_side")

    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor
        self._rows = None
        self._row_idx = 0
        self.server_side = not cursor.buffered

    @property
    def description(self) -> Any:
        return self._cursor.description

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount  # type: ignore[no-any-return]

    @property
    def lastrowid(self) -> Any:
        return self._cursor.lastrowid

    @property
    def arraysize(self) -> int:
        return self._cursor.arraysize  # type: ignore[no-any-return]

    @arraysize.setter
    def arraysize(self, value: int) -> None:
        self._cursor.arraysize = value

    def execute(self, query: str, params: Any = None, **kw: Any) -> 'AsyncAdapt_mariadb_cursor':
        rows = await_only(_execute_and_buffer(self._cursor, query, params))
        if rows is not None:
            self._rows = rows  # type: ignore[assignment]
            self._row_idx = 0
        else:
            self._rows = None
            self._row_idx = 0
        return self

    def executemany(self, query: str, params_seq: Sequence[Any]) -> None:
        await_only(self._cursor.executemany(query, params_seq))

    def fetchone(self) -> Optional[Any]:
        rows = self._rows
        if rows is None:
            return None
        idx = self._row_idx  # type: ignore[unreachable]
        if idx >= len(rows):
            return None
        self._row_idx = idx + 1
        return rows[idx]

    def fetchmany(self, size: Optional[int] = None) -> List[Any]:
        rows = self._rows
        if rows is None:
            return []
        if size is None:  # type: ignore[unreachable]
            size = self._cursor.arraysize
        idx = self._row_idx
        end = min(idx + size, len(rows))
        self._row_idx = end
        return rows[idx:end]

    def fetchall(self) -> List[Any]:
        rows = self._rows
        if rows is None:
            return []
        idx = self._row_idx  # type: ignore[unreachable]
        self._row_idx = len(rows)
        if idx == 0:
            return rows
        return rows[idx:]

    def close(self) -> None:
        self._rows = None
        self._row_idx = 0

    async def _async_soft_close(self) -> None:
        pass

    def setinputsizes(self, sizes: Any) -> None:
        pass

    def setoutputsize(self, size: int, column: Optional[int] = None) -> None:
        pass


class AsyncAdapt_mariadb_ss_cursor(AsyncAdapt_mariadb_cursor):
    """Server-side (unbuffered/streaming) cursor wrapper.

    Unlike the buffered cursor, fetch methods use await_only on each call
    since rows arrive from the server on demand.
    """

    __slots__ = ()

    def __init__(self, cursor: Any) -> None:
        super().__init__(cursor)
        self.server_side = True

    def execute(self, query: str, params: Any = None, **kw: Any) -> 'AsyncAdapt_mariadb_ss_cursor':
        if params is not None:
            await_only(self._cursor.execute(query, params))
        else:
            await_only(self._cursor.execute(query))
        return self

    def fetchone(self) -> Optional[Any]:
        return await_only(self._cursor.fetchone())

    def fetchmany(self, size: Optional[int] = None) -> List[Any]:
        if size is None:
            size = self._cursor.arraysize
        return await_only(self._cursor.fetchmany(size))

    def fetchall(self) -> List[Any]:
        return await_only(self._cursor.fetchall())

    def close(self) -> None:
        await_only(self._cursor.close())


class AsyncAdapt_mariadb_connection(AdaptedConnection):
    """Sync-style connection wrapper for SQLAlchemy.

    Wraps an async connection from either mariadb or mariadb_c backend.
    Uses explicit methods instead of __getattr__.
    """

    __slots__ = ("dbapi", "_connection")

    def __init__(self, dbapi: Any, connection: Any) -> None:
        self.dbapi = dbapi
        self._connection = connection

    def cursor(self, **kwargs: Any) -> AsyncAdapt_mariadb_cursor:
        cursor = self._connection.cursor(**kwargs)
        if kwargs.get("buffered", True):
            return AsyncAdapt_mariadb_cursor(cursor)
        return AsyncAdapt_mariadb_ss_cursor(cursor)

    @property
    def autocommit(self) -> bool:
        return self._connection.autocommit  # type: ignore[no-any-return]

    @autocommit.setter
    def autocommit(self, value: bool) -> None:
        await_only(self._connection.set_autocommit(value))

    def commit(self) -> None:
        await_only(self._connection.commit())

    def rollback(self) -> None:
        await_only(self._connection.rollback())

    def close(self) -> None:
        await_only(self._connection.close())


class AsyncAdapt_mariadb_dbapi:
    """Minimal DBAPI module facade for SQLAlchemy.

    Provides exception classes, type constructors, and a connect() method
    that returns an AsyncAdapt_mariadb_connection wrapper.
    """

    def __init__(self, mariadb_asyncio: Any) -> None:
        self.mariadb_asyncio = mariadb_asyncio
        for name in (
            'Error', 'Warning', 'InterfaceError', 'DatabaseError',
            'InternalError', 'OperationalError', 'ProgrammingError',
            'IntegrityError', 'DataError', 'NotSupportedError',
            'apilevel', 'threadsafety', 'paramstyle'
        ):
            if hasattr(mariadb_asyncio, name):
                setattr(self, name, getattr(mariadb_asyncio, name))

        import mariadb
        for name in (
            'Binary', 'Date', 'Time', 'Timestamp', 'DateFromTicks',
            'TimeFromTicks', 'TimestampFromTicks', 'STRING', 'BINARY',
            'NUMBER', 'DATETIME', 'ROWID'
        ):
            if hasattr(mariadb, name):
                setattr(self, name, getattr(mariadb, name))

    def connect(self, *args: Any, **kwargs: Any) -> AsyncAdapt_mariadb_connection:
        connection = await_only(self.mariadb_asyncio.connect(*args, **kwargs))
        return AsyncAdapt_mariadb_connection(self, connection)


class MySQLExecutionContext_mariadbconnector_async(
    MySQLExecutionContext_mariadbconnector
):
    def create_server_side_cursor(self) -> Any:
        return self._dbapi_connection.cursor(buffered=False)

    def create_default_cursor(self) -> Any:
        return self._dbapi_connection.cursor(buffered=True)


class MySQLDialect_mariadbconnector_async(MySQLDialect_mariadbconnector):
    """
    Async dialect for MariaDB Connector/Python.

    Uses lightweight wrapper objects that adapt the async DBAPI to
    SQLAlchemy's sync-style interface via await_only(). Works with
    both mariadb (pure Python) and mariadb_c (C extension) backends.

    Usage:
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(
            "mariadb+mariadbconnector_async://user:pass@host/db"
        )
    """

    driver = "mariadbconnector_async"
    supports_statement_cache = True
    supports_server_side_cursors = True
    is_async = True

    execution_ctx_cls = MySQLExecutionContext_mariadbconnector_async

    @classmethod
    def import_dbapi(cls) -> Any:
        import mariadb.asyncio
        return AsyncAdapt_mariadb_dbapi(mariadb.asyncio)

    @classmethod
    def get_pool_class(cls, url: Any) -> Any:
        return pool.AsyncAdaptedQueuePool

    @classmethod
    def load_provisioning(cls) -> None:
        try:
            from sqlalchemy.dialects.mysql import provision  # noqa: F401
        except ImportError:
            pass


# Alias for registration
dialect = MySQLDialect_mariadbconnector_async
