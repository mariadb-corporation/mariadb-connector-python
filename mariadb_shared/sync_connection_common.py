# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Provides common logic that can be shared between mariadb (pure Python) and mariadb_c (C extension)
connection implementations.
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from .sync_cursor_common import SyncCursorCommon
from .constants import STATUS, TPC_STATE
from .xid import Xid
from .exceptions import ProgrammingError, Error

class SyncConnectionCommon(ABC):

    @abstractmethod
    def _check_closed(self) -> None:
        """
        Check if connection is closed and raise exception if it is
        
        Raises:
            ProgrammingError: If connection is closed
        """
        ...

    @abstractmethod
    def cursor(self, cursor_class=None, **kwargs) -> SyncCursorCommon:
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
    def close(self) -> None:
        """
        Close the database connection
        
        After calling this method, the connection object should not be used anymore.
        """
        ...

    @property
    @abstractmethod
    def server_status(self) -> int:
        """
        Returns the server status.
        """
        ...
        
    @abstractmethod
    def ping(self) -> None:
        """
        Check if the connection to the server is alive
        
        Sends a ping command to the server.
        
        Raises:
            OperationalError: If connection is not alive
        """
        ...

    @abstractmethod
    def reconnect(self) -> None:
        """
        Reconnect to the database server
        
        Closes the current connection and establishes a new one with the same parameters.
        """
        ...

    @abstractmethod
    def reset(self) -> None:
        """
        Reset the connection state
        
        Clears session variables, temporary tables, and prepared statements.
        """
        ...

    @abstractmethod
    def change_user(self, user: Optional[str], password: Optional[str], database: Optional[str] = None) -> None:
        """
        Change the user and database of the current connection
        
        Args:
            user: New user name
            password: New password
            database: New database name
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

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Context manager exit
        
        Automatically closes the connection.
        """
        self.close()

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
        with self.cursor() as cursor:
            cursor.execute(f"KILL {connection_id}")

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
        if (self.server_status & STATUS.IN_TRANS) > 0:
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
        if (self.server_status & STATUS.IN_TRANS) > 0:
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

    @property
    def autocommit(self) -> bool:
        """
        Toggles autocommit mode on or off for the current database connection.

        Autocommit mode only affects operations on transactional table types.
        Be aware that rollback() will not work if autocommit mode was switched
        on.

        By default, autocommit mode is set to False.
        """

        self._check_closed()
        return bool(self.server_status & STATUS.AUTOCOMMIT)

    @autocommit.setter
    def autocommit(self, value: bool) -> None:
        """
        Set autocommit status
        
        Args:
            value: True to enable autocommit, False to disable
        """
        self.set_autocommit(value)

    def set_autocommit(self, value: bool) -> None:
        """
        Set autocommit status
        
        Args:
            value: True to enable autocommit, False to disable
        """
        self._check_closed()
        current = (self.server_status & STATUS.AUTOCOMMIT) > 0
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
        if not self.warnings:
            return None
        with self.cursor() as cursor:
            cursor.execute("SHOW WARNINGS")
            return cursor.fetchall()

    @property
    def open(self) -> bool:
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
            
    # =========================================================================
    # XA Methods
    # =========================================================================

    """
    This class contains the validation and state management logic
    for XA transactions that is identical between the pure Python
    and C extension implementations.
    """
    
    def xid(self, format_id: int, transaction_id: str, branch_qualifier: str) -> Xid:
        return Xid(format_id, transaction_id, branch_qualifier)

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

        with self.cursor() as cursor:
            try:
                if self.tpc_state < TPC_STATE.PREPARE:
                    cursor.execute("XA END '%s','%s',%s" % (xid[1], xid[2], xid[0]))
                if self.tpc_state < TPC_STATE.PREPARE:
                    cursor.execute("XA COMMIT '%s','%s',%s ONE PHASE" % (xid[1], xid[2], xid[0]))
                else:
                    cursor.execute("XA COMMIT '%s','%s',%s" % (xid[1], xid[2], xid[0]))
            finally:
                self._xid = None
                self.tpc_state = TPC_STATE.NONE

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
        with self.cursor() as cursor:
            try:
                cursor.execute("XA END '%s','%s',%s" % (xid[1], xid[2], xid[0]))
                cursor.execute("XA PREPARE '%s','%s',%s" % (xid[1], xid[2], xid[0]))
            except Error:
                self._xid = None
                self.tpc_state = TPC_STATE.NONE
                raise
        self.tpc_state = TPC_STATE.PREPARE

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
        with self.cursor() as cursor:
            try:
                if self.tpc_state < TPC_STATE.PREPARE:
                    cursor.execute("XA END '%s','%s',%s" % (xid[1], xid[2], xid[0]))
                cursor.execute("XA ROLLBACK '%s','%s',%s" % (xid[1], xid[2], xid[0]))
            except Error:
                self._xid = None
                self.tpc_state = TPC_STATE.NONE
                raise
        self._xid = None
        self.tpc_state = TPC_STATE.NONE

    def tpc_recover(self) -> List[tuple]:
        """
        Returns a list of pending transaction IDs suitable for use with
        tpc_commit(xid) or .tpc_rollback(xid).
        """

        self._check_closed()
        with self.cursor() as cursor:
            cursor.execute("XA RECOVER")
            result = cursor.fetchall()
            return result
