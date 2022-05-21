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
  connection_dump_debug_info__doc__,
  "dump_debug_info()\n"
  "--\n"
  "\n"
  "This function is designed to be executed by an user with the SUPER privilege\n"
  "and is used to dump server status information into the log for the MariaDB\n"
  "Server relating to the connection."
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
  connection_change_user__doc__,
  "change_user(user: str, password: str, database: str)\n"
  "--\n"
  "\n"
  "Changes the user and default database of the current connection\n\n"
  "Parameters:\n"
  "  - user: user name\n"
  "  - password: password\n"
  "  - database: name of default database\n\n"
  "In order to successfully change users a valid username and password\n"
  "parameters must be provided and that user must have sufficient\n"
  "permissions to access the desired database. If for any reason\n"
  "authorization fails an exception will be raised and the current user\n"
  "authentication will remain."
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

/* ok */
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
  connection_auto_reconnect__doc__,
  "(read/write)\n\n"
  "Enable or disable automatic reconnection to the server if the connection\n"
  "is found to have been lost.\n\n"
  "When enabled, client tries to reconnect to a database server in case\n"
  "the connection to a database server died due to timeout or other errors."
);

PyDoc_STRVAR(
  connection_warnings__doc__,
  "Returns the number of warnings from the last executed statement, or zero\n"
  "if there are no warnings."
);
