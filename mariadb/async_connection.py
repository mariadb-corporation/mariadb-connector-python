# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Asynchronous connection implementation

Provides a native async API directly using the async Client.
"""

from typing import Optional, Any, TYPE_CHECKING

from mariadb_shared.constants import CAPABILITY
from mariadb_shared.async_connection_common import AsyncConnectionCommon
from .base_connection import BaseConnection

from .impl.client.async_client import AsyncClient


class AsyncConnection(BaseConnection['AsyncClient'], AsyncConnectionCommon):
    """
    Asynchronous MariaDB connection
    
    Provides a native async API using the async Client directly.
    All I/O operations are async and use await.
    
    Type Parameters:
        _client: AsyncClient
    
    Example:
        async def main():
            conn = await mariadb.asyncConnect(user='root', database='test')
            cursor = conn.cursor()
            await cursor.execute("SELECT * FROM users")
            results = await cursor.fetchall()
            await conn.close()
    """
    
    # =========================================================================
    # Initialization and Context Managers
    # =========================================================================
    
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        Initialize asynchronous connection (does not connect)
        
        Use AsyncConnection.connect() or asyncConnect() to connect.
        
        Args:
            **kwargs: Connection parameters (host, user, password, database, etc.)
        """
        super().__init__(*args, **kwargs)
        # Create async client
        self._client = AsyncClient(self._configuration)
    
    @classmethod
    async def connect(cls, *args: Any, **kwargs: Any) -> 'AsyncConnection':
        """
        Create and connect an async connection
        
        This is the recommended way to create async connections.
        
        Args:
            **kwargs: Connection parameters
            
        Returns:
            Connected AsyncConnection instance
            
        Raises:
            OperationalError: If connection fails
        """
        instance = cls(*args, **kwargs)
        try:
            await instance._client.connect()
        except Exception as e:
            instance._closed = True
            if hasattr(e, 'errno') and hasattr(e, 'sqlstate'):
                raise
            raise instance._exception_factory.create_connection_exception(f"Connection failed: {e}", cause=e)
        return instance

    # =========================================================================
    # Core Connection Methods
    # =========================================================================
    
    def cursor(self, cursor_class=None, **kwargs) -> 'AsyncCursor':
        """
        Create a new async cursor for executing queries
        
        Args:
            **kwargs: Additional cursor parameters:
                - named_tuple: Return rows as named tuples
                - dictionary: Return rows as dictionaries
                - buffered: Buffer all results immediately
            
        Returns:
            AsyncCursor object
            
        Raises:
            ProgrammingError: If connection is closed
        """
        # Import here to avoid circular dependency
        from .async_cursor import AsyncCursor
        return AsyncCursor(self, **kwargs)
    
    async def close(self) -> None:
        """
        Close the database connection asynchronously
        
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
                await self._client.close()
            except Exception as e:
                pass
            finally:
                self._closed = True
    
    async def ping(self) -> None:
        """
        Check if the connection to the server is alive
        
        Sends a ping command to verify the connection is active.
        
        Raises:
            OperationalError: If ping fails or connection is dead
        """
        self._check_closed()
        try:
            await self._client.ping()
        except Exception as e:
            raise self._exception_factory.create_exception(
                f"Ping failed: {e}",
                errno=2013,
                sql_state='HY000'
            )
    
    async def reconnect(self) -> None:
        """
        Reconnect to the database server
        
        Closes the current connection and establishes a new one
        with the same parameters.
        
        Raises:
            OperationalError: If reconnection fails
        """
        if not self._closed:
            await self.close()
        
        self._closed = False
        try:
            self._client = AsyncClient(self._configuration)
            await self._client.connect()
        except Exception as e:
            self._closed = True
            raise self._exception_factory.create_exception(
                f"Reconnection failed: {e}",
                errno=2013,
                sql_state='08S01'
            )
    
    async def reset(self) -> None:
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
            await self._client.execute(ResetConnectionPacket(), self._configuration)
        except Exception as e:
            raise self._exception_factory.create_exception(
                f"Reset failed: {e}",
                errno=2013,
                sql_state='HY000'
            )
    
    async def change_user(self, user: Optional[str], password: Optional[str], database: Optional[str] = None) -> None:
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
            await self._client.change_user(user, password, database)
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
    # Utility Methods
    # =========================================================================
    
    async def select_db(self, database: str) -> None:
        """
        Change the default database
        
        Args:
            database: Database name to select
        """
        self._check_closed()
        context_db = self._client.context.database
        if context_db != database:
            from .impl.message.client.change_db_packet import ChangeDbPacket
            await self._client.execute(ChangeDbPacket(database), self._configuration)
        self._database = database
        if not self._client.context.has_capability(CAPABILITY.SESSION_TRACKING):
            self._client.context.database = database


    # Async context manager
    async def __aenter__(self) -> 'AsyncConnection':
        """Async context manager entry"""
        return self
    
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
