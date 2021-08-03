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
import mariadb.cursors

from mariadb.constants import STATUS, TPC_STATE, INFO

_DEFAULT_CHARSET = "utf8mb4"
_DEFAULT_COLLATION = "utf8mb4_general_ci"
_MAX_TPC_XID_SIZE=64

class Connection(mariadb._mariadb.connection):
    """
    MariaDB Connector/Python Connection Object

    Handles the connection to a MariaDB or MySQL database server.
    It encapsulates a database session.

    Connections are created using the method mariadb.connect()
    """

    def __init__(self, *args, **kwargs):
        """
        Establishes a connection to a database server and returns a connection
        object.
        """

        self._socket= None
        self.__in_use= 0
        self.__pool = None
        self.__last_used = 0
        self.tpc_state= TPC_STATE.NONE
        self._xid= None

        autocommit= kwargs.pop("autocommit", False)
        self._converter= kwargs.pop("converter", None)

        # compatibiity feature: if SSL is provided as a dictionary,
        # we will map it's content
        if "ssl" in kwargs and not isinstance(kwargs["ssl"], bool):
             ssl= kwargs.pop("ssl", None)
             for key in ["ca", "cert", "capath", "key", "cipher"]:
                 if key in ssl:
                     kwargs["ssl_%s" % key] = ssl[key]
             kwargs["ssl"]= True

        super().__init__(*args, **kwargs)
        self.autocommit= autocommit

    def cursor(self, cursorclass=mariadb.cursors.Cursor, **kwargs):
        """
        Returns a new cursor object for the current connection.

        If no cursorclass was specified, a cursor with default mariadb.Cursor class
        will be created.

        Optional parameters:

        - buffered= False
          By default the result will be unbuffered, which means before executing
          another statement with the same connection the entire result set must be fetched.
        - dictionary= False
          Return fetch values as dictionary.

        - named_tuple= False
          Return fetch values as named tuple. This feature exists for compatibility reasons
          and should be avoided due to possible inconsistency.

        - cursor_type= CURSOR_TYPE.NONE
          If cursor_type is set to CURSOR_TYPE.READ_ONLY, a cursor is opened for the
          statement invoked with cursors execute() method.

        - prepared= False
          When set to True cursor will remain in prepared state after the first execute()
          method was called. Further calls to execute() method will ignore the sql statement.

        - binary= False
          Always execute statements in MariaDB client/server binary protocol.

        By default the result will be unbuffered, which means before executing another 
        statement with the same connection the entire result set must be fetched.

        fetch* methods of the cursor class by default return result set values as a 
        tuple, unless named_tuple or dictionary was specified. The latter one exists 
        for compatibility reasons and should be avoided due to possible inconsistency
        in case two or more fields in a result set have the same name.

        If cursor_type is set to CURSOR_TYPE.READ_ONLY, a cursor is opened for
        the statement invoked with cursors execute() method.
        """

        cursor= cursorclass(self, **kwargs)
        if not isinstance(cursor, mariadb._mariadb.cursor):
            raise mariadb.ProgrammingError("%s is not an instance of mariadb.cursor" % cursor)
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
        """
        Commit any pending transaction to the database.
        """

        if self.tpc_state > TPC_STATE.NONE:
            raise mariadb.ProgrammingError("commit() is not allowed if a TPC transaction is active")
        self._execute_command("COMMIT")
        self._read_response()

    def rollback(self):
        """
        Causes the database to roll back to the start of any pending transaction

        Closing a connection without committing the changes first will cause an
        implicit rollback to be performed.
        Note that rollback() will not work as expected if autocommit mode was set to True
        or the storage engine does not support transactions."
        """

        if self.tpc_state > TPC_STATE.NONE:
            raise mariadb.ProgrammingError("rollback() is not allowed if a TPC transaction is active")
        self._execute_command("ROLLBACK")
        self._read_response()

    def kill(self, id):
        """
        This function is used to ask the server to kill a database connection
        specified by the processid parameter. 

        The connection id must be retrieved by SHOW PROCESSLIST sql command.
        """

        if not isinstance(id, int):
            raise mariadb.ProgrammingError("id must be of type int.")
        stmt= "KILL %s" % id
        self._execute_command(stmt)
        self._read_response()

    def begin(self):
        """
        Start a new transaction which can be committed by .commit() method,
        or cancelled by .rollback() method.
        """
        self._execute_command("BEGIN")
        self._read_response()

    def select_db(self, new_db):
        """
        Gets the default database for the current connection.

        The default database can also be obtained or changed by database attribute.
        """

        self.database= new_db

    def get_server_version(self):
        """
        Returns a tuple representing the version of the connected server in
        the following format: (MAJOR_VERSION, MINOR_VERSION, PATCH_VERSION)
        """

        return self.server_version_info

    def show_warnings(self):
        """
        Shows error, warning and note messages from last executed command.
        """

        if (not self.warnings):
            return None;

        cursor= self.cursor()
        cursor.execute("SHOW WARNINGS")
        ret= cursor.fetchall()
        del cursor
        return ret

    class xid(tuple):
        """
        A transaction ID object suitable for passing to the .tpc_*()
        methods of this connection.

        Parameters:
          - format_id: Format id. If not set default value `0` will be used.
          - global_transaction_id: Global transaction qualifier, which must be unique. The maximum length of the global transaction id is limited to 64 characters.
          - branch_qualifier: Branch qualifier which represents a local transaction identifier. The maximum length of the branch qualifier is limited to 64 characters.
 
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
          xid: xid object which was created by .xid() method of connection class

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
        A ProgrammingError will be raised if this method was called outside of
        a TPC transaction.

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
        """
        Returns a list of pending transaction IDs suitable for use with
        tpc_commit(xid) or .tpc_rollback(xid).
        """

        cursor= self.cursor()
        cursor.execute("XA RECOVER")
        result= cursor.fetchall()
        del cursor
        return result

    @property
    def database(self):
        """Get default database for connection."""

        return self._mariadb_get_info(INFO.SCHEMA, str)
 
    @database.setter
    def database(self, schema):
          """Set default database."""

          try:
              self._execute_command("USE %s" % str(schema))
              self._read_response()
          except:
              raise

    @property
    def user(self):
        """
        Returns the user name for the current connection or empty
        string if it can't be determined, e.g. when using socket
        authentication.
        """

        return self._mariadb_get_info(INFO.USER, str)

    @property
    def character_set(self):
        """
        Client character set.

        For MariaDB Connector/Python it is always utf8mb4.
        """

        return _DEFAULT_CHARSET

    @property
    def collation(self):
        """Client character set collation"""

        return _DEFAULT_COLLATION

    @property
    def server_status(self):
        """
        Return server status flags
        """

        return self._mariadb_get_info(INFO.SERVER_STATUS, int)

    @property
    def server_version_info(self):
        """
        Returns numeric version of connected database server in tuple format. 
        """

        version= self.server_version
        return (int(version / 10000), int((version % 10000) / 100), version % 100)

    @property
    def autocommit(self):
        """
        Toggles autocommit mode on or off for the current database connection.

        Autocommit mode only affects operations on transactional table types.
        Be aware that rollback() will not work, if autocommit mode was switched
        on.

        By default autocommit mode is set to False."
        """

        return bool(self.server_status & STATUS.AUTOCOMMIT)

    @autocommit.setter
    def autocommit(self, mode):
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

    @property
    def open(self):
        """
        Returns true if the connection is alive.

        A ping command will be send to the serve for this purpose,
        which means this function might fail if there are still
        non processed pending result sets.
        """

        try:
            self.ping()
        except:
            return False
        return True

    # Aliases
    character_set_name= character_set

    @property
    def thread_id(self):
        """
        Alias for connection_id
        """

        return self.connection_id