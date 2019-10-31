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
  "implicit rollback to be performed.\n\\n"
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
