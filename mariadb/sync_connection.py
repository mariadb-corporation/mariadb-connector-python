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
Synchronous connection implementation

Provides a blocking API using the sync Client.
"""

from typing import Optional, Any, Type, List
from mariadb_shared.constants import STATUS, TPC_STATE
from mariadb_shared.xid import Xid

from .base_connection import BaseConnection
from .impl.client.sync_client import SyncClient
from .impl.message.client.query_packet import QueryPacket
from .impl.message.client.ping_packet import PingPacket
from .exceptions import ProgrammingError, Error


class SyncConnection(BaseConnection):
    """
    Synchronous MariaDB connection
    
    Provides a blocking API using the sync Client directly.
    All I/O operations are synchronous and blocking.
    """
    
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        Initialize synchronous connection
        
        Args:
            **kwargs: Connection parameters (host, user, password, database, etc.)
        """
        super().__init__(*args, **kwargs)
        # Create sync client
        self._client = SyncClient(self._configuration, self._host_address)
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
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()
        return False

    def cursor(self, cursor_class=None, **kwargs):
        """
        Returns a new sync cursor object for the current connection
        
        Args:
            cursor_class: Optional custom cursor class
            **kwargs: Additional cursor parameters (named_tuple, dictionary, etc.)
            
        Returns:
            SyncCursor object
        """
        self._check_closed()
        
        # Import here to avoid circular dependency
        from .sync_cursor import SyncCursor
        
        # Update configuration with cursor-specific options
        if kwargs:
            from .impl.configuration import Configuration
            temp_config = Configuration.from_dict({**self._connection_params, **kwargs})
            original_config = self._client.configuration
            self._client.configuration = temp_config
            
            try:
                if cursor_class is None:
                    cursor = SyncCursor(self, **kwargs)
                else:
                    cursor = cursor_class(self, **kwargs)
                    
                cursor._cursor_config = temp_config
                return cursor
            finally:
                self._client.configuration = original_config
        else:
            if cursor_class is None:
                return SyncCursor(self)
            else:
                return cursor_class(self, **kwargs)
    
    def commit(self) -> None:
        """Commit the current transaction"""
        self._check_closed()
        if self._xid is not None:
            raise ProgrammingError("Cannot commit during XA transaction. Use tpc_commit() instead.")
        if (self._client.context.server_status & STATUS.IN_TRANS) > 0:
            self._client.execute(QueryPacket("COMMIT"), self._configuration, True)
    
    def rollback(self) -> None:
        """Rollback the current transaction"""
        self._check_closed()
        if self._xid is not None:
            raise ProgrammingError("Cannot rollback during XA transaction. Use tpc_rollback() instead.")
        if (self._client.context.server_status & STATUS.IN_TRANS) > 0:
            self._client.execute(QueryPacket("ROLLBACK"), self._configuration, True)
    
    def close(self) -> None:
        """Close the connection"""
        if self._pooled_connection:
            self._pooled_connection.return_to_pool()
            return

        self._check_closed()
        if not self._closed:
            try:
                self._client.close()
            except Exception as e:
                raise self._exception_factory.create_exception(
                    f"Failed to close connection: {e}",
                    errno=2013,
                    sql_state='08003'
                )
            finally:
                self._closed = True
    
    def ping(self) -> None:
        """Check if the connection to the server is alive"""
        self._check_closed()
        try:
            self._client.execute(PingPacket(), self._configuration)
        except Exception as e:
            raise self._exception_factory.create_exception(
                f"Ping failed: {e}",
                errno=2013,
                sql_state='HY000'
            )
    
    def begin(self) -> None:
        """Start a new transaction"""
        self._check_closed()
        self._client.execute(QueryPacket("BEGIN", self._configuration))
    
    def kill(self, id: int) -> None:
        """Kill a database connection specified by the process id parameter"""
        self._check_closed()
        try:
            self._client.execute(QueryPacket(f"KILL {id}"), self._configuration, True)
        except Exception as e:
            raise self._exception_factory.create_exception(
                f"Failed to kill connection {id}: {e}",
                errno=2013,
                sql_state='HY000'
            )
    
    def reconnect(self) -> None:
        """Reconnect to the database server"""
        try:
            if not self._closed:
                self.close()
        except:
            pass
        
        self._closed = False
        try:
            self._client = SyncClient(self._configuration, self._host_address)
            self._client.connect()
        except Exception as e:
            self._closed = True
            raise self._exception_factory.create_exception(
                f"Reconnection failed: {e}",
                errno=2013,
                sql_state='08S01'
            )
    
    def reset(self) -> None:
        """Reset the connection"""
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
    
    def change_user(self, user: str, password: str, database: Optional[str] = None) -> None:
        """Change the user and database of the current connection"""
        self._check_closed()
        try:
            self._client.change_user(user, password, database)
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
    
    @property
    def database(self) -> Optional[str]:
        """Get current database name"""
        if self._client:
            context_db = self._client.context.database
            if context_db is not None:
                return context_db
        return self._database
    
    @database.setter
    def database(self, value: Optional[str]) -> None:
        """Set database name"""
        self._check_closed()
        context_db = self._client.context.database
        if context_db != value:
            from .impl.message.client.change_db_packet import ChangeDbPacket
            self._client.execute(ChangeDbPacket(value), self._configuration)
        self._database = value
    
    @property
    def autocommit(self) -> bool:
        """Get current autocommit status"""
        if self._client:
            return (self._client.context.server_status & STATUS.AUTOCOMMIT) > 0
        return False
    
    @autocommit.setter
    def autocommit(self, value: bool) -> None:
        """Set autocommit status"""
        self.set_autocommit(value)
    
    def set_autocommit(self, value: bool) -> None:
        """Set autocommit status"""
        self._check_closed()
        current = (self._client.context.server_status & STATUS.AUTOCOMMIT) > 0
        if current != bool(value):
            self._client.execute(QueryPacket(f"SET autocommit={1 if bool(value) else 0}"), self._configuration)
    
    def show_warnings(self) -> Optional[List[tuple]]:
        """Shows error, warning and note messages from last executed command"""
        self._check_closed()
        from .sync_cursor import SyncCursor
        cursor = SyncCursor(self)
        try:
            cursor.execute(QueryPacket("SHOW WARNINGS"), self._configuration)
            return cursor.fetchall()
        finally:
            cursor.close()

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

        self._check_closed()
        if not isinstance(xid, Xid):
            raise ProgrammingError("argument 1 must be xid "
                                           "not %s", type(xid).__name__)
        xa_command = "XA BEGIN '%s','%s',%s" % (xid[1], xid[2], xid[0])
        self._client.execute(QueryPacket(xa_command), self._configuration)
        self.tpc_state = TPC_STATE.XID
        self._xid = xid
    
    def tpc_prepare(self) -> None:
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
            self._client.execute(QueryPacket(xa_command), self._configuration)
        except Error:
            self._xid = None
            self.tpc_state = TPC_STATE.NONE
            raise

        xa_command = "XA PREPARE '%s','%s',%s" % (xid[1], xid[2], xid[0])
        try:
            self._client.execute(QueryPacket(xa_command), self._configuration)
        except Error:
            self._xid = None
            self.tpc_state = TPC_STATE.NONE
            raise

        self.tpc_state = TPC_STATE.PREPARE


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
                self._client.execute(QueryPacket(xa_command), self._configuration)
            except Error:
                self._xid = None
                self.tpc_state = TPC_STATE.NONE
                raise

        xa_command = "XA COMMIT '%s','%s',%s" % (xid[1], xid[2], xid[0])
        if self.tpc_state < TPC_STATE.PREPARE:
            xa_command = xa_command + " ONE PHASE"
        try:
            self._client.execute(QueryPacket(xa_command), self._configuration)
        except Error:
            self._xid = None
            self.tpc_state = TPC_STATE.NONE
            raise

        # cleanup
        self._xid = None
        self.tpc_state = TPC_STATE.NONE

    
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
                self._client.execute(QueryPacket(xa_command), self._configuration)
            except Error:
                self._xid = None
                self.tpc_state = TPC_STATE.NONE
                raise

        xa_command = "XA ROLLBACK '%s','%s',%s" % (xid[1], xid[2], xid[0])
        try:
            self._client.execute(QueryPacket(xa_command), self._configuration)
        except Error:
            self._xid = None
            self.tpc_state = TPC_STATE.NONE
            raise

        self.tpc_state = TPC_STATE.PREPARE

    def tpc_recover(self) -> list:
        """
        Returns a list of pending transaction IDs suitable for use with
        tpc_commit(xid) or .tpc_rollback(xid).
        """

        self._check_closed()
        cursor = self.cursor()
        cursor.execute("XA RECOVER")
        result = cursor.fetchall()
        del cursor
        return result
