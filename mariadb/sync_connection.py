# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Synchronous connection implementation

Provides a blocking API using the sync Client.
"""

from typing import Optional, Any, Type, List, TYPE_CHECKING
from mariadb_shared.constants import STATUS, TPC_STATE
from mariadb_shared.xid import Xid

from .base_connection import BaseConnection

from .impl.client.sync_client import SyncClient

from .exceptions import ProgrammingError, Error


class SyncConnection(BaseConnection['SyncClient']):
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
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """
        Context manager exit
        
        Automatically commits on success, rolls back on exception,
        and closes the connection.
        """
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()
        return False

    # =========================================================================
    # Core Connection Methods
    # =========================================================================

    def cursor(self, cursor_class=None, **kwargs) -> 'SyncCursor':
        """
        Create a new cursor for executing queries
        
        Args:
            cursor_class: Optional custom cursor class
            **kwargs: Additional cursor parameters:
                - named_tuple: Return rows as named tuples
                - dictionary: Return rows as dictionaries
                - buffered: Buffer all results immediately
            
        Returns:
            SyncCursor object
            
        Raises:
            ProgrammingError: If connection is closed
        """
        self._check_closed()       
        
        # Update configuration with cursor-specific options
        if cursor_class is None:
            # Import here to avoid circular dependency
            from .sync_cursor import SyncCursor
            return SyncCursor(self, **kwargs)
        else:
            return cursor_class(self, **kwargs)
    
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
    
    def kill(self, connection_id: int) -> None:
        """
        Kill a database connection
        
        Args:
            connection_id: Connection ID to kill
            
        Raises:
            OperationalError: If kill fails
        """
        self._check_closed()
        if not isinstance(connection_id, int):
            raise ProgrammingError("connection_id must be of type int.")        
        try:
            with self.cursor() as cursor:
                cursor.execute(f"KILL {connection_id}")
        except Exception as e:
            raise self._exception_factory.create_exception(
                f"Failed to kill connection {connection_id}: {e}",
                errno=2013,
                sql_state='HY000'
            )

    # =========================================================================
    # Transaction Methods
    # =========================================================================
    
    def commit(self) -> None:
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
            with self.cursor() as cursor:
                cursor.execute("COMMIT")
    
    def rollback(self) -> None:
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
            with self.cursor() as cursor:
                cursor.execute("ROLLBACK")
    
    
    def begin(self) -> None:
        """
        Start a new transaction explicitly
        
        Note: Transactions usually start implicitly when autocommit is off.
        """
        self._check_closed()
        with self.cursor() as cursor:
            cursor.execute("BEGIN")

    # =========================================================================
    # TPC/XA Transaction Methods
    # =========================================================================
    
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
        with self.cursor() as cursor:
            cursor.execute("XA BEGIN '%s','%s',%s" % (xid[1], xid[2], xid[0]))
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
        try:
            with self.cursor() as cursor:
                cursor.execute("XA END '%s','%s',%s" % (xid[1], xid[2], xid[0]))
        except Error:
            self._xid = None
            self.tpc_state = TPC_STATE.NONE
            raise

        try:
            with self.cursor() as cursor:
                cursor.execute("XA PREPARE '%s','%s',%s" % (xid[1], xid[2], xid[0]))
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

        if self.tpc_state == TPC_STATE.NONE:
            raise ProgrammingError("Transaction not started.")
        if xid is None and self.tpc_state != TPC_STATE.PREPARE:
            raise ProgrammingError("Transaction is not prepared.")

        if not xid:
            xid = self._xid
        if xid and not isinstance(xid, Xid):
            raise ProgrammingError("argument 1 must be xid "
                                           "not %s" % type(xid).__name__)

        if self.tpc_state < TPC_STATE.PREPARE:
            try:
                with self.cursor() as cursor:
                    cursor.execute("XA END '%s','%s',%s" % (xid[1], xid[2], xid[0]))
            except Error:
                self._xid = None
                self.tpc_state = TPC_STATE.NONE
                raise

        xa_command = "XA COMMIT '%s','%s',%s" % (xid[1], xid[2], xid[0])
        if self.tpc_state < TPC_STATE.PREPARE:
            xa_command = xa_command + " ONE PHASE"
        try:
            with self.cursor() as cursor:
                cursor.execute(xa_command)
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

        if not xid:
            xid = self._xid

        if xid and not isinstance(xid, Xid):
            raise ProgrammingError("argument 1 must be xid "
                                           "not %s" % type(xid).__name__)

        if self.tpc_state < TPC_STATE.PREPARE:
            try:
                with self.cursor() as cursor:
                    cursor.execute("XA END '%s','%s',%s" % (xid[1], xid[2], xid[0]))
            except Error:
                self._xid = None
                self.tpc_state = TPC_STATE.NONE
                raise

        try:
            with self.cursor() as cursor:
                cursor.execute("XA ROLLBACK '%s','%s',%s" % (xid[1], xid[2], xid[0]))
        except Error:
            self._xid = None
            self.tpc_state = TPC_STATE.NONE
            raise

        self.tpc_state = TPC_STATE.PREPARE

    def tpc_recover(self) -> List[tuple]:
        """
        Returns a list of pending transaction IDs suitable for use with
        tpc_commit(xid) or .tpc_rollback(xid).
        """
        self._check_closed()
        with self.cursor() as cursor:
            cursor.execute("XA RECOVER")
            return cursor.fetchall()
        
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
        Set autocommit status
        
        Args:
            value: True to enable autocommit, False to disable
        """
        self.set_autocommit(value)

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
    
    def set_autocommit(self, value: bool) -> None:
        """
        Set autocommit status
        
        Args:
            value: True to enable autocommit, False to disable
        """
        self._check_closed()
        current = (self._client.context.server_status & STATUS.AUTOCOMMIT) > 0
        if current != bool(value):
            with self.cursor() as cursor:
                cursor.execute(f"SET autocommit={1 if bool(value) else 0}")
    
    def show_warnings(self) -> Optional[List[tuple]]:
        """
        Get warnings from the last executed command
        
        Returns:
            List of warning tuples (level, code, message), or None if no warnings
        """
        self._check_closed()
        if self._client.context.warning_count == 0:
            return None
        with self.cursor() as cursor:
            cursor.execute("SHOW WARNINGS")
            return cursor.fetchall()


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