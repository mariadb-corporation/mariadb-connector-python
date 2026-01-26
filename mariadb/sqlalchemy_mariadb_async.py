# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
SQLAlchemy Async Dialect for MariaDB Connector/Python

Provides async support for SQLAlchemy using mariadb-connector-python's
native AsyncConnection implementation.
"""

from collections import deque
from sqlalchemy.dialects.mysql.mariadbconnector import MySQLDialect_mariadbconnector, MySQLExecutionContext_mariadbconnector
from sqlalchemy import pool
from sqlalchemy.util.concurrency import await_only
from sqlalchemy.engine import AdaptedConnection


class AsyncAdapt_mariadb_cursor:
    """Adapter for mariadb AsyncCursor to work with SQLAlchemy's sync-style API"""
    
    __slots__ = ("_cursor", "await_", "_rows", "server_side")
    
    def __init__(self, cursor, await_):
        self._cursor = cursor
        self.await_ = await_
        self._rows = deque()
        # Server-side cursors use unbuffered mode
        self.server_side = not cursor.buffered
    
    def __getattr__(self, name):
        return getattr(self._cursor, name)
    
    @property
    def arraysize(self):
        return self._cursor.arraysize
    
    @arraysize.setter
    def arraysize(self, value):
        self._cursor.arraysize = value
    
    async def _async_soft_close(self):
        """Async soft close for SQLAlchemy result handling"""
        pass
    
    def close(self):
        self._rows.clear()
        self.await_(self._cursor.close())
    
    def execute(self, query, params=None, **kw):
        """Execute query and cache all results immediately"""
        self.await_(self._cursor.execute(query, params, **kw))
        
        # If there's a result set, fetch all rows and cache them
        # This is necessary because SQLAlchemy's result is not async
        if self._cursor.description:
            rows = self.await_(self._cursor.fetchall())
            self._rows = deque(rows)
        
        return self
    
    def executemany(self, query, params_seq):
        return self.await_(self._cursor.executemany(query, params_seq))
    
    def __iter__(self):
        while self._rows:
            yield self._rows.popleft()
    
    def fetchone(self):
        if self._rows:
            return self._rows.popleft()
        return None
    
    def fetchmany(self, size=None):
        if size is None:
            size = self._cursor.arraysize
        
        result = [self._rows.popleft() for _ in range(min(size, len(self._rows)))]
        return result
    
    def fetchall(self):
        result = list(self._rows)
        self._rows.clear()
        return result
    
    def setinputsizes(self, sizes):
        pass
    
    def setoutputsize(self, size, column=None):
        pass


class AsyncAdapt_mariadb_connection(AdaptedConnection):
    """Adapter for mariadb AsyncConnection to work with SQLAlchemy's sync-style API"""
    
    __slots__ = ("dbapi", "_connection")
    
    await_ = staticmethod(await_only)
    
    def __init__(self, dbapi, connection):
        self.dbapi = dbapi
        self._connection = connection
    
    def __getattr__(self, name):
        return getattr(self._connection, name)
    
    @property
    def autocommit(self):
        """Get autocommit status"""
        return self._connection.autocommit
    
    @autocommit.setter
    def autocommit(self, value):
        """Set autocommit mode using async method"""
        self.await_(self._connection.set_autocommit(value))
    
    def cursor(self, **kwargs):
        """Return wrapped async cursor"""
        cursor = self._connection.cursor(**kwargs)
        return AsyncAdapt_mariadb_cursor(cursor, self.await_)
    
    def commit(self):
        self.await_(self._connection.commit())
    
    def rollback(self):
        self.await_(self._connection.rollback())
    
    def close(self):
        self.await_(self._connection.close())


class AsyncAdapt_mariadb_dbapi:
    """
    DBAPI wrapper to handle async connect() and wrap connections.
    
    Wraps mariadb AsyncConnection and AsyncCursor with adapters that provide
    sync-style methods for SQLAlchemy's greenlet-based async execution.
    """
    
    def __init__(self, mariadb_asyncio):
        self.mariadb_asyncio = mariadb_asyncio
        # Copy exception classes and constants from mariadb.asyncio
        for name in (
            'Error', 'Warning', 'InterfaceError', 'DatabaseError',
            'InternalError', 'OperationalError', 'ProgrammingError',
            'IntegrityError', 'DataError', 'NotSupportedError',
            'apilevel', 'threadsafety', 'paramstyle'
        ):
            if hasattr(mariadb_asyncio, name):
                setattr(self, name, getattr(mariadb_asyncio, name))
        
        # Import type constructors from main mariadb module
        import mariadb
        for name in (
            'Binary', 'Date', 'Time', 'Timestamp', 'DateFromTicks',
            'TimeFromTicks', 'TimestampFromTicks', 'STRING', 'BINARY',
            'NUMBER', 'DATETIME', 'ROWID'
        ):
            if hasattr(mariadb, name):
                setattr(self, name, getattr(mariadb, name))
    
    def connect(self, *args, **kwargs):
        """Handle async connect and return wrapped AsyncConnection"""
        # Get the async connection coroutine and await it
        async_conn_coro = self.mariadb_asyncio.connect(*args, **kwargs)
        connection = await_only(async_conn_coro)
        
        # Wrap the connection with AsyncAdapt adapter
        return AsyncAdapt_mariadb_connection(self, connection)


class MySQLExecutionContext_mariadbconnector_async(MySQLExecutionContext_mariadbconnector):
    """Execution context for async mariadb connector with server-side cursor support"""
    
    def create_server_side_cursor(self):
        """Create unbuffered cursor for server-side (streaming) results"""
        return self._dbapi_connection.cursor(buffered=False)
    
    def create_default_cursor(self):
        """Create buffered cursor for default (client-side) results"""
        return self._dbapi_connection.cursor(buffered=True)


class MySQLDialect_mariadbconnector_async(MySQLDialect_mariadbconnector):
    """
    Async dialect for MariaDB Connector/Python.
    
    Uses AsyncAdapt wrappers to integrate mariadb-connector-python's AsyncConnection
    with SQLAlchemy's greenlet-based async execution model.
    
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
    def import_dbapi(cls):
        """Import the async DBAPI module with minimal wrapper"""
        import mariadb.asyncio
        return AsyncAdapt_mariadb_dbapi(mariadb.asyncio)
    
    @classmethod
    def get_pool_class(cls, url):
        """Use AsyncAdaptedQueuePool for async connections"""
        return pool.AsyncAdaptedQueuePool
    
    @classmethod
    def load_provisioning(cls):
        """Load provisioning hooks for SQLAlchemy test suite.
        
        This ensures that MySQL/MariaDB provisioning hooks (like temp_table_keyword_args)
        are available when running SQLAlchemy tests with the async dialect.
        """
        # Explicitly import SQLAlchemy's MySQL provision module to register
        # handlers for the "mariadb" backend (which is what get_backend_name() returns)
        try:
            from sqlalchemy.dialects.mysql import provision  # noqa: F401
        except ImportError:
            pass


# Alias for registration
dialect = MySQLDialect_mariadbconnector_async
