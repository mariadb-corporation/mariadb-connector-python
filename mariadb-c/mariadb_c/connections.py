# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from __future__ import annotations

import socket
from collections import OrderedDict
from typing import Optional, Any

# Import shared constants and exceptions to avoid circular dependencies
from mariadb_shared.constants import STATUS, TPC_STATE, INFO
from mariadb_shared.exceptions import (
    Error, ProgrammingError,
)
from mariadb_shared.sync_connection_common import SyncConnectionCommon

# Import mariadbapi_version from C extension
from mariadb_c._mariadb import mariadbapi_version
from packaging import version

from mariadb_shared.xid import Xid

_DEFAULT_CHARSET = "utf8mb4"
_DEFAULT_COLLATION = "utf8mb4_general_ci"
_MAX_TPC_XID_SIZE = 64


class StmtCacheEntry:
    """A cached prepared statement with template-capsule lifecycle tracking.

    The *capsule* holds the MYSQL_STMT* (with field metadata from prepare).
    When a cursor checks out the template, *capsule* becomes ``None`` and
    *checked_out* is ``True``.  When it returns the template, the capsule is
    restored.  On eviction the capsule is closed immediately if available,
    or deferred until the cursor returns it.
    """

    __slots__ = ("capsule", "checked_out", "in_cache")

    def __init__(self, capsule: Any) -> None:
        self.capsule: Any = capsule
        self.checked_out: bool = False
        self.in_cache: bool = True

    def checkout(self) -> Optional[Any]:
        """Take the template capsule (exclusive). Returns capsule or None."""
        if self.capsule is None or self.checked_out:
            return None
        capsule = self.capsule
        self.capsule = None
        self.checked_out = True
        return capsule

    def checkin(self, capsule: Any, connection: Any) -> None:
        """Return the template capsule after use."""
        self.checked_out = False
        if not self.in_cache:
            # Evicted while checked out — close now
            try:
                connection._close_stmt_capsule(capsule)
            except Exception:
                pass
        else:
            self.capsule = capsule

    def evict(self, connection: Any) -> None:
        """Mark as evicted.  Close capsule immediately if not checked out."""
        self.in_cache = False
        if self.capsule is not None:
            try:
                connection._close_stmt_capsule(self.capsule)
            except Exception:
                pass
            self.capsule = None


class StmtCache:
    """OrderedDict-based LRU cache for prepared statement templates.

    Keys are SQL strings; values are :class:`StmtCacheEntry` instances
    wrapping PyCapsule MYSQL_STMT* handles with field metadata intact.
    """

    __slots__ = ("_cache", "_maxsize", "_connection")

    def __init__(self, connection: Any, maxsize: int) -> None:
        self._cache: OrderedDict[str, StmtCacheEntry] = OrderedDict()
        self._maxsize: int = maxsize
        self._connection: Any = connection

    def get(self, sql: str) -> Optional[StmtCacheEntry]:
        """Return the entry for *sql* if the template is available, or None."""
        entry = self._cache.get(sql)
        if entry is None or entry.capsule is None:
            return None
        self._cache.move_to_end(sql)
        return entry

    def put(self, sql: str, capsule: Any) -> None:
        """Store *capsule* under *sql*, evicting the LRU entry if over capacity."""
        if self._maxsize <= 0:
            try:
                self._connection._close_stmt_capsule(capsule)
            except Exception:
                pass
            return
        if sql in self._cache:
            old = self._cache.pop(sql)
            old.evict(self._connection)
        entry = StmtCacheEntry(capsule)
        self._cache[sql] = entry
        while len(self._cache) > self._maxsize:
            _, evicted = self._cache.popitem(last=False)
            evicted.evict(self._connection)

    def clear(self, close: bool = True) -> None:
        """Discard all cached statements, optionally closing each on the server."""
        if close:
            for entry in self._cache.values():
                entry.evict(self._connection)
        self._cache.clear()

    def __len__(self) -> int:
        return len(self._cache)


# Import the C connection base class
from mariadb_c._mariadb import connection as CConnection

class Connection(CConnection, SyncConnectionCommon):
    """
    MariaDB Connector/Python Connection Object

    Handles the connection to a MariaDB or MySQL database server.
    It encapsulates a database session.

    Connections are created using the method mariadb_c.connect()
    """

    def _check_closed(self):
        if self._closed:
            raise ProgrammingError("Invalid connection or "
                                           "not connected")

    def __init__(self, *args, **kwargs):
        """
        Establishes a connection to a database server and returns a connection
        object.
        """
        # Pre-initialize _stmt_cache before super().__init__() so that any
        # attribute access during C-level init (e.g. autocommit setter) never
        # raises AttributeError.
        self._stmt_cache: Optional[StmtCache] = None

        self._socket = None
        self._used = 0
        self._last_executed_statement = None
        self._socket = None
        self.__last_used = 0
        self.tpc_state = TPC_STATE.NONE
        self._xid = None
        self._pooled_connection = None  # PooledConnection wrapper for pooled connections
        self._active_streaming_result = None  # Python-level tracking for unbuffered cursors
        self._active_async_cursor = None

        autocommit = kwargs.pop("autocommit", False)
        kwargs.pop("reconnect", None)
        converter = kwargs.pop("converter", None)
        self._binary = bool(kwargs.pop("binary", False))
        # Remove debug parameter that C extension doesn't support
        kwargs.pop("debug", None)
        cache_prep_stmts: bool = bool(kwargs.pop("cache_prep_stmts", True))
        prep_stmt_cache_size: int = int(kwargs.pop("prep_stmt_cache_size", 100))

        # if host contains a connection string or multiple hosts,
        # we need to check if it's supported by Connector/C
        if "host" in kwargs:
            host = kwargs.get("host")
            if version.Version(mariadbapi_version) <\
               version.Version('3.3.0') and ',' in host:
                raise ProgrammingError("Host failover list requires "
                                               "MariaDB Connector/C 3.3.0 "
                                               "or newer")

        # Initialize using parent C extension class
        super().__init__(*args, **kwargs)

        # Set converter on C extension's _converter field
        if converter is not None:
            self._converter = converter

        cache_size: int = prep_stmt_cache_size if cache_prep_stmts else 0
        self._stmt_cache = StmtCache(self, cache_size)

        self.autocommit = autocommit

    def cursor(self, cursorclass=None, **kwargs):
        """
        Returns a new cursor object for the current connection.

        If no cursorclass was specified, a cursor with default mariadb_c.Cursor class will be created.

        Optional keyword parameters:

        - **buffered** (default: ``True``) - If disabled, the result will be unbuffered, which means before executing another statement with the same connection, the entire result set must be fetched. Please note that the default was False for MariaDB Connector/Python versions < 1.1.0.
        - **dictionary** (default: ``False``) - Return fetch values as dictionary when enabled.
        - **named_tuple** (default: ``False``) - Return fetch values as named tuple. This feature exists for compatibility reasons and should be avoided due to possible inconsistency.
        - **cursor_type** (default: ``CURSOR.NONE``) - If cursor_type is set to CURSOR.READ_ONLY, a cursor is opened for the statement invoked with cursors execute() method.
        - **binary** (default: ``False``) - Always execute statement in MariaDB client/server binary protocol.

        In versions prior to 1.1.0 results were unbuffered by default, which means before executing another statement with the same connection, the entire result set must be fetched.

        fetch* methods of the cursor class by default return result set values as a tuple, unless dictionary or named_tuple was specified. The latter one exists for compatibility reasons and should be avoided due to possible inconsistency in case two or more fields in a result set have the same name.

        If cursor_type is set to CURSOR.READ_ONLY, a cursor is opened for the statement invoked with cursors execute() method.
        """
        self._check_closed()
        if cursorclass is None:
            cursorclass = _DefaultCursor
        cursor = cursorclass(self, **kwargs)
        return cursor
    
    def close(self) -> None:
        if self._pooled_connection:
            self._pooled_connection.return_to_pool()
        else:
            if self._stmt_cache is not None:
                self._stmt_cache.clear(close=True)
                self._stmt_cache = None
            super().close()

    def __enter__(self):
        self._check_closed()
        "Returns a copy of the connection."

        return self

    def select_db(self, new_db: str):
        """
        Gets the default database for the current connection.

        The default database can also be obtained or changed by database
        attribute.
        """

        self._check_closed()
        self.database = new_db

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
        with self.cursor() as cursor:
            cursor.execute("USE %s" % str(schema))

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

    def ping(self):
        """
        Check if the connection to the server is alive
        
        Sends a ping command to the server.

        Raises:
            OperationalError: If connection is not alive
        """
        self._check_closed()
        return self._sync_ping()

    @property
    def open(self):
        """
        Returns true if the connection is alive.

        A ping command will be sent to the server for this purpose,
        which means this function might fail if there are still
        non-processed pending result sets.

        for pymysql compatibility
        """

        self._check_closed()
        try:
            self.ping()
        except Error:
            return False
        return True

    # Aliases
    character_set_name = character_set

    @property
    def thread_id(self):
        """
        Alias for connection_id
        """

        self._check_closed()
        return self.connection_id


def _lazy_import_cursor():
    from .cursors import Cursor
    return Cursor

_DefaultCursor = _lazy_import_cursor()
