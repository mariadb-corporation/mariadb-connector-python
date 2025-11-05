#
# Copyright (C) 2020-2021 Georg Richter and MariaDB Corporation AB

# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Library General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.

# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Library General Public License for more details.

# You should have received a copy of the GNU Library General Public
# License along with this library; if not see <http://www.gnu.org/licenses>
# or write to the Free Software Foundation, Inc.,
# 51 Franklin St., Fifth Floor, Boston, MA 02110, USA
#

from abc import ABC, abstractmethod
from typing import Optional, Any, Type, List

from mariadb_shared.constants import STATUS, TPC_STATE
from mariadb_shared.xid import Xid

from .exceptions import (
    ProgrammingError, NotSupportedError, OperationalError,
    Error, Warning, InterfaceError, DatabaseError,
    InternalError, IntegrityError, DataError
)
from .impl.configuration import Configuration
from .impl.host_address import HostAddress
from .impl.string_utils import StringEscaper
from .impl.client.exception_factory import ExceptionFactory

_DEFAULT_CHARSET = "utf8mb4"
_DEFAULT_COLLATION = "utf8mb4_general_ci"
_MAX_TPC_XID_SIZE = 64


class BaseConnection(ABC):
    """
    Abstract base class for MariaDB Connector/Python Connection Objects

    Provides common functionality for both sync and async connections.
    Subclasses must implement abstract methods for sync or async behavior.
    """
    
    # DB-API 2.0 exception attributes
    Warning = Warning
    Error = Error
    InterfaceError = InterfaceError
    DatabaseError = DatabaseError
    DataError = DataError
    OperationalError = OperationalError
    IntegrityError = IntegrityError
    InternalError = InternalError
    ProgrammingError = ProgrammingError
    NotSupportedError = NotSupportedError

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        Initialize base connection attributes
        
        Subclasses must call this and then establish the actual connection.
        """
        self._closed = False
        self._exception_factory = ExceptionFactory()
        self._pooled_connection: 'PooledConnection' = None
        self._xid = None  # Current XA transaction ID
        self.tpc_state = TPC_STATE.NONE
        self._host = kwargs.get('host', 'localhost')
        self._port = kwargs.get('port', 3306)
        self._user = kwargs.get('user') or kwargs.get('username')
        self._database = kwargs.get('database') or kwargs.get('db')
        
        # Store all connection parameters
        self._connection_params = kwargs
        
        # Create configuration and host address
        self._configuration = Configuration.from_dict(kwargs)
        self._host_address = HostAddress(host=self._host, port=self._port)
        
        # Client will be set by subclass
        self._client: Union[SyncClient, AsyncClient] = None

    def _check_closed(self) -> None:
        """Check if connection is closed and raise exception if it is"""
        if self._closed:
            raise self._exception_factory.create_exception(
                "Invalid connection or not connected",
                sql_state='42000'
            )
    
    # Public properties for connection attributes
    @property
    def host(self) -> str:
        """Get connection host"""
        return self._host
    
    @property
    def port(self) -> int:
        """Get connection port"""
        return self._port
    
    @property
    def user(self) -> Optional[str]:
        """Get connection user"""
        return self._user

    @abstractmethod
    def cursor(self, cursor_class=None, **kwargs):
        """Returns a new cursor object for the current connection"""
        pass

    @abstractmethod
    def commit(self):
        """Commit the current transaction"""
        pass

    @abstractmethod
    def rollback(self):
        """Rollback the current transaction"""
        pass

    @abstractmethod
    def close(self):
        """Close the connection"""
        pass

    @abstractmethod
    def ping(self):
        """Check if the connection to the server is alive"""
        pass

    @abstractmethod
    def begin(self):
        """Start a new transaction"""
        pass

    @abstractmethod
    def kill(self, id: int):
        """Kill a database connection specified by the process id parameter"""
        pass

    @abstractmethod
    def reconnect(self):
        """Reconnect to the database server"""
        pass

    @abstractmethod
    def reset(self):
        """Reset the connection"""
        pass

    @abstractmethod
    def change_user(self, user: str, password: str, database: Optional[str] = None):
        """Change the user and database of the current connection"""
        pass


    # Common methods (non-async, work for both sync and async)
    def _set_pooled_connection(self, pooled_connection : 'PooledConnection'):
        """Set the PooledConnection wrapper for this connection (internal use only)"""
        self._pooled_connection : 'PooledConnection' = pooled_connection

    def escape_string(self, string: str) -> str:
        """Escape a string for use in SQL statements"""
        self._check_closed()
        no_backslash_escapes = (self._client.context.server_status & STATUS.NO_BACKSLASH_ESCAPES) > 0
        return StringEscaper.escape_string(string, no_backslash_escapes)

    def xid(self, format_id: int, transaction_id: str, branch_qualifier: str) -> Xid:
        return Xid(format_id, transaction_id, branch_qualifier)
        
    # Properties (common for both sync and async)
    @property
    def connection_id(self) -> int:
        """Get current connection_id"""
        if not self._closed and self._client:
            return self._client.context.connection_id
        return -1

    @property
    def database(self) -> Optional[str]:
        """Get current database name"""
        if self._client:
            context_db = self._client.context.database
            if context_db is not None:
                return context_db
        return self._database

    @property
    def autocommit(self) -> bool:
        """Get current autocommit status"""
        if self._client:
            return (self._client.context.server_status & STATUS.AUTOCOMMIT) > 0
        return False

    @property
    def server_status(self) -> int:
        """Get current server_status"""
        if self._client:
            return int(self._client.context.server_status)
        return 0

    @property
    def warnings(self) -> int:
        """Get the number of warnings from the last executed statement"""
        if self._client:
            return self._client.context.warning_count
        return 0

    @property
    def server_version(self) -> int:
        """Get server version as integer in format MMPPRR (major, minor, patch with 2 digits each)"""
        self._check_closed()
        version = self._client.context.version
        return version.major * 10000 + version.minor * 100 + version.patch

    @property
    def server_version_info(self) -> tuple:
        """Get server version as tuple (major, minor, patch)"""
        self._check_closed()
        version = self._client.context.version
        return (version.major, version.minor, version.patch)

    @property
    def server_version_info(self):
        """
        Returns numeric version of connected database server in tuple format.
        """
        self._check_closed()
        version = self._client.context.version
        return (version.major,
                version.minor,
                version.patch)

    def get_server_version(self):
        """
        Returns a tuple representing the version of the connected server in
        the following format: (MAJOR_VERSION, MINOR_VERSION, PATCH_VERSION)
        """
        return self.server_version_info

    @property
    def server_info(self) -> str:
        """Get server version string"""
        self._check_closed()
        return self._client.context.server_version

    @property
    def character_set(self) -> str:
        """Get current character set"""
        if self._client and self._client.context:
            return self._client.context.character_set or _DEFAULT_CHARSET
        return _DEFAULT_CHARSET

    @property
    def collation(self) -> str:
        """Get current collation"""
        if self._client and self._client.context:
            return self._client.context.collation or _DEFAULT_COLLATION
        return _DEFAULT_COLLATION

    @property
    def user(self) -> Optional[str]:
        """Get current user"""
        return self.user if hasattr(self, 'user') else None

    @property
    def tls_cipher(self) -> Optional[str]:
        """Get TLS cipher in use"""
        self._check_closed()
        if self._client:
            return self._client.get_ssl_cipher()
        return None

    @property
    def _tls(self) -> Optional[str]:
        """
        Get if using SSL connection
        
        Returns:
            True if SSL is active,
            False if not using SSL connection
        """
        self._check_closed()
        return self._client.get_ssl_version() != None

    @property
    def tls_version(self) -> Optional[str]:
        """Get TLS version in use"""
        self._check_closed()
        return self._client.get_ssl_version()

    @property
    def _tls_verify_status(self) -> Optional[int]:
        """Get TLS certificate verification status"""
        self._check_closed()
        return 1 if self._configuration.ssl_verify_cert else 0

    @property
    def tls_peer_cert_info(self) -> Optional[dict]:
        """Get peer certificate information for TLS connections"""
        self._check_closed()
        return self._client.get_peer_certificate()

    @property
    def _tls_verify_status(self) -> Optional[int]:
        """
        Get TLS certificate verification status
        
        Returns:
            None if SSL is not enabled,
            1 if SSL verification is enabled (check_hostname=True and verify_mode=CERT_REQUIRED),
            0 if SSL is enabled but verification is disabled
        """
        self._check_closed()
        if not self._tls:
            return None
        return 1 if self._configuration.ssl_verify_cert else 0



    @property
    def server_port(self) -> Optional[int]:
        """
        Database server TCP/IP port. This value will be 0 in case of an unix
        socket connection.
        """
        self._check_closed()
        return 0 if self._client.configuration.socket_path else self._client.get_host_address().port


    @property
    def unix_socket(self) -> Optional[str]:
        """Unix socket name."""

        self._check_closed()
        return self._client.configuration.socket_path

    @property
    def server_name(self) -> Optional[str]:
        """Name or IP address of database server."""

        self._check_closed()
        return None if self._client.configuration.socket_path else self._client.get_host_address().host


    @abstractmethod
    def tpc_begin(self, xid: Xid) -> None:
        """
        Parameter:
          xid: xid object which was created by .xid() method of connection
               class

        Begins a TPC transaction with the given transaction ID xid.

        This method should be called outside a transaction
        (i.e., nothing may have been executed since the last .commit()
        or .rollback()).
        Furthermore, it is an error to call .commit() or .rollback() within
        the TPC transaction. A ProgrammingError is raised if the application
        calls .commit() or .rollback() during an active TPC transaction.
        """
        pass
    
    @abstractmethod
    def tpc_prepare(self) -> None:
        """
        Performs the first phase of a transaction started with .tpc_begin().
        A ProgrammingError will be raised if this method was called outside
        a TPC transaction.

        After calling .tpc_prepare(), no statements can be executed until
        .tpc_commit() or .tpc_rollback() have been called.
        """
        pass


    @abstractmethod
    def tpc_commit(self, xid: Xid=None) -> None:
        """
        Optional parameter:

        - xid
          : xid object which was created by .xid() method of connection class.

        When called with no arguments, .tpc_commit() commits a TPC transaction
        previously prepared with .tpc_prepare().

        If .tpc_commit() is called prior to .tpc_prepare(), a single phase
        commit is performed. A transaction manager may choose to do this if
        only a single resource is participating in the global transaction.
        When called with a transaction ID xid, the database commits the given
        transaction. If an invalid transaction ID is provided,
        a ProgrammingError will be raised.
        This form should be called outside a transaction, and
        is intended for use in recovery.
        """
        pass

    
    @abstractmethod
    def tpc_rollback(self, xid: Xid=None) -> None:
        """
        Parameter:
           xid: xid object which was created by .xid() method of connection
                class

        Performs the first phase of a transaction started with .tpc_begin().
        A ProgrammingError will be raised if this method outside a TPC
        transaction.

        After calling .tpc_prepare(), no statements can be executed until
        .tpc_commit() or .tpc_rollback() have been called.
        """
        pass

    @abstractmethod
    def tpc_recover(self) -> list:
        """
        Returns a list of pending transaction IDs suitable for use with
        tpc_commit(xid) or .tpc_rollback(xid).
        """
        pass

