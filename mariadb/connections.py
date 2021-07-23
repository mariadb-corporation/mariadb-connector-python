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

import mariadb
import socket
import time

from mariadb.constants import STATUS
from mariadb.constants import TPC_STATE

_DEFAULT_CHARSET = "utf8mb4"
_DEFAULT_COLLATION = "utf8mb4_general_ci"
_MAX_TPC_XID_SIZE=64

class Connection(mariadb._mariadb.connection):
    """MariaDB connection class"""

    def __init__(self, *args, **kwargs):
        self._socket= None
        self.__in_use= 0
        self.__pool = None
        self.__last_used = 0
        self.tpc_state= TPC_STATE.NONE
        self._xid= None

        autocommit= kwargs.pop("autocommit", False)
        self._converter= kwargs.pop("converter", None)

        super().__init__(*args, **kwargs)
        self.autocommit= autocommit

    def cursor(self, **kwargs):
        cursor= mariadb.Cursor(self, **kwargs)
        return cursor

    def close(self):
        if self._Connection__pool:
            self._Connection__pool._close_connection(self)
        else:
            super().close()

    def __enter__(self):
        "Returns a copy of the connection."
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        "Closes connection."
        self.close()

    def commit(self):
        if self.tpc_state > TPC_STATE.NONE:
            raise mariadb.ProgrammingError("commit() is not allowed if a TPC transaction is active")
        self._execute_command("COMMIT")
        self._read_response()

    def rollback(self):
        if self.tpc_state > TPC_STATE.NONE:
            raise mariadb.ProgrammingError("rollback() is not allowed if a TPC transaction is active")
        self._execute_command("ROLLBACK")
        self._read_response()

    def kill(self, id):
        if not isinstance(id, int):
            raise mariadb.ProgrammingError("id must be of type int.")
        stmt= "KILL %s" % id
        self._execute_command(stmt)
        self._read_response()

    def get_server_version(self):
        return self.server_version_info

    class xid(tuple):
        """
        A transaction ID object suitable for passing to the .tpc_*()
        methods of this connection.
        """
        def __new__(self, format_id, transaction_id, branch_qualifier):
            if not isinstance(format_id, int):
                raise TypeError("argument 1 must be int, not %s", type(format_id).__name__)
            if not isinstance(transaction_id, str):
                raise TypeError("argument 2 must be str, not %s", type(transaction_id).__mane__)
            if not isinstance(branch_qualifier, str):
                raise TypeError("argument 3 must be str, not %s", type(transaction_id).__name__)
            if len(transaction_id) > _MAX_TPC_XID_SIZE:
                raise mariadb.ProgrammingError("Maximum length of transaction_id exceeded.")
            if len(branch_qualifier) > _MAX_TPC_XID_SIZE:
                raise mariadb.ProgrammingError("Maximum length of branch_qualifier exceeded.")
            if format_id == 0:
                format_id= 1
            return super().__new__(self, (format_id, transaction_id, branch_qualifier))

    def tpc_begin(self, xid):
        """
        Parameter:
        xid: xid object which was created by .xid() method of 
             connection class

        Begins a TPC transaction with the given transaction ID xid.

        This method should be called outside of a transaction
        (i.e. nothing may have executed since the last .commit()
        or .rollback()).
        Furthermore, it is an error to call .commit() or .rollback() within
        the TPC transaction. A ProgrammingError is raised, if the application
        calls .commit() or .rollback() during an active TPC transaction.
        """

        if type(xid).__name__ != "xid":
            raise TypeError("argument 1 must be xid not %s", type(xid).__name__)
        stmt= "XA BEGIN '%s','%s',%s" % (xid[1], xid[2], xid[0])
        try:
            self._execute_command(stmt)
            self._read_response()
        except:
            raise
        self.tpc_state= TPC_STATE.XID
        self._xid= xid

    def tpc_commit(self, xid=None):
        """
        Optional parameter:"
        xid: xid object which was created by .xid() method of connection class.

        When called with no arguments, .tpc_commit() commits a TPC transaction
        previously prepared with .tpc_prepare().

        If .tpc_commit() is called prior to .tpc_prepare(), a single phase commit
        is performed. A transaction manager may choose to do this if only a
        single resource is participating in the global transaction.
        When called with a transaction ID xid, the database commits the given
        transaction. If an invalid transaction ID is provided, a ProgrammingError
        will be raised. This form should be called outside of a transaction, and
        is intended for use in recovery."
        """

        if not xid:
            xid= self._xid

        if self.tpc_state == TPC_STATE.NONE:
            raise mariadb.ProgrammingError("Transaction not started.")
        if xid is None and self.tpc_state != TPC_STATE.PREPARE:
            raise mariadb.ProgrammingError("Transaction is not prepared.")
        if xid and type(xid).__name__ != "xid":
            raise TypeError("argument 1 must be xid not %s" % type(xid).__name__)

        if self.tpc_state < TPC_STATE.PREPARE:
            stmt= "XA END '%s','%s',%s" % (xid[1], xid[2], xid[0])
            self._execute_command(stmt)
            try:
                self._read_response()
            except:
                self._xid= None
                self.tpc_state= TPC_STATE.NONE
                raise

        stmt= "XA COMMIT '%s','%s',%s" % (xid[1], xid[2], xid[0])
        if self.tpc_state < TPC_STATE.PREPARE:
            stmt= stmt + " ONE PHASE"
        try:
            self._execute_command(stmt)
            self._read_response()
        except:
            self._xid= None
            self.tpc_state= TPC_STATE.NONE
            raise

        #cleanup
        self._xid= None
        self.tpc_state= TPC_STATE.NONE

    def tpc_prepare(self): 
        """
        Performs the first phase of a transaction started with .tpc_begin().
        A ProgrammingError will be raised if this method outside of a TPC
        transaction.

        After calling .tpc_prepare(), no statements can be executed until
        .tpc_commit() or .tpc_rollback() have been called.
        """
        if self.tpc_state == TPC_STATE.NONE:
            raise mariadb.ProgrammingError("Transaction not started.")
        if self.tpc_state == TPC_STATE.PREPARE:
            raise mariadb.ProgrammingError("Transaction is already in prepared state.")

        xid= self._xid
        stmt= "XA END '%s','%s',%s" % (xid[1], xid[2], xid[0])
        try:
            self._execute_command(stmt)
            self._read_response()
        except:
            self._xid= None
            self.tpc_state= TPC_STATE.NONE
            raise

        stmt= "XA PREPARE '%s','%s',%s" % (xid[1], xid[2], xid[0])
        try:
            self._execute_command(stmt)
            self._read_response()
        except:
            self._xid= None
            self.tpc_state= TPC_STATE.NONE
            raise

        self.tpc_state= TPC_STATE.PREPARE

    def tpc_rollback(self, xid=None):
        """
        Parameter:
           xid: xid object which was created by .xid() method of connection
                class

        Performs the first phase of a transaction started with .tpc_begin().
        A ProgrammingError will be raised if this method outside of a TPC
        transaction.

        After calling .tpc_prepare(), no statements can be executed until
        .tpc_commit() or .tpc_rollback() have been called.
        """
        if self.tpc_state == TPC_STATE.NONE:
            raise mariadb.ProgrammingError("Transaction not started.")
        if xid and type(xid).__name__ != "xid":
            raise TypeError("argument 1 must be xid not %s" % type(xid).__name__)

        if not xid:
            xid= self._xid

        if self.tpc_state < TPC_STATE.PREPARE:
            stmt= "XA END '%s','%s',%s" % (xid[1], xid[2], xid[0])
            self._execute_command(stmt)
            try:
                self._read_response()
            except:
                self._xid= None
                self.tpc_state= TPC_STATE.NONE
                raise

        stmt= "XA ROLLBACK '%s','%s',%s" % (xid[1], xid[2], xid[0])
        try:
            self._execute_command(stmt)
            self._read_response()
        except:
            self._xid= None
            self.tpc_state= TPC_STATE.NONE
            raise

        self.tpc_state= TPC_STATE.PREPARE

    def tpc_recover(self):
        cursor= self.cursor()
        cursor.execute("XA RECOVER")
        result= cursor.fetchall()
        del cursor
        return result

    @property
    def character_set(self):
        """Client character set."""
        return _DEFAULT_CHARSET

    @property
    def collation(self):
        """Client character set collation"""
        return _DEFAULT_COLLATION

    @property
    def server_status(self):
        """Returns server status flags."""
        return super()._server_status

    @property
    def server_version_info(self):
        version= self.server_version
        return (int(version / 10000), int((version % 10000) / 100), version % 100)

    @property
    def get_autocommit(self):
        return bool(self.server_status & STATUS.AUTOCOMMIT)

    @property
    def set_autocommit(self, mode):
        if bool(mode) == self.autocommit:
            return
        try:
            self._execute_command("SET AUTOCOMMIT=%s" % int(mode))
            self._read_response()
        except:
            raise

    @property
    def socket(self):
        """Returns the socket used for database connection"""

        fno= self.get_socket()
        if not self._socket:
            self._socket= socket.socket(fileno=fno)
        # in case of a possible reconnect, file descriptor has changed
        elif fno != self._socket.fileno():
            self._socket= socket.socket(fileno=fno)
        return self._socket
