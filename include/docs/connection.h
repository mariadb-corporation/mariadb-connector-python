/************************************************************************************
    Copyright (C) 2019 Georg Richter and MariaDB Corporation AB

   This library is free software; you can redistribute it and/or
   modify it under the terms of the GNU Library General Public
   License as published by the Free Software Foundation; either
   version 2 of the License, or (at your option) any later version.

   This library is distributed in the hope that it will be useful,
   but WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
   Library General Public License for more details.

   You should have received a copy of the GNU Library General Public
   License along with this library; if not see <http://www.gnu.org/licenses>
   or write to the Free Software Foundation, Inc.,
   51 Franklin St., Fifth Floor, Boston, MA 02110, USA
*************************************************************************************/
PyDoc_STRVAR(
  connection_connect__doc__,
  __connect__doc__
);

PyDoc_STRVAR(
  connection__doc__,
  "The Connection class is used to open and manage a connection to a\n"
  "MariaDB or compatible database server"
);

PyDoc_STRVAR(
  connection_close__doc__,
  "close()\n"
  "--\n"
  "\n"
  "Close the connection now (rather than whenever .__del__() is called).\n\n"
  "The connection will be unusable from this point forward; an Error\n"
  "(or subclass) exception will be raised if any operation is attempted\n"
  "with the connection. The same applies to all cursor objects trying to\n"
  "use the connection.\n\n"
  "Note that closing a connection without committing the changes first\n"
  "will cause an implicit rollback to be performed."
);

PyDoc_STRVAR(
  connection_commit__doc__,
  "commit()\n"
  "--\n"
  "\n"
  "Commit any pending transaction to the database.\n\n"
  "Note that this function has no effect, when autocommit was set to True\n"
);

PyDoc_STRVAR(
  connection_rollback__doc__,
  "rollback()\n"
  "--\n"
  "\n"
  "Causes the database to roll back to the start of any pending transaction\n\n"
  "Closing a connection without committing the changes first will cause an\n"
  "implicit rollback to be performed.\n\n"
  "Note that rollback() will not work as expected if autocommit mode was set to True\n"
  "or the storage engine does not support transactions."
);

PyDoc_STRVAR(
  connection_cursor__doc__,
  "cursor()\n"
  "--\n"
  "\n"
  "Return a new cursor object for the current connection."
);

PyDoc_STRVAR(
  connection_tpc_begin__doc__,
  "tpc_begin(xid)\n"
  "--\n"
  "\n"
  "Parameter:\n"
  "xid: xid object which was created by .xid()\n\n"
  "Begins a TPC transaction with the given transaction ID xid.\n\n"
  "This method should be called outside of a transaction\n"
  "(i.e. nothing may have executed since the last .commit()\n"
  "or .rollback()).\n\n"
  "Furthermore, it is an error to call .commit() or .rollback() within\n"
  "the TPC transaction. A ProgrammingError is raised, if the application\n"
  "calls .commit() or .rollback() during an active TPC transaction."
);

PyDoc_STRVAR(
  connection_tpc_prepare__doc__,
  "tpc_prepare(xid)\n"
  "--\n"
  "\n"
  "Parameter:\n"
  "xid: xid object which was created by .xid()\n\n"
  "Performs the first phase of a transaction started with .tpc_begin().\n"
  "A ProgrammingError will be raised if this method outside of a TPC\n"
  "transaction.\n\n"
  "After calling .tpc_prepare(), no statements can be executed until\n"
  ".tpc_commit() or .tpc_rollback() have been called."
);

PyDoc_STRVAR(
  connection_tpc_commit__doc__,
  "tpc_commit([xid])\n"
  "--\n"
  "\n"
  "Optional parameter:\n"
  "xid: xid object which was created by .xid()\n\n"
  "When called with no arguments, .tpc_commit() commits a TPC transaction\n" 
  "previously prepared with .tpc_prepare().\n\n"
  "If .tpc_commit() is called prior to .tpc_prepare(), a single phase commit\n"
  "is performed. A transaction manager may choose to do this if only a\n"
  "single resource is participating in the global transaction.\n"
  "When called with a transaction ID xid, the database commits the given\n"
  "transaction. If an invalid transaction ID is provided, a ProgrammingError\n"
  "will be raised. This form should be called outside of a transaction, and\n"
  "is intended for use in recovery."
);

PyDoc_STRVAR(
  connection_tpc_recover__doc__,
  "tpc_recover()\n"
  "--\n"
  "\n"
  "Returns a list of pending transaction IDs suitable for use with\n"
  ".tpc_commit(xid) or .tpc_rollback(xid)."
);

PyDoc_STRVAR(
  connection_tpc_rollback__doc__,
  "tpc_rollback([xid])\n"
  "--\n"
  "\n"
  "Optional parameter:\n"
  "xid: xid object which was created by .xid()\n\n"
  "When called with no arguments, .tpc_rollback() rolls back a TPC\n"
  "transaction. It may be called before or after .tpc_prepare().\n\n"
  "When called with a transaction ID xid, it rolls back the given\n"
  "transaction.\n\n"
);

