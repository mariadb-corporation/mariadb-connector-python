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

"""
Asynchronous connection implementation

Provides a native async API directly using the async Client.
"""

from typing import Optional, Any, Type, List
from mariadb_shared.constants import STATUS, TPC_STATE
from mariadb_shared.xid import Xid

from .base_connection import BaseConnection
from .impl.client.async_client import AsyncClient
from .impl.message.client.query_packet import QueryPacket
from .impl.message.client.ping_packet import PingPacket
from .exceptions import ProgrammingError, Error


class AsyncConnection(BaseConnection):
    """
    Asynchronous MariaDB connection
    
    Provides a native async API using the async Client directly.
    All I/O operations are async and use await.
    
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
        
        Use AsyncConnection.create() or asyncConnect() to create and connect.
        
        Args:
            **kwargs: Connection parameters (host, user, password, database, etc.)
        """
        super().__init__(*args, **kwargs)
        # Create async client
        self._client = AsyncClient(self._configuration, self._host_address)
    
    async def __aenter__(self) -> 'AsyncConnection':
        """Async context manager entry"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        """
        Async context manager exit
        
        Automatically closes the connection.
        """
        await self.close()
        return False

    @classmethod
    async def create(cls, *args: Any, **kwargs: Any) -> 'AsyncConnection':
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
        # Set autocommit if configured
        if instance._configuration.autocommit:
            await instance.set_autocommit(True)
        return instance

    # =========================================================================
    # Core Connection Methods
    # =========================================================================
    
    def cursor(self, cursor_class=None, **kwargs) -> 'AsyncCursor':
        """
        Create a new async cursor for executing queries
        
        Args:
            cursor_class: Optional custom cursor class
            **kwargs: Additional cursor parameters:
                - named_tuple: Return rows as named tuples
                - dictionary: Return rows as dictionaries
                - buffered: Buffer all results immediately
            
        Returns:
            AsyncCursor object
            
        Raises:
            ProgrammingError: If connection is closed
        """
        self._check_closed()
        
        # Import here to avoid circular dependency
        from .async_cursor import AsyncCursor
        
        # Update configuration with cursor-specific options
        if kwargs:
            from .impl.configuration import Configuration
            temp_config = Configuration.from_dict({**self._connection_params, **kwargs})
            original_config = self._client.configuration
            self._client.configuration = temp_config
            
            try:
                if cursor_class is None:
                    cursor = AsyncCursor(self, **kwargs)
                else:
                    cursor = cursor_class(self, **kwargs)
                    
                cursor._cursor_config = temp_config
                return cursor
            finally:
                self._client.configuration = original_config
        else:
            if cursor_class is None:
                return AsyncCursor(self)
            else:
                return cursor_class(self, **kwargs)
    
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
        
        self._check_closed()
        if not self._closed:
            try:
                await self._client.close()
            except Exception as e:
                raise self._exception_factory.create_exception(
                    f"Failed to close connection: {e}",
                    errno=2013,
                    sql_state='08003'
                )
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
            await self._client.execute(PingPacket(), self._configuration)
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
        try:
            if not self._closed:
                await self.close()
        except:
            pass
        
        self._closed = False
        try:
            self._client = AsyncClient(self._configuration, self._host_address)
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
    
    async def kill(self, connection_id: int) -> None:
        """
        Kill a database connection
        
        Args:
            connection_id: Connection ID to kill
            
        Raises:
            OperationalError: If kill fails
        """
        self._check_closed()
        try:
            await self._client.execute(QueryPacket(f"KILL {connection_id}"), self._configuration)
        except Exception as e:
            raise self._exception_factory.create_exception(
                f"Failed to kill connection {connection_id}: {e}",
                errno=2013,
                sql_state='HY000'
            )

    # =========================================================================
    # Transaction Methods
    # =========================================================================
    
    async def commit(self) -> None:
        """
        Commit the current transaction
        
        Makes all changes since the last commit/rollback permanent.
        
        Raises:
            ProgrammingError: If called during XA transaction
        """
        self._check_closed()
        if self._xid is not None:
            raise ProgrammingError("Cannot commit during XA transaction. Use tpc_commit() instead.")
        if (self._client.context.server_status & STATUS.IN_TRANS) > 0:
            await self._client.execute(QueryPacket("COMMIT"), self._configuration, True)
    
    async def rollback(self) -> None:
        """
        Rollback the current transaction
        
        Discards all changes since the last commit/rollback.
        
        Raises:
            ProgrammingError: If called during XA transaction
        """
        self._check_closed()
        if self._xid is not None:
            raise ProgrammingError("Cannot rollback during XA transaction. Use tpc_rollback() instead.")
        if (self._client.context.server_status & STATUS.IN_TRANS) > 0:
            await self._client.execute(QueryPacket("ROLLBACK"), self._configuration, True)
    
    async def begin(self) -> None:
        """
        Start a new transaction explicitly
        
        Note: Transactions usually start implicitly when autocommit is off.
        """
        self._check_closed()
        await self._client.execute(QueryPacket("BEGIN"), self._configuration)

    # =========================================================================
    # TPC/XA Transaction Methods
    # =========================================================================
    

    async def tpc_begin(self, xid: Xid) -> None:
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

        self._check_closed()
        if not isinstance(xid, Xid):
            raise ProgrammingError("argument 1 must be xid "
                                           "not %s", type(xid).__name__)
        xa_command = "XA BEGIN '%s','%s',%s" % (xid[1], xid[2], xid[0])
        await self._client.execute(QueryPacket(xa_command), self._configuration)
        self.tpc_state = TPC_STATE.XID
        self._xid = xid
    
    async def tpc_prepare(self) -> None:
        """
        Performs the first phase of a transaction started with .tpc_begin().
        A ProgrammingError will be raised if this method was called outside
        a TPC transaction.

        After calling .tpc_prepare(), no statements can be executed until
        .tpc_commit() or .tpc_rollback() have been called.
        """

        self._check_closed()
        if self.tpc_state == TPC_STATE.NONE:
            raise ProgrammingError("Transaction not started.")
        if self.tpc_state == TPC_STATE.PREPARE:
            raise ProgrammingError("Transaction is already in "
                                           "prepared state.")

        xid = self._xid
        xa_command = "XA END '%s','%s',%s" % (xid[1], xid[2], xid[0])
        try:
            await self._client.execute(QueryPacket(xa_command), self._configuration)
        except Error:
            self._xid = None
            self.tpc_state = TPC_STATE.NONE
            raise

        xa_command = "XA PREPARE '%s','%s',%s" % (xid[1], xid[2], xid[0])
        try:
            await self._client.execute(QueryPacket(xa_command), self._configuration)
        except Error:
            self._xid = None
            self.tpc_state = TPC_STATE.NONE
            raise

        self.tpc_state = TPC_STATE.PREPARE


    async def tpc_commit(self, xid: Xid=None) -> None:
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

        self._check_closed()
        if not xid:
            xid = self._xid

        if self.tpc_state == TPC_STATE.NONE:
            raise ProgrammingError("Transaction not started.")
        if xid is None and self.tpc_state != TPC_STATE.PREPARE:
            raise ProgrammingError("Transaction is not prepared.")
        if xid and not isinstance(xid, Xid):
            raise ProgrammingError("argument 1 must be xid "
                                           "not %s" % type(xid).__name__)

        if self.tpc_state < TPC_STATE.PREPARE:
            xa_command = "XA END '%s','%s',%s" % (xid[1], xid[2], xid[0])
            try:
                await self._client.execute(QueryPacket(xa_command), self._configuration)
            except Error:
                self._xid = None
                self.tpc_state = TPC_STATE.NONE
                raise

        xa_command = "XA COMMIT '%s','%s',%s" % (xid[1], xid[2], xid[0])
        if self.tpc_state < TPC_STATE.PREPARE:
            xa_command = xa_command + " ONE PHASE"
        try:
            await self._client.execute(QueryPacket(xa_command), self._configuration)
        except Error:
            self._xid = None
            self.tpc_state = TPC_STATE.NONE
            raise

        # cleanup
        self._xid = None
        self.tpc_state = TPC_STATE.NONE

    
    async def tpc_rollback(self, xid: Xid=None) -> None:
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

        self._check_closed()
        if self.tpc_state == TPC_STATE.NONE:
            raise ProgrammingError("Transaction not started.")
        if xid and not isinstance(xid, Xid):
            raise ProgrammingError("argument 1 must be xid "
                                           "not %s" % type(xid).__name__)

        if not xid:
            xid = self._xid

        if self.tpc_state < TPC_STATE.PREPARE:
            xa_command = "XA END '%s','%s',%s" % (xid[1], xid[2], xid[0])
            try:
                await self._client.execute(QueryPacket(xa_command), self._configuration)
            except Error:
                self._xid = None
                self.tpc_state = TPC_STATE.NONE
                raise

        xa_command = "XA ROLLBACK '%s','%s',%s" % (xid[1], xid[2], xid[0])
        try:
            await self._client.execute(QueryPacket(xa_command), self._configuration)
        except Error:
            self._xid = None
            self.tpc_state = TPC_STATE.NONE
            raise

        self.tpc_state = TPC_STATE.PREPARE

    async def tpc_recover(self) -> list:
        """
        Returns a list of pending transaction IDs suitable for use with
        tpc_commit(xid) or .tpc_rollback(xid).
        """

        self._check_closed()
        cursor = self.cursor()
        await cursor.execute("XA RECOVER")
        result = await cursor.fetchall()
        del cursor
        return result


    
    # =========================================================================
    # Properties and Setters
    # =========================================================================
    
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
    
    @database.setter
    def database(self, value: Optional[str]) -> None:
        """
        Set database name - not supported for async connections
        
        Use await connection.select_db(database) instead.
        
        Raises:
            NotImplementedError: Always (use select_db() instead)
        """
        raise NotImplementedError("Use await connection.select_db(database) for async connections")

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
    
    @autocommit.setter
    def autocommit(self, value: bool) -> None:
        """
        Set autocommit status - not supported for async connections
        
        Use await connection.set_autocommit(value) instead.
        
        Raises:
            NotImplementedError: Always (use set_autocommit() instead)
        """
        raise NotImplementedError("Use await connection.set_autocommit(value) for async connections")

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
    
    async def set_autocommit(self, value: bool) -> None:
        """
        Set autocommit status
        
        Args:
            value: True to enable autocommit, False to disable
        """
        self._check_closed()
        current = (self._client.context.server_status & STATUS.AUTOCOMMIT) > 0
        if current != bool(value):
            await self._client.execute(QueryPacket(f"SET autocommit={1 if bool(value) else 0}"), self._configuration)
    
    async def show_warnings(self) -> Optional[List[tuple]]:
        """Shows error, warning and note messages from last executed command"""
        self._check_closed()
        from .async_cursor import AsyncCursor
        cursor = AsyncCursor(self)
        try:
            await cursor.execute("SHOW WARNINGS")
            return await cursor.fetchall()
        finally:
            await cursor.close()
    
    # Async context manager
    async def __aenter__(self) -> 'AsyncConnection':
        """Async context manager entry"""
        return self
    
    async def __aexit__(self, exc_type: Optional[type], exc_val: Optional[Exception], exc_tb: Optional[Any]) -> bool:
        """Async context manager exit"""
        if exc_type:
            await self.rollback()
        else:
            await self.commit()
        await self.close()
        return False



    async def show_warnings(self) -> Optional[List[tuple]]:
        """
        Get warnings from the last executed command
        
        Returns:
            List of warning tuples (level, code, message), or None if no warnings
        """
        self._check_closed()
        from .async_cursor import AsyncCursor
        cursor = AsyncCursor(self)
        try:
            await cursor.execute("SHOW WARNINGS")
            return await cursor.fetchall()
        finally:
            await cursor.close()
