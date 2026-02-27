# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from __future__ import annotations

# PyPy compatibility check - prevent loading C extension async on PyPy
import sys
if hasattr(sys, 'pypy_version_info'):
    raise ImportError(
        "mariadb_c async implementation is not compatible with PyPy due to cpyext limitations. "
        "Please use the pure Python 'mariadb' package for async operations on PyPy."
    )

import asyncio
import socket
from typing import Optional

from .connections import StmtCache

# Import shared constants and exceptions to avoid circular dependencies
from mariadb_shared.constants import STATUS, TPC_STATE, INFO
from mariadb_shared.exceptions import (
    Error, ProgrammingError, OperationalError,
)
from mariadb_shared.async_connection_common import AsyncConnectionCommon

# Import mariadbapi_version from C extension
from mariadb_c._mariadb import mariadbapi_version
from packaging import version

from mariadb_shared.xid import Xid

_DEFAULT_CHARSET = "utf8mb4"
_DEFAULT_COLLATION = "utf8mb4_general_ci"
_MAX_TPC_XID_SIZE = 64

# Wait status flags for non-blocking operations
MYSQL_WAIT_READ = 1
MYSQL_WAIT_WRITE = 2
MYSQL_WAIT_EXCEPT = 4
MYSQL_WAIT_TIMEOUT = 8

# Import the C connection base class
from mariadb_c._mariadb import connection as CConnection

