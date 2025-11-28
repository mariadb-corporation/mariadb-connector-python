# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Synchronous connection implementation

Provides a blocking API using the sync Client.
"""

from typing import Optional, Any
from mariadb_shared.constants import CAPABILITY
from mariadb_shared.sync_connection_common import SyncConnectionCommon
from .base_connection import BaseConnection

from .impl.client.sync_client import SyncClient


class SyncConnection(BaseConnection['SyncClient'], SyncConnectionCommon):
    """
    Synchronous MariaDB connection
    
    Provides a blocking API using the sync Client directly.
    All I/O operations are synchronous and blocking.
    
    Type Parameters:
        _client: SyncClient
    """
    
    # =========================================================================
    # Initialization and Context Managers
    # =========================================================================
    
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        Initialize synchronous connection and connect immediately
        
        Args:
            **kwargs: Connection parameters (host, user, password, database, etc.)
            
        Raises:
            OperationalError: If connection fails
        """
        super().__init__(*args, **kwargs)
        # Create sync client
        self._client = SyncClient(self._configuration)
        # Connect immediately for sync connections
        try:
            self._client.connect()
        except Exception as e:
            self._closed = True
            if hasattr(e, 'errno') and hasattr(e, 'sqlstate'):
                raise
            raise self._exception_factory.create_connection_exception(f"Connection failed: {e}", cause=e)
        # Set autocommit if configured
        if self._configuration.autocommit:
            self.set_autocommit(True)
    
    def __enter__(self) -> 'SyncConnection':
        """Context manager entry"""
        return self
    
    # =========================================================================
    # Core Connection Methods
    # =========================================================================

    def cursor(self, **kwargs) -> 'SyncCursor':
        """
        Create a new cursor for executing queries
        
        Args:
            **kwargs: Additional cursor parameters:
                - named_tuple: Return rows as named tuples
                - dictionary: Return rows as dictionaries
                - buffered: Buffer all results immediately
            
        Returns:
            SyncCursor object
            
        Raises:
            ProgrammingError: If connection is closed
        """
        # Import here to avoid circular dependency
        from .sync_cursor import SyncCursor
        return SyncCursor(self, **kwargs)
    
    def close(self) -> None:
        """
        Close the database connection
        
        If this is a pooled connection, returns it to the pool.
        Otherwise, closes the underlying socket connection.
        
        Raises:
            OperationalError: If close fails
        """
        if self._pooled_connection:
            self._pooled_connection.return_to_pool()
            return

        if not self._closed:
            try:
                self._client.close()
            except Exception as e:
                pass
            finally:
                self._closed = True
    
    def ping(self) -> None:
        """
        Check if the connection to the server is alive
        
        Sends a ping command to verify the connection is active.
        
        Raises:
            OperationalError: If ping fails or connection is dead
        """
        self._check_closed()
        try:
            self._client.ping()
        except Exception as e:  
            raise self._exception_factory.create_exception(
                f"Ping failed: {e}",
                errno=2013,
                sql_state='HY000'
            )
    
    def reconnect(self) -> None:
        """
        Reconnect to the database server
        
        Closes the current connection and establishes a new one
        with the same parameters.
        
        Raises:
            OperationalError: If reconnection fails
        """
        if not self._closed:
            self.close()
        
        self._closed = False
        try:
            self._client = SyncClient(self._configuration)
            self._client.connect()
        except Exception as e:
            self._closed = True
            raise self._exception_factory.create_exception(
                f"Reconnection failed: {e}",
                errno=2013,
                sql_state='08S01'
            )
    
    def reset(self) -> None:
        """
        Reset the connection state
        
        Clears session variables, temporary tables, and prepared statements
        without reconnecting.
        
        Raises:
            OperationalError: If reset fails
        """
        self._check_closed()
        try:
            from .impl.message.client.reset_connection_packet import ResetConnectionPacket
            self._client.execute(ResetConnectionPacket(), self._configuration)
        except Exception as e:
            raise self._exception_factory.create_exception(
                f"Reset failed: {e}",
                errno=2013,
                sql_state='HY000'
            )
    
    def change_user(self, user: Optional[str], password: Optional[str], database: Optional[str] = None) -> None:
        """
        Change the user and database of the current connection
        
        Args:
            user: New username (None = keep current)
            password: New password (None = keep current)
            database: New database (None = keep current)
            
        Raises:
            OperationalError: If change user fails
        """
        self._check_closed()
        try:
            self._client.change_user(user, password, database)
            if user is not None:
                self._user = user
            if database is not None:
                self._database = database
        except Exception as e:
            if hasattr(e, 'errno') and hasattr(e, 'sqlstate'):
                raise
            raise self._exception_factory.create_exception(
                f"Change user failed: {e}",
                errno=2013,
                sql_state='HY000'
            )
    
    # =========================================================================
    # Properties and Setters
    # =========================================================================
    
    @BaseConnection.database.setter
    def database(self, value: Optional[str]) -> None:
        """
        Set database name
        
        Args:
            value: Database name to select
        """
        self._check_closed()
        context_db = self._client.context.database
        if context_db != value:
            from .impl.message.client.change_db_packet import ChangeDbPacket
            self._client.execute(ChangeDbPacket(value), self._configuration)
        self._database = value
        if not self._client.context.has_capability(CAPABILITY.SESSION_TRACKING):
            self._client.context.database = value

    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    def select_db(self, new_db: str) -> None:
        """
        Change the default database
        
        This is a convenience method that sets the database property.
        
        Args:
            new_db: Database name to select
        """
        self.database = new_db

    @property
    def server_status(self) -> int:
        """
        Returns the server status.
        """
        return self._client.context.server_status

    @property
    def warnings(self) -> int:
        """
        Returns the last execution warnings count.
        """
        return self._client.context.warning_count