PyDoc_STRVAR(
  connection_xid__doc__, 
  "xid(format_id, global_transaction_id, branch_qualifier)\n"
  "--\n"
  "\n"
  "Parameters:\n"
  "format_id: string xid object which was created by .xid()\n\n"
  "Returns a transaction ID object suitable for passing to the .tpc_*()\n"
  "methods of this connection\n"
);

PyDoc_STRVAR(
  connection_change_user__doc__,
  "change_user(user, password, database)\n"
  "--\n"
  "\n"
  "Parameters:\n"
  "user: string\n"
  "password: string\n"
  "database: string\n\n"
  "Changes the user and default database of the current connection.\n"
  "In order to successfully change users a valid username and password\n"
  "parameters must be provided and that user must have sufficient\n"
  "permissions to access the desired database. If for any reasonßn"
  "authorization fails, the current user authentication will remain."
);

PyDoc_STRVAR(
  connection_reconnect__doc__,
  "reconnect()\n"
  "--\n"
  "\n"
  "tries to reconnect to a server in case the connection died due to timeout\n"
  "or other errors. It uses the same credentials which were specified in\n"
  "connect() method."
);

PyDoc_STRVAR(
  connection_reset__doc__,
  "reset()\n"
  "--\n"
  "\n"
  "Resets the current connection and clears session state and pending\n"
  "results. Open cursors will become invalid and cannot be used anymore."
);

PyDoc_STRVAR(
  connection_escape_string__doc__,
  "escape_string(statement)\n"
  "--\n"
  "\n"
  "Parameters:\n"
  "statement: string\n\n"
  "This function is used to create a legal SQL string that you can use in\n"
  "an SQL statement. The given string is encoded to an escaped SQL string."
);

PyDoc_STRVAR(
  connection_kill__doc__,
  "kill(connection_id)\n"
  "--\n"
  "\n"
  "Parameters:\n"
  "connection_id: integer\n\n"
  "This function is used to ask the server to kill a database connection"
  "specified by the processid parameter. This value must be retrieved "
  "by SHOW PROCESSLIST sql command."
);

PyDoc_STRVAR(
  connection_ping__doc__, 
  "ping()\n"
  "--\n"
  "\n"
  "Checks if the connection to the database server is still available.\n\n"
  "If auto reconnect was set to true, an attempt will be made to reconnect\n"
  "to the database server in case the connection\n"
  "was lost\n\n"
  "If the connection is not available an InterfaceError will be raised."
);

PyDoc_STRVAR(
  connection_autocommit__doc__,
  "(read/write)\n\n"
  "Toggles autocommit mode on or off for the current database connection.\n\n"
  "Autocommit mode only affects operations on transactional table types.\n"
  "Be aware that rollback() will not work, if autocommit mode was switched\n"
  "on.\n\n"
  "By default autocommit mode is set to False."
);

PyDoc_STRVAR(
  connection_connection_id__doc__,
  "(read only)\n\n"
  "returns the (thread) id for the current connection.\n\n"
  "If reconnect was set to True, the id might change if the client\n"
  "reconnects to the database server"
);

PyDoc_STRVAR(
  connection_database__doc__,
  "(read/write)\n\n"
  "Returns or sets the default database for the current connection\n\n"
  "If the used datbase will not change, the preffered way is to specify\n"
  "the default database in connect() method."
);

PyDoc_STRVAR(
  connection_auto_reconnect__doc__,
  "(read/write)\n\n"
  "Enable or disable automatic reconnection to the server if the connection\n"
  "is found to have been lost.\n\n"
  "When enabled, client tries to reconnect to a database server in case\n"
  "the connection to a database server died due to timeout or other errors."
);

PyDoc_STRVAR(
  connection_user__doc__,
  "(read only)\n\n"
  "Returns the user name for the current connection."
);

PyDoc_STRVAR(
  connection_warnings__doc__,
  "(read only)\n\n"
  "Returns the number of warnings from the last executed statement, or zero\n"
  "if there are no warnings.\n\n"
  "If SQL_MODE TRADITIONAL is enabled an error instead of a warning will be\n"
  "returned. To retrieve warnings use the cursor method execute(\"SHOW WARNINGS\").\n"
);

PyDoc_STRVAR(
  connection_server_version__doc__,
  "(read only)\n\n"
  "Returns numeric version of connected database server. The form of the version\n"
  "number is VERSION_MAJOR * 10000 + VERSION_MINOR * 100 + VERSION_PATCH"
);

PyDoc_STRVAR(
  connection_server_info__doc__,
  "(read only)\n\n"
  "Returns the alphanumeric version of connected database. Tthe numeric version\n"
  "can be obtained with server_version property."
);

PyDoc_STRVAR(
  connection_enter__doc__,
  "(read)\n\n"
  "returns a copy of the connection"
);

PyDoc_STRVAR(
  connection_exit__doc__,
  "--\n"
  "closes the connection"
);
