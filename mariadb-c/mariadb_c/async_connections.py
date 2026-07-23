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
import os
import socket
from typing import Any, Callable, Tuple, cast

from .connections import StmtCache

# Import shared constants and exceptions to avoid circular dependencies
from mariadb_shared.constants import TPC_STATE, INFO
from mariadb_shared.exceptions import (
    ProgrammingError,
)
from mariadb_shared.async_connection_common import AsyncConnectionCommon
from mariadb_shared.validators import validate_bool

# Import mariadbapi_version from C extension
from mariadb_c._mariadb import mariadbapi_version
from packaging import version


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

    def _check_closed(self) -> None:
        if self._closed:
            raise ProgrammingError("Invalid connection or "
                                           "not connected")

    @property
    def is_closed(self) -> bool:
        """Whether the connection has been closed."""
        return self._closed

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        Initialize async connection (does not connect yet).
        Use AsyncConnection.connect() or asyncConnect() to connect.
        """
        # Pre-initialize _stmt_cache before super().__init__() to avoid AttributeError
        self._stmt_cache: StmtCache | None = None

        # Initialize Python-side attributes first (same order as sync)
        self._socket: socket.socket | None = None
        self._socket_fd: int | None = None
        self._used = 0
        self._last_executed_statement = None
        self.__last_used = 0
        self.tpc_state = TPC_STATE.NONE
        self._xid = None
        self._pooled_connection: Any = None
        self._active_async_cursor = None  # Python-level tracking for async cursors only
        
        # Persistent event loop state for efficient I/O waiting.
        # _waiter holds the Future for an in-flight wait (None when idle);
        # _reader_armed tracks whether the persistent reader is registered.
        self._loop: asyncio.AbstractEventLoop | None = None
        self._waiter: asyncio.Future | None = None
        self._reader_armed = False
        
        # Extract parameters that need special handling (use .pop() like sync)
        self._autocommit = validate_bool(kwargs.pop("autocommit", False), "autocommit")
        kwargs.pop("reconnect", None)
        self._converter_param = kwargs.pop("converter", None)
        self._binary = validate_bool(kwargs.pop("binary", False), "binary")
        # Remove debug parameter that C extension doesn't support
        kwargs.pop("debug", None)
        # Shared connection-level statement cache is opt-in (default off);
        # per-cursor single-statement reuse is the default.
        self._cache_prep_stmts: bool = validate_bool(kwargs.pop("cache_prep_stmts", False), "cache_prep_stmts")
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

        # Normalize boolean connection options to the same accepted values as the
        # pure-Python client before handing them to the C connect.
        for _bk in ("ssl", "ssl_verify_cert", "compress", "local_infile"):
            if _bk in kwargs and kwargs[_bk] is not None and not isinstance(kwargs[_bk], dict):
                kwargs[_bk] = validate_bool(kwargs[_bk], _bk)

        # Validate host parameter (same as sync)
        if "host" in kwargs:
            host = kwargs["host"]
            if version.Version(mariadbapi_version) < version.Version('3.3.0') and ',' in host:
                raise ProgrammingError("Host failover list requires MariaDB Connector/C 3.3.0 or newer")
        
        # Store args/kwargs for later connection
        self._args = args
        self._kwargs = kwargs
        
        # Initialize C struct fields without connecting (makes active_result_cursor available)
        CConnection._init_fields_only(self)
    
    @classmethod
    async def connect(cls, *args: Any, **kwargs: Any) -> Any:
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
    
    async def _connect(self) -> None:
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
                def dummy_callback() -> None:
                    pass
                loop.add_reader(self._socket_fd, dummy_callback)
                loop.remove_reader(self._socket_fd)
                supports_add_reader = True
            except (NotImplementedError, AttributeError):
                supports_add_reader = False
        
        if supports_add_reader:
            # Unix/Linux: drive non-blocking I/O off the selector.
            #
            # The reader is registered persistently and reused across queries.
            # It is armed lazily on the first read-wait.
            # when it fires with no pending wait, i.e. the peer closed it (EOF is
            # "readable"), it self-suspends so an idle connection cannot spin.
            # The next operation re-arms it.
            #
            # The writer is registered on demand only for the duration of a
            # write-wait: a connected socket is almost always writable, so a
            # persistent writer would fire every loop iteration and busy-spin.
            self._loop = loop
            self._wait_for_status = self._wait_for_status_selector
            
            # libmariadb leaves the socket in blocking mode after the synchronous connect/handshake.
            os.set_blocking(self._socket_fd, False)
        else:
            # Windows: Use C-based polling
            self._wait_for_status = self._wait_for_status_c_poll

        await self.set_autocommit(self._autocommit)

    def _io_ready(self, status: int) -> None:
        """Selector callback for socket readiness (status is READ or WRITE).

        Resolves the pending wait, if any. If there is no pending wait, the
        persistent reader has fired while idle (peer close / unexpected data);
        it self-suspends to avoid a busy spin and is re-armed by the next wait.
        """
        waiter = self._waiter
        if waiter is None:
            if status == MYSQL_WAIT_READ:
                self._disarm_reader()
            return
        if not waiter.done():
            waiter.set_result(status)

    def _disarm_reader(self) -> None:
        """Remove the persistent reader if armed (before an FD change or close)."""
        if self._reader_armed and self._loop and self._socket_fd is not None:
            try:
                self._loop.remove_reader(self._socket_fd)
            except (OSError, ValueError):
                pass
            self._reader_armed = False

    async def _drive(self, start: Callable[[], Any], cont: Callable[[int], Any]) -> Any:
        """Drive a libmariadb non-blocking start/cont pair to completion.

        Repeatedly waits for the requested socket readiness and feeds the
        actual status back into cont() until the operation finishes (cont
        returns 0 or None).
        """
        status = start()
        while isinstance(status, int) and status != 0:
            status = cont(await self._wait_for_status(status))
        return status

    async def _wait_for_status_selector(self, wait_status: int) -> int:
        """
        Wait for socket readiness using the asyncio selector (Unix/Linux).

        Uses a persistent self-suspending reader and an on-demand writer.
        The bare Future fast-path avoids asyncio.wait_for overhead
        when no socket timeout is configured.
        """
        if wait_status == 0:
            return 0

        if self._waiter is not None and not self._waiter.done():
            raise ProgrammingError(
                "Concurrent async operations on a single connection "
                "are not supported")

        timeout = None
        if wait_status & MYSQL_WAIT_TIMEOUT:
            timeout = self.get_timeout_value()
            if timeout <= 0:
                timeout = None

        loop = self._loop
        fd = self._socket_fd
        # Both are set during _connect, before any wait can run.
        if not (loop is not None and fd is not None):
            raise AssertionError
        writing = False

        if wait_status & MYSQL_WAIT_READ:
            if not self._reader_armed:
                loop.add_reader(fd, self._io_ready, MYSQL_WAIT_READ)
                self._reader_armed = True
        elif wait_status & MYSQL_WAIT_WRITE:
            # Suspend the reader while waiting to write so a spurious read-ready
            # cannot resolve this wait with the wrong status; it re-arms on the
            # next read-wait.
            self._disarm_reader()
            loop.add_writer(fd, self._io_ready, MYSQL_WAIT_WRITE)
            writing = True
        else:
            # No read or write requested
            return wait_status

        waiter = loop.create_future()
        self._waiter = waiter
        try:
            if timeout is not None:
                return cast(int, await asyncio.wait_for(waiter, timeout=timeout))
            return cast(int, await waiter)
        except asyncio.TimeoutError:
            return MYSQL_WAIT_TIMEOUT
        finally:
            # Only clear the slot if it is still ours: a concurrent close() may
            # have cancelled this waiter and installed its own (see close()).
            if self._waiter is waiter:
                self._waiter = None
            if writing:
                loop.remove_writer(fd)
    
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
                if not (start_time is not None):  # set together with timeout above
                    raise AssertionError
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed >= timeout:
                    return MYSQL_WAIT_TIMEOUT
            
            # Yield to event loop
            # Use 0 sleep since C extension now handles SSL efficiently
            await asyncio.sleep(0)

    def cursor(self, cursorclass: type | None = None, **kwargs: Any) -> Any:
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
                self._stmt_cache.clear()
                self._stmt_cache = None
            # Wake any coroutine still parked on the waiter so it raises
            # CancelledError instead of hanging once the reader is torn down.
            if self._waiter is not None and not self._waiter.done():
                self._waiter.cancel()
            self._disarm_reader()
            # Use async close to avoid blocking the event loop
            await self._drive(self._async_close_start, self._async_close_cont)

    async def __aenter__(self) -> "AsyncConnection":
        """Async context manager entry"""
        self._check_closed()
        return self
    
    async def __aexit__(self, exc_type: type | None, exc_val: Exception | None, exc_tb: Any | None) -> None:
        """Async context manager exit"""
        await self.close()

    async def select_db(self, new_db: str) -> None:
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

    def get_server_version(self) -> Tuple[int, int, int]:
        """
        Returns a tuple representing the version of the connected server in
        the following format: (MAJOR_VERSION, MINOR_VERSION, PATCH_VERSION)
        """

        return self.server_version_info

    @property
    def tls_peer_cert_info(self) -> Any | None:
        """Get peer certificate information."""

        if version.Version(mariadbapi_version) <\
               version.Version('3.4.2'):
            return None
        self._check_closed()
        if self._tls:
            return self._mariadb_get_info(INFO.TLS_PEER_CERT_INFO)
        return None

    @property
    def database(self) -> str:
        """Get the current database of the connection."""

        self._check_closed()
        return cast(str, self._mariadb_get_info(INFO.SCHEMA))

    @database.setter
    def database(self, schema: str) -> None:
        """Set default database.

        Property setters cannot be async, so this raises an error.
        Use ``await conn.select_db(schema)`` instead.
        """
        raise ProgrammingError(
            "Cannot set database synchronously on an async connection. "
            "Use 'await conn.select_db(schema)' instead."
        )

    @property
    def user(self) -> str:
        """
        Returns the username for the current connection or empty
        string if it can't be determined, e.g., when using socket
        authentication.
        """
        self._check_closed()

        return cast(str, self._mariadb_get_info(INFO.USER))

    @property
    def character_set(self) -> str:
        """
        Client character set.

        For MariaDB Connector/Python, it is always utf8mb4.
        """

        return _DEFAULT_CHARSET

    @property
    def client_capabilities(self) -> int:
        """Client capability flags."""

        self._check_closed()
        return cast(int, self._mariadb_get_info(INFO.CLIENT_CAPABILITIES))

    @property
    def server_capabilities(self) -> int:
        """Server capability flags."""

        self._check_closed()
        return cast(int, self._mariadb_get_info(INFO.SERVER_CAPABILITIES))

    @property
    def extended_server_capabilities(self) -> int:
        """
        Extended server capability flags (only for MariaDB
        database servers).
        """

        self._check_closed()
        return cast(int, self._mariadb_get_info(INFO.EXTENDED_SERVER_CAPABILITIES))

    @property
    def server_port(self) -> int:
        """
        Database server TCP/IP port. This value will be 0 in case of an unix
        socket connection.
        """

        self._check_closed()
        if self.unix_socket:
            return 0
        return cast(int, self._mariadb_get_info(INFO.PORT))

    @property
    def server_mariadb(self) -> bool:
        """
        Check if server is MariaDB
        
        Returns:
            True if server is MariaDB, False if MySQL
        """
        self._check_closed()
        # MARIADB_CONNECTION_SREVER_TYPE returns 1 for MariaDB, 0 for MySQL
        return bool(self._mariadb_get_info(INFO.SERVER_TYPE) == "MariaDB")

    @property
    def unix_socket(self) -> str | None:
        """Unix socket name."""

        self._check_closed()
        return cast(str | None, self._mariadb_get_info(INFO.UNIX_SOCKET))

    @property
    def server_name(self) -> str | None:
        """Name or IP address of database server."""

        self._check_closed()
        if self.unix_socket:
            return None
        return cast(str | None, self._mariadb_get_info(INFO.HOST))

    @property
    def collation(self) -> str:
        """Client character set collation"""

        return _DEFAULT_COLLATION

    @property
    def server_info(self) -> str:
        """Server version in alphanumerical format (str)"""

        self._check_closed()
        return cast(str, self._mariadb_get_info(INFO.SERVER_VERSION))

    @property
    def tls_cipher(self) -> str | None:
        """TLS cipher suite if a secure connection is used."""

        self._check_closed()
        if self._tls:
            return cast(str | None, self._mariadb_get_info(INFO.SSL_CIPHER))
        return None

    @property
    def tls_version(self) -> str | None:
        """TLS protocol version if a secure connection is used."""

        self._check_closed()
        if self._tls:
            return cast(str | None, self._mariadb_get_info(INFO.TLS_VERSION))
        return None

    @property
    def _tls_verify_status(self) -> Any | None:
        """Returns the result of the peer certificate verification."""

        if version.Version(mariadbapi_version) <\
               version.Version('3.4.2'):
            return None

        self._check_closed()
        if self._tls:
            return self._mariadb_get_info(INFO.TLS_VERIFY_STATUS)
        return None

    @property
    def server_status(self) -> int:
        """
        Return server status flags
        """

        self._check_closed()
        return cast(int, self._mariadb_get_info(INFO.SERVER_STATUS))

    @property
    def server_version(self) -> int:
        """
        Server version in numerical format.

        The form of the version number is
        VERSION_MAJOR * 10000 + VERSION_MINOR * 100 + VERSION_PATCH
        """

        self._check_closed()
        return cast(int, self._mariadb_get_info(INFO.SERVER_VERSION_ID))

    @property
    def server_version_info(self) -> Tuple[int, int, int]:
        """
        Returns numeric version of connected database server in tuple format.
        """

        self._check_closed()
        version = self.server_version
        return (int(version / 10000),
                int((version % 10000) / 100),
                version % 100)

    @property
    def socket(self) -> socket.socket:
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
    def thread_id(self) -> int:
        """
        Alias for connection_id
        """

        self._check_closed()
        return self.connection_id

    async def ping(self) -> Any:
        """
        Check if the connection to the server is alive (async)
        
        Raises:
            Error: If the connection is not alive
        """
        self._check_closed()
        return await self._drive(self._async_ping_start, self._async_ping_cont)

    async def change_user(self, user: str | None, password: str | None, database: str | None = None) -> None:
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
        
        # Use async change_user to avoid blocking the event loop
        args = (user, password, database) if database is not None \
            else (user, password)
        await self._drive(lambda: self._async_change_user_start(*args),
                          self._async_change_user_cont)

        # The socket FD may change if the connection was re-established; drop the
        # persistent reader (armed on the old FD) so the next wait re-arms it.
        self._disarm_reader()
        self._socket_fd = self.get_socket()

    async def reconnect(self) -> None:
        """
        Reconnect to the server
        
        Note: MariaDB C library doesn't have mysql_reconnect_start/cont,
        so we use thread pool to avoid blocking the event loop.
        """
        # Run synchronous reconnect in thread pool
        loop = asyncio.get_event_loop()
        
        # Reset closed flag before reconnecting
        self.closed = False
        
        # Unregister old socket FD from event loop before it is closed/reused
        self._disarm_reader()

        # Call the C library's mariadb_reconnect function
        await loop.run_in_executor(None, lambda: super(AsyncConnection, self).reconnect())

        # Update socket FD after reconnect since the connection socket has changed.
        # The reader re-arms lazily on the new FD at the next read-wait.
        self._socket_fd = self.get_socket()

    async def reset(self) -> None:
        """
        Reset the connection
        """
        self._check_closed()
        await self._drive(self._async_reset_start, self._async_reset_cont)

    async def dump_debug_info(self) -> None:
        """
        Send a COM_DEBUG command to the server (async)

        Instructs the server to write debug information to its error log.
        Requires the SUPER privilege.

        Raises:
            OperationalError: If the command fails (e.g. insufficient privileges)
        """
        self._check_closed()
        await self._drive(self._async_dump_debug_info_start,
                          self._async_dump_debug_info_cont)