class AsyncConnection(CConnection, AsyncConnectionCommon):
    """
    MariaDB Connector/Python Async Connection Object

    Handles async connection to a MariaDB or MySQL database server.
    It encapsulates a database session with async/await support.

    Connections are created using the method mariadb_c.asyncConnect()
    """

    def _check_closed(self):
        if self._closed:
            raise ProgrammingError("Invalid connection or "
                                           "not connected")

    def __init__(self, *args, **kwargs):
        """
        Initialize async connection (does not connect yet).
        Use AsyncConnection.connect() or asyncConnect() to connect.
        """
        # Pre-initialize _stmt_cache before super().__init__() to avoid AttributeError
        self._stmt_cache: Optional[StmtCache] = None

        # Initialize Python-side attributes first (same order as sync)
        self._socket = None
        self._socket_fd: Optional[int] = None
        self._used = 0
        self._last_executed_statement = None
        self.__last_used = 0
        self.tpc_state = TPC_STATE.NONE
        self._xid = None
        self._pooled_connection = None
        self._active_async_cursor = None  # Python-level tracking for async cursors only
        
        # Persistent event loop state for efficient I/O waiting
        self._loop = None
        self._read_event = None
        self._write_event = None
        
        # Extract parameters that need special handling (use .pop() like sync)
        self._autocommit = kwargs.pop("autocommit", False)
        kwargs.pop("reconnect", None)
        self._converter_param = kwargs.pop("converter", None)
        self._binary = bool(kwargs.pop("binary", False))
        # Remove debug parameter that C extension doesn't support
        kwargs.pop("debug", None)
        self._cache_prep_stmts: bool = bool(kwargs.pop("cache_prep_stmts", True))
        self._prep_stmt_cache_size: int = int(kwargs.pop("prep_stmt_cache_size", 100))
        
        # Handle SSL dictionary for compatibility (mariadb-c compatibility)
        if 'ssl' in kwargs and isinstance(kwargs['ssl'], dict):
            ssl_dict = kwargs.pop('ssl')
            # Map dictionary keys to individual SSL parameters
            if 'ca' in ssl_dict:
                kwargs['ssl_ca'] = ssl_dict['ca']
            if 'cert' in ssl_dict:
                kwargs['ssl_cert'] = ssl_dict['cert']
            if 'key' in ssl_dict:
                kwargs['ssl_key'] = ssl_dict['key']
            if 'cipher' in ssl_dict:
                kwargs['ssl_cipher'] = ssl_dict['cipher']
            if 'capath' in ssl_dict:
                kwargs['ssl_capath'] = ssl_dict['capath']
            if 'crlpath' in ssl_dict:
                kwargs['ssl_crlpath'] = ssl_dict['crlpath']
            if 'verify_cert' in ssl_dict:
                kwargs['ssl_verify_cert'] = ssl_dict['verify_cert']
            # Set ssl to True to enable SSL
            kwargs['ssl'] = True
        
        # Validate host parameter (same as sync)
        if "host" in kwargs:
            host = kwargs.get("host")
            if version.Version(mariadbapi_version) < version.Version('3.3.0') and ',' in host:
                raise ProgrammingError("Host failover list requires MariaDB Connector/C 3.3.0 or newer")
        
        # Store args/kwargs for later connection
        self._args = args
        self._kwargs = kwargs
        
        # Initialize C struct fields without connecting (makes active_result_cursor available)
        CConnection._init_fields_only(self)
    
    @classmethod
    async def connect(cls, *args, **kwargs):
        """
        Create and connect an async connection (classmethod).
        
        This is the recommended way to create async connections.
        
        Note: On Windows with SSL, the pure Python async implementation is automatically
        used due to SCHANNEL buffering issues with the C extension.
        
        Args:
            **kwargs: Connection parameters
            
        Returns:
            Connected AsyncConnection instance
        """
        # Windows + SSL workaround: Use pure Python async implementation
        # This is needed until MariaDB Connector/C properly supports async SSL on Windows
        import platform
        if platform.system() == "Windows" and cls.__module__ == 'mariadb_c.async_connections':
            # Check if SSL is enabled in kwargs (check all SSL-related parameters)
            ssl_param = kwargs.get('ssl', False)
            ssl_enabled = (
                ssl_param is True or 
                isinstance(ssl_param, dict) or
                kwargs.get('ssl_ca') or 
                kwargs.get('ssl_cert') or
                kwargs.get('ssl_key') or
                kwargs.get('ssl_capath') or
                kwargs.get('ssl_cipher') or
                kwargs.get('ssl_crlpath') or
                kwargs.get('ssl_verify_cert') or
                kwargs.get('tls_version') or
                kwargs.get('tls_fp')
            )
            if ssl_enabled:
                # Import and use pure Python async implementation instead
                try:
                    from mariadb import async_connection as async_conn_module
                    # Call pure Python's connect() classmethod directly
                    return await async_conn_module.AsyncConnection.connect(*args, **kwargs)
                except ImportError:
                    # If pure Python not available, continue with C implementation
                    pass
        
        # Use C extension implementation
        instance = cls(*args, **kwargs)
        await instance._connect()
        return instance
    
    async def _connect(self):
        """
        Internal method to establish async connection.
        
        Uses standard blocking mysql_real_connect() for initial connection (including SSL handshake),
        then sets MYSQL_OPT_NONBLOCK afterward. This avoids SSL/TLS issues on Windows with SCHANNEL
        buffering and simplifies the code.
        """
        # Call the C extension's __init__ which does mysql_real_connect() synchronously
        CConnection.__init__(self, *self._args, **self._kwargs)

        # Connection is now fully established (including SSL handshake)
        # NOW set MYSQL_OPT_NONBLOCK for async operations
        self.set_nonblock_option()

        # Set converter on C extension's _converter field (same as sync)
        if self._converter_param is not None:
            self._converter = self._converter_param

        cache_size: int = self._prep_stmt_cache_size if self._cache_prep_stmts else 0
        self._stmt_cache = StmtCache(self, cache_size)
        
        # Get socket FD after connection is fully established
        self._socket_fd = self.get_socket()
        
        # Select platform-specific wait implementation BEFORE calling async methods
        loop = asyncio.get_event_loop()
        supports_add_reader = False
        if hasattr(loop, 'add_reader'):
            # Test if add_reader actually works (Windows ProactorEventLoop has it but raises NotImplementedError)
            try:
                def dummy_callback():
                    pass
                loop.add_reader(self._socket_fd, dummy_callback)
                loop.remove_reader(self._socket_fd)
                supports_add_reader = True
            except (NotImplementedError, AttributeError):
                supports_add_reader = False
        
        if supports_add_reader:
            # Unix/Linux: Use efficient add_reader/remove_reader with persistent registration
            self._loop = loop
            self._read_event = asyncio.Event()
            self._write_event = asyncio.Event()
            
            # Register callbacks once at connection time
            self._loop.add_reader(self._socket_fd, self._on_socket_readable)
            self._loop.add_writer(self._socket_fd, self._on_socket_writable)
            self._reader_registered = True
            self._writer_registered = True
            
            self._wait_for_status = self._wait_for_status_selector
        else:
            # Windows: Use C-based polling
            self._wait_for_status = self._wait_for_status_c_poll
        
        await self.set_autocommit(self._autocommit)
    
    def _on_socket_readable(self):
        """Callback when socket becomes readable (registered once at connection time)."""
        self._read_event.set()
    
    def _on_socket_writable(self):
        """Callback when socket becomes writable (registered once at connection time)."""
        self._write_event.set()
    
    async def _wait_for_status_selector(self, wait_status: int) -> int:
        """
        Wait for socket events using persistent event loop registration (Unix/Linux).
        
        Callbacks are registered once at connection time and remain active.
        This avoids the overhead of repeatedly calling add_reader/remove_reader.
        """
        if wait_status == 0:
            return 0
        
        timeout = None
        if wait_status & MYSQL_WAIT_TIMEOUT:
            timeout = self.get_timeout_value()
            if timeout <= 0:
                timeout = None
        
        try:
            if wait_status & MYSQL_WAIT_READ:
                if not self._read_event.is_set():
                    await asyncio.wait_for(self._read_event.wait(), timeout=timeout)
                self._read_event.clear()
                return MYSQL_WAIT_READ
            elif wait_status & MYSQL_WAIT_WRITE:
                if not self._write_event.is_set():
                    await asyncio.wait_for(self._write_event.wait(), timeout=timeout)
                self._write_event.clear()
                return MYSQL_WAIT_WRITE
            else:
                # No read or write requested
                return wait_status
            
        except asyncio.TimeoutError:
            return MYSQL_WAIT_TIMEOUT
    
    async def _wait_for_status_c_poll(self, wait_status: int) -> int:
        """
        Wait for socket events using C-based polling (Windows ProactorEventLoop).
        
        For SSL connections, the C extension bypasses select() and returns immediately,
        letting the SSL layer (SCHANNEL) handle buffering and I/O directly.
        For non-SSL, uses select() to check socket readiness.
        """
        if wait_status == 0:
            return 0
        
        timeout = self.get_timeout_value() if (wait_status & MYSQL_WAIT_TIMEOUT) else None
        start_time = asyncio.get_event_loop().time() if timeout is not None else None
        
        while True:
            # C extension checks socket readiness
            # For SSL on Windows, this returns immediately (no select() call)
            # For non-SSL, this uses select() with 0 timeout
            ready_status = self._check_socket_ready(wait_status)
            
            if ready_status != 0:
                return ready_status
            
            # Check for timeout
            if timeout is not None:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed >= timeout:
                    return MYSQL_WAIT_TIMEOUT
            
            # Yield to event loop
            # Use 0 sleep since C extension now handles SSL efficiently
            await asyncio.sleep(0)

    def cursor(self, cursorclass=None, **kwargs):
        """
        Returns a new async cursor object for the current connection.

        If no cursorclass was specified, a cursor with default AsyncCursor class will be created.

        Optional keyword parameters:

        - **buffered** (default: ``True``) - If disabled, the result will be unbuffered, which means before executing another statement with the same connection, the entire result set must be fetched.
        - **dictionary** (default: ``False``) - Return fetch values as dictionary when enabled.
        - **named_tuple** (default: ``False``) - Return fetch values as named tuple.
        - **cursor_type** (default: ``CURSOR.NONE``) - If cursor_type is set to CURSOR.READ_ONLY, a cursor is opened for the statement invoked with cursors execute() method.
        - **binary** (default: ``False``) - Always execute statement in MariaDB client/server binary protocol.
        """
        self._check_closed()
        if cursorclass is None:
            from mariadb_c.async_cursors import AsyncCursor
            cursorclass = AsyncCursor
        cursor = cursorclass(self, **kwargs)
        return cursor
    
    async def close(self) -> None:
        """Close the async connection"""
        if self._pooled_connection:
            await self._pooled_connection.return_to_pool()
        else:
            if self._stmt_cache is not None:
                self._stmt_cache.clear(close=True)
                self._stmt_cache = None
            # Unregister event loop callbacks before closing
            if self._read_event and self._loop and self._socket_fd is not None:
                try:
                    self._loop.remove_reader(self._socket_fd)
                    self._loop.remove_writer(self._socket_fd)
                except (OSError, ValueError):
                    # Socket already closed or invalid - ignore
                    pass
            
            # Use async close to avoid blocking event loop
            wait_status = self._async_close_start()
            
            # If it's an integer, we need to wait
            while isinstance(wait_status, int) and wait_status != 0:
                actual_status = await self._wait_for_status(wait_status)
                wait_status = self._async_close_cont(actual_status)

    async def __aenter__(self):
        """Async context manager entry"""
        self._check_closed()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()

    async def select_db(self, new_db: str):
        """
        Gets the default database for the current connection (async).

        The default database can also be obtained or changed by database
        attribute.
        """
        self._check_closed()
        cursor = self.cursor()
        try:
            await cursor.execute("USE `%s`" % str(new_db))
        finally:
            await cursor.close()

    def get_server_version(self):
        """
        Returns a tuple representing the version of the connected server in
        the following format: (MAJOR_VERSION, MINOR_VERSION, PATCH_VERSION)
        """

        return self.server_version_info

    @property
    def tls_peer_cert_info(self):
        """Get peer certificate information."""

        if version.Version(mariadbapi_version) <\
               version.Version('3.4.2'):
            return None
        self._check_closed()
        if self._tls:
            return self._mariadb_get_info(INFO.TLS_PEER_CERT_INFO)
        return None

    @property
    def database(self):
        """Get the current database of the connection."""

        self._check_closed()
        return self._mariadb_get_info(INFO.SCHEMA)

    @database.setter
    def database(self, schema):
        """Set default database."""
        self._check_closed()
        # Note: For async, use select_db() method instead
        # This setter uses synchronous approach for compatibility
        cursor = self.cursor()
        import asyncio
        asyncio.create_task(cursor.execute("USE %s" % str(schema)))
        asyncio.create_task(cursor.close())

    @property
    def user(self):
        """
        Returns the username for the current connection or empty
        string if it can't be determined, e.g., when using socket
        authentication.
        """
        self._check_closed()

        return self._mariadb_get_info(INFO.USER)

    @property
    def character_set(self):
        """
        Client character set.

        For MariaDB Connector/Python, it is always utf8mb4.
        """

        return _DEFAULT_CHARSET

    @property
    def client_capabilities(self):
        """Client capability flags."""

        self._check_closed()
        return self._mariadb_get_info(INFO.CLIENT_CAPABILITIES)

    @property
    def server_capabilities(self):
        """Server capability flags."""

        self._check_closed()
        return self._mariadb_get_info(INFO.SERVER_CAPABILITIES)

    @property
    def extended_server_capabilities(self):
        """
        Extended server capability flags (only for MariaDB
        database servers).
        """

        self._check_closed()
        return self._mariadb_get_info(INFO.EXTENDED_SERVER_CAPABILITIES)

    @property
    def server_port(self):
        """
        Database server TCP/IP port. This value will be 0 in case of an unix
        socket connection.
        """

        self._check_closed()
        if self.unix_socket:
            return 0
        return self._mariadb_get_info(INFO.PORT)

    @property
    def server_mariadb(self) -> bool:
        """
        Check if server is MariaDB
        
        Returns:
            True if server is MariaDB, False if MySQL
        """
        self._check_closed()
        # MARIADB_CONNECTION_SREVER_TYPE returns 1 for MariaDB, 0 for MySQL
        return self._mariadb_get_info(INFO.SERVER_TYPE) == "MariaDB"

    @property
    def unix_socket(self):
        """Unix socket name."""

        self._check_closed()
        return self._mariadb_get_info(INFO.UNIX_SOCKET)

    @property
    def server_name(self):
        """Name or IP address of database server."""

        self._check_closed()
        if self.unix_socket:
            return None
        return self._mariadb_get_info(INFO.HOST)

    @property
    def collation(self):
        """Client character set collation"""

        return _DEFAULT_COLLATION

    @property
    def server_info(self):
        """Server version in alphanumerical format (str)"""

        self._check_closed()
        return self._mariadb_get_info(INFO.SERVER_VERSION)

    @property
    def tls_cipher(self):
        """TLS cipher suite if a secure connection is used."""

        self._check_closed()
        if self._tls:
            return self._mariadb_get_info(INFO.SSL_CIPHER)
        return None

    @property
    def tls_version(self):
        """TLS protocol version if a secure connection is used."""

        self._check_closed()
        if self._tls:
            return self._mariadb_get_info(INFO.TLS_VERSION)
        return None

    @property
    def _tls_verify_status(self):
        """Returns the result of the peer certificate verification."""

        if version.Version(mariadbapi_version) <\
               version.Version('3.4.2'):
            return None

        self._check_closed()
        if self._tls:
            return self._mariadb_get_info(INFO.TLS_VERIFY_STATUS)
        return None

    @property
    def server_status(self):
        """
        Return server status flags
        """

        self._check_closed()
        return self._mariadb_get_info(INFO.SERVER_STATUS)

    @property
    def server_version(self):
        """
        Server version in numerical format.

        The form of the version number is
        VERSION_MAJOR * 10000 + VERSION_MINOR * 100 + VERSION_PATCH
        """

        self._check_closed()
        return self._mariadb_get_info(INFO.SERVER_VERSION_ID)

    @property
    def server_version_info(self):
        """
        Returns numeric version of connected database server in tuple format.
        """

        self._check_closed()
        version = self.server_version
        return (int(version / 10000),
                int((version % 10000) / 100),
                version % 100)

    @property
    def socket(self):
        """Returns the socket used for database connection"""

        fno = self._get_socket()
        if not self._socket:
            self._socket = socket.socket(fileno=fno)
        # in case of a possible reconnect, file descriptor has changed
        elif fno != self._socket.fileno():
            self._socket = socket.socket(fileno=fno)
        return self._socket

    # Aliases
    character_set_name = character_set

    @property
    def thread_id(self):
        """
        Alias for connection_id
        """

        self._check_closed()
        return self.connection_id

    async def ping(self):
        """
        Check if the connection to the server is alive (async)
        
        Raises:
            Error: If the connection is not alive
        """
        self._check_closed()
        
        # Start async ping
        wait_status = self._async_ping_start()
        
        # If it's an integer, we need to wait
        while isinstance(wait_status, int) and wait_status != 0:
            actual_status = await self._wait_for_status(wait_status)
            wait_status = self._async_ping_cont(actual_status)
        
        # wait_status is None when completed successfully
        return wait_status

    async def change_user(self, user, password, database=None):
        """
        Change the user and default database for the current connection
        
        Args:
            user: New username
            password: New password
            database: New default database (optional)
        """
        self._check_closed()
        
        # Validate required parameters - reject if both are None
        if user is None and password is None:
            raise TypeError("change_user() missing required argument: 'user' and 'password' cannot both be None")
        
        # Use async change_user to avoid blocking event loop
        if database is not None:
            wait_status = self._async_change_user_start(user, password, database)
        else:
            wait_status = self._async_change_user_start(user, password)
        
        # If it's an integer, we need to wait
        while isinstance(wait_status, int) and wait_status != 0:
            actual_status = await self._wait_for_status(wait_status)
            wait_status = self._async_change_user_cont(actual_status)
        
        # Update socket FD after change_user in case the connection was re-established
        self._socket_fd = self.get_socket()

    async def reconnect(self):
        """
        Reconnect to the server
        
        Note: MariaDB C library doesn't have mysql_reconnect_start/cont,
        so we use thread pool to avoid blocking the event loop.
        """
        # Run synchronous reconnect in thread pool
        loop = asyncio.get_event_loop()
        
        # Reset closed flag before reconnecting
        self.closed = False
        
        # Unregister old socket FD from event loop if using persistent registration
        if self._read_event and self._loop and self._socket_fd is not None:
            try:
                self._loop.remove_reader(self._socket_fd)
                self._loop.remove_writer(self._socket_fd)
            except (OSError, ValueError):
                # Socket already closed or invalid - ignore
                pass
        
        # Call the C library's mariadb_reconnect function
        await loop.run_in_executor(None, lambda: super(AsyncConnection, self).reconnect())
        
        # Update socket FD after reconnect since the connection socket has changed
        self._socket_fd = self.get_socket()
        
        # Re-register event loop callbacks with new socket FD
        if self._read_event and self._loop:
            self._loop.add_reader(self._socket_fd, self._on_socket_readable)
            self._loop.add_writer(self._socket_fd, self._on_socket_writable)

    async def reset(self):
        """
        Reset the connection
        """
        self._check_closed()
        
        # Use async reset to avoid blocking event loop
        wait_status = self._async_reset_start()
        
        # If it's an integer, we need to wait
        while isinstance(wait_status, int) and wait_status != 0:
            actual_status = await self._wait_for_status(wait_status)
            wait_status = self._async_reset_cont(actual_status)
