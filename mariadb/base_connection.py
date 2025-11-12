# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Base connection class for MariaDB Connector/Python

Provides abstract base class with common functionality for both
synchronous and asynchronous connection implementations.
"""

from abc import ABC, abstractmethod
from typing import Optional, Any, Union, TypeVar, Generic, TYPE_CHECKING

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

if TYPE_CHECKING:
    from .impl.client.base_client import BaseClient

TClient = TypeVar('TClient', bound='BaseClient')


class BaseConnection(ABC, Generic[TClient]):
    """
    Abstract base class for MariaDB Connector/Python Connection Objects

    Provides common functionality for both sync and async connections.
    Subclasses must implement abstract methods for sync or async behavior.
    
    Type Parameters:
        TClient: The client type (SyncClient or AsyncClient)
    
    Organization:
    1. Class attributes (DB-API 2.0 exceptions)
    2. Initialization
    3. Core connection methods (abstract)
    4. Transaction methods (abstract)
    5. TPC/XA transaction methods (abstract)
    6. Utility methods
    7. Properties (connection info, server info, TLS info)
    """
    
    # =========================================================================
    # DB-API 2.0 Exception Attributes
    # =========================================================================
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

    # =========================================================================
    # Initialization
    # =========================================================================
    
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        Initialize base connection attributes
        
        Subclasses must call this and then establish the actual connection.
        
        Args:
            *args: Positional arguments (typically unused)
            **kwargs: Connection parameters (host, port, user, password, database, etc.)
        """
        self._closed = False
        self._exception_factory = ExceptionFactory()
        self._pooled_connection: 'PooledConnection' = None
        self._xid = None  # Current XA transaction ID
        self.tpc_state = TPC_STATE.NONE
        
        # Store connection parameters
        self._host = kwargs.get('host', 'localhost')
        self._port = kwargs.get('port', 3306)
        self._user = kwargs.get('user') or kwargs.get('username')
        self._database = kwargs.get('database') or kwargs.get('db')
        self._connection_params = kwargs
        
        # Create configuration and host address
        self._configuration = Configuration.from_dict(kwargs)
        
        # Client will be set by subclass (SyncClient or AsyncClient)
        self._client: Optional[TClient] = None

    def _check_closed(self) -> None:
        """
        Check if connection is closed and raise exception if it is
        
        Raises:
            ProgrammingError: If connection is closed
        """
        if self._closed:
            raise self._exception_factory.create_exception(
                "Invalid connection or not connected",
                sql_state='42000'
            )

    # =========================================================================
    # Core Connection Methods (Abstract - must be implemented by subclasses)
    # =========================================================================
    
    @abstractmethod
    def cursor(self, cursor_class=None, **kwargs):
        """
        Create a new cursor object for executing queries
        
        Args:
            cursor_class: Optional custom cursor class
            **kwargs: Additional cursor parameters
            
        Returns:
            Cursor object
        """
        ...

    @abstractmethod
    def close(self):
        """
        Close the database connection
        
        After calling this method, the connection object should not be used anymore.
        """
        ...

    @abstractmethod
    def ping(self):
        """
        Check if the connection to the server is alive
        
        Sends a ping command to the server.
        
        Raises:
            OperationalError: If connection is not alive
        """
        ...

    @abstractmethod
    def reconnect(self):
        """
        Reconnect to the database server
        
        Closes the current connection and establishes a new one with the same parameters.
        """
        ...

    @abstractmethod
    def reset(self):
        """
        Reset the connection state
        
        Clears session variables, temporary tables, and prepared statements.
        """
        ...

    @abstractmethod
    def change_user(self, user: Optional[str], password: Optional[str], database: Optional[str] = None):
        """
        Change the user and database of the current connection
        
        Args:
            user: New username (None = keep current)
            password: New password (None = keep current)
            database: New database (None = keep current)
            
        Raises:
            OperationalError: If change user fails
        """
        ...

    def select_db(self, database: str) -> None:
        """
        Change the default database for the current connection
        
        This is a convenience method that sets the database property.
        
        Args:
            database: Database name to select
        """
        self.database = database

    # =========================================================================
    # Transaction Methods (Abstract - must be implemented by subclasses)
    # =========================================================================
    
    @abstractmethod
    def commit(self):
        """
        Commit the current transaction
        
        Makes all changes made since the last commit/rollback permanent.
        """
        ...

    @abstractmethod
    def rollback(self):
        """
        Rollback the current transaction
        
        Discards all changes made since the last commit/rollback.
        """
        ...

    @abstractmethod
    def begin(self):
        """
        Start a new transaction explicitly
        
        Note: Most operations start a transaction implicitly if autocommit is off.
        """
        ...

    # =========================================================================
    # TPC/XA Transaction Methods (Abstract - for distributed transactions)
    # =========================================================================
    
    def xid(self, format_id: int, transaction_id: str, branch_qualifier: str) -> Xid:
        """
        Create a transaction ID object for two-phase commit
        
        Args:
            format_id: Format identifier (0 will be converted to 1)
            transaction_id: Global transaction identifier
            branch_qualifier: Branch qualifier
            
        Returns:
            Xid object suitable for TPC methods
            
        Raises:
            ProgrammingError: If parameters are invalid
        """
        return Xid(format_id, transaction_id, branch_qualifier)
    
    @abstractmethod
    def tpc_begin(self, xid: Xid) -> None:
        """
        Begin a TPC transaction with the given transaction ID
        
        This method should be called outside a transaction.
        
        Args:
            xid: Transaction ID object created by xid() method
            
        Raises:
            ProgrammingError: If called within an active transaction
        """
        ...
    
    @abstractmethod
    def tpc_prepare(self) -> None:
        """
        Perform the first phase of a two-phase commit transaction
        
        After calling this, no statements can be executed until
        tpc_commit() or tpc_rollback() is called.
        
        Raises:
            ProgrammingError: If called outside a TPC transaction
        """
        ...

    @abstractmethod
    def tpc_commit(self, xid: Optional[Xid] = None) -> None:
        """
        Commit a TPC transaction
        
        When called with no arguments, commits a TPC transaction previously
        prepared with tpc_prepare().
        
        If called prior to tpc_prepare(), performs a single-phase commit.
        
        When called with a transaction ID, commits the given transaction
        (used for recovery).
        
        Args:
            xid: Optional transaction ID for recovery
            
        Raises:
            ProgrammingError: If transaction state is invalid
        """
        ...
    
    @abstractmethod
    def tpc_rollback(self, xid: Optional[Xid] = None) -> None:
        """
        Rollback a TPC transaction
        
        Args:
            xid: Optional transaction ID for recovery
            
        Raises:
            ProgrammingError: If called outside a TPC transaction
        """
        ...

    @abstractmethod
    def tpc_recover(self) -> list:
        """
        Return a list of pending transaction IDs
        
        Returns:
            List of transaction IDs suitable for tpc_commit() or tpc_rollback()
        """
        ...

    # =========================================================================
    # Administrative Methods (Abstract)
    # =========================================================================
    
    @abstractmethod
    def kill(self, connection_id: int):
        """
        Kill a database connection
        
        Args:
            connection_id: Connection ID to kill
            
        Raises:
            OperationalError: If kill fails
        """
        ...

    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    def _set_pooled_connection(self, pooled_connection: 'PooledConnection') -> None:
        """
        Set the PooledConnection wrapper (internal use only)
        
        Args:
            pooled_connection: PooledConnection wrapper object
        """
        self._pooled_connection = pooled_connection

    def escape_string(self, string: str) -> str:
        """
        Escape a string for use in SQL statements
        
        Args:
            string: String to escape
            
        Returns:
            Escaped string safe for SQL queries
        """
        self._check_closed()
        no_backslash_escapes = (self._client.context.server_status & STATUS.NO_BACKSLASH_ESCAPES) > 0
        return StringEscaper.escape_string(string, no_backslash_escapes)

    def get_server_version(self) -> tuple:
        """
        Get server version as tuple
        
        Returns:
            Tuple of (major, minor, patch)
        """
        return self.server_version_info

    # =========================================================================
    # Connection Information Properties
    # =========================================================================
    
    @property
    def connection_id(self) -> int:
        """
        Get current connection thread ID
        
        Returns:
            Connection ID, or -1 if not connected
        """
        if not self._closed and self._client:
            return self._client.context.connection_id
        return -1
    
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
        """Get connection username"""
        return self._user

    @property
    def database(self) -> Optional[str]:
        """
        Get current database name
        
        Returns:
            Current database name, or None if no database selected
        """
        if self._client:
            context_db = self._client.context.database
            if context_db is not None:
                return context_db
        return self._database

    @property
    def unix_socket(self) -> Optional[str]:
        """
        Get Unix socket path
        
        Returns:
            Unix socket path, or None if using TCP/IP
        """
        self._check_closed()
        return self._client.configuration.socket_path

    # =========================================================================
    # Server Information Properties
    # =========================================================================
    
    @property
    def server_info(self) -> str:
        """
        Get server version string
        
        Returns:
            Server version string (e.g., "10.11.2-MariaDB")
        """
        self._check_closed()
        return self._client.context.server_version

    @property
    def server_name(self) -> Optional[str]:
        """
        Get server hostname or IP address
        
        Returns:
            Server hostname/IP, or None if using Unix socket
        """
        self._check_closed()
        return None if self._client.configuration.socket_path else self._client.get_host_address().host

    @property
    def server_port(self) -> int:
        """
        Get server TCP/IP port
        
        Returns:
            Port number, or 0 if using Unix socket
        """
        self._check_closed()
        return 0 if self._client.configuration.socket_path else self._client.get_host_address().port

    @property
    def server_mariadb(self) -> bool:
        """
        Get server type
        
        Returns:
            true if server is MariaDB, false otherwise
        """
        self._check_closed()
        return self._client.context.is_mariadb_server()


    @property
    def server_version(self) -> int:
        """
        Get server version as integer
        
        Returns:
            Version in format MMPPRR (major*10000 + minor*100 + patch)
            Example: 101102 for version 10.11.2
        """
        self._check_closed()
        version = self._client.context.version
        return version.major * 10000 + version.minor * 100 + version.patch


    @property
    def server_version_info(self) -> tuple:
        """
        Get server version as tuple
        
        Returns:
            Tuple of (major, minor, patch)
        """
        self._check_closed()
        version = self._client.context.version
        return (version.major, version.minor, version.patch)

    @property
    def server_status(self) -> int:
        """
        Get current server status flags
        
        Returns:
            Server status flags as integer
        """
        if self._client:
            return int(self._client.context.server_status)
        return 0

    @property
    def warnings(self) -> int:
        """
        Get number of warnings from last executed statement
        
        Returns:
            Warning count
        """
        if self._client:
            return self._client.context.warning_count
        return 0

    # =========================================================================
    # Character Set and Collation Properties
    # =========================================================================
    
    @property
    def character_set(self) -> str:
        """
        Get current character set
        
        Returns:
            Character set name (e.g., "utf8mb4")
        """
        if self._client and self._client.context:
            return self._client.context.get_charset() or _DEFAULT_CHARSET
        return _DEFAULT_CHARSET

    @property
    def collation(self) -> str:
        """
        Get current collation
        
        Returns:
            Collation name (e.g., "utf8mb4_general_ci")
        """
        if self._client and self._client.context:
            return self._client.context.get_collation() or _DEFAULT_COLLATION
        return _DEFAULT_COLLATION

    # =========================================================================
    # Transaction State Properties
    # =========================================================================
    
    @property
    def autocommit(self) -> bool:
        """
        Get current autocommit status
        
        Returns:
            True if autocommit is enabled, False otherwise
        """
        if self._client:
            return (self._client.context.server_status & STATUS.AUTOCOMMIT) > 0
        return False

    # =========================================================================
    # TLS/SSL Properties
    # =========================================================================
    
    @property
    def _tls(self) -> bool:
        """
        Check if using TLS/SSL connection
        
        Returns:
            True if TLS is active, False otherwise
        """
        self._check_closed()
        return self._client.get_ssl_version() is not None

    @property
    def tls_version(self) -> Optional[str]:
        """
        Get TLS protocol version
        
        Returns:
            TLS version string (e.g., "TLSv1.3"), or None if not using TLS
        """
        self._check_closed()
        return self._client.get_ssl_version()

    @property
    def tls_cipher(self) -> Optional[str]:
        """
        Get TLS cipher suite in use
        
        Returns:
            Cipher suite name, or None if not using TLS
        """
        self._check_closed()
        if self._client:
            return self._client.get_ssl_cipher()
        return None

    @property
    def _tls_verify_status(self) -> Optional[int]:
        """
        Get TLS certificate verification status
        
        Returns:
            None if TLS not enabled,
            1 if verification is enabled,
            0 if TLS enabled but verification disabled
        """
        self._check_closed()
        if not self._tls:
            return None
        return 1 if self._configuration.ssl_verify_cert else 0

    @property
    def tls_peer_cert_info(self) -> Optional[dict]:
        """
        Get peer certificate information for TLS connections
        
        Returns:
            Dictionary with certificate info, or None if not using TLS
        """
        self._check_closed()
        return self._client.get_peer_certificate()
