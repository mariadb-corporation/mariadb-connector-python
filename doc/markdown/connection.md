# The connection class

### *class* Connection(\*args, \*\*kwargs)

MariaDB Connector/Python Connection Object

Handles the connection to a MariaDB or MySQL database server.
It encapsulates a database session.

Connections are created using the method mariadb.connect()

## Connection constructors

#### Connection.cursor(cursorclass=<class 'mariadb.cursors.Cursor'>, \*\*kwargs)

Returns a new cursor object for the current connection.

If no cursorclass was specified, a cursor with default mariadb.Cursor
class will be created.

Optional keyword parameters:

- buffered = True
  If set to False the result will be unbuffered, which means before
  executing another statement with the same connection the entire
  result set must be fetched.
  Please note that the default was False for MariaDB Connector/Python
  versions < 1.1.0.
- dictionary = False
  Return fetch values as dictionary.
- named_tuple = False
  Return fetch values as named tuple. This feature exists for
  compatibility reasons and should be avoided due to possible
  inconsistency.
- cursor_type = CURSOR.NONE
  If cursor_type is set to CURSOR.READ_ONLY, a cursor is opened
  for the statement invoked with cursors execute() method.
- prepared = False
  When set to True cursor will remain in prepared state after the first
  execute() method was called. Further calls to execute() method will
  ignore the sql statement.
- binary = False
  Always execute statement in MariaDB client/server binary protocol.

In versions prior to 1.1.0 results were unbuffered by default,
which means before executing another statement with the same
connection the entire result set must be fetched.

fetch\* methods of the cursor class by default return result set values
as a tuple, unless dictionary or named_tuple was specified.
The latter one exists for compatibility reasons and should be avoided
due to possible inconsistency in case two or more fields in a result
set have the same name.

If cursor_type is set to CURSOR.READ_ONLY, a cursor is opened for
the statement invoked with cursors execute() method.

#### Connection.xid(format_id: int, global_transaction_id: str, branch_qualifier: str)

Creates a transaction ID object suitable for passing to the .tpc_\*()
methods of this connection.

Parameters:

- format_id: Format id. If not set default value 0 will be used.
- global_transaction_id: Global transaction qualifier, which must be
  unique. The maximum length of the global transaction id is
  limited to 64 characters.
- branch_qualifier: Branch qualifier which represents a local
  transaction identifier. The maximum length of the branch qualifier
  is limited to 64 characters.

### History:

#### Versionadded
Added in version 1.0.1: The xid object.

## Connection methods

#### Versionadded
Added in version 1.1.0.

#### Connection.begin()

Start a new transaction which can be committed by .commit() method,
or cancelled by .rollback() method.

#### Connection.commit()

Commit any pending transaction to the database.

#### Connection.change_user(user, password, database)

Changes the user and default database of the current connection

Parameters:
: - user: user name
  - password: password
  - database: name of default database

In order to successfully change users a valid username and password
parameters must be provided and that user must have sufficient
permissions to access the desired database. If for any reason
authorization fails an exception will be raised and the current user
authentication will remain.

#### Connection.close()

Close the connection now (rather than whenever ._\_del_\_() is called).

The connection will be unusable from this point forward; an Error
(or subclass) exception will be raised if any operation is attempted
with the connection. The same applies to all cursor objects trying to
use the connection.

Note that closing a connection without committing the changes first
will cause an implicit rollback to be performed.

#### Connection.cursor(cursorclass=<class 'mariadb.cursors.Cursor'>, \*\*kwargs)

Returns a new cursor object for the current connection.

If no cursorclass was specified, a cursor with default mariadb.Cursor
class will be created.

Optional keyword parameters:

- buffered = True
  If set to False the result will be unbuffered, which means before
  executing another statement with the same connection the entire
  result set must be fetched.
  Please note that the default was False for MariaDB Connector/Python
  versions < 1.1.0.
- dictionary = False
  Return fetch values as dictionary.
- named_tuple = False
  Return fetch values as named tuple. This feature exists for
  compatibility reasons and should be avoided due to possible
  inconsistency.
- cursor_type = CURSOR.NONE
  If cursor_type is set to CURSOR.READ_ONLY, a cursor is opened
  for the statement invoked with cursors execute() method.
- prepared = False
  When set to True cursor will remain in prepared state after the first
  execute() method was called. Further calls to execute() method will
  ignore the sql statement.
- binary = False
  Always execute statement in MariaDB client/server binary protocol.

In versions prior to 1.1.0 results were unbuffered by default,
which means before executing another statement with the same
connection the entire result set must be fetched.

fetch\* methods of the cursor class by default return result set values
as a tuple, unless dictionary or named_tuple was specified.
The latter one exists for compatibility reasons and should be avoided
due to possible inconsistency in case two or more fields in a result
set have the same name.

If cursor_type is set to CURSOR.READ_ONLY, a cursor is opened for
the statement invoked with cursors execute() method.

#### Versionadded
Added in version 1.1.2.

#### Connection.dump_debug_info()

This function is designed to be executed by an user with the SUPER privilege
and is used to dump server status information into the log for the MariaDB
Server relating to the connection.

#### Connection.get_server_version()

Returns a tuple representing the version of the connected server in
the following format: (MAJOR_VERSION, MINOR_VERSION, PATCH_VERSION)

#### Versionadded
Added in version 1.0.5.

#### Connection.escape_string()

Parameters:
statement: string

This function is used to create a legal SQL string that you can use in
an SQL statement. The given string is encoded to an escaped SQL string.

```python
import mariadb

# connection parameters
conn_params= {
    "user" : "example_user",
    "password" : "GHbe_Su3B8",
    "host" : "localhost"
}

# Establish a connection
connection= mariadb.connect(**conn_params)

string= 'This string contains the following special characters: \,"'
print(connection.escape_string(string))
```

*Output*:

```none
This string contains the following special characters: \\,\"
```

#### Connection.kill(id: int)

This function is used to ask the server to kill a database connection
specified by the processid parameter.

The connection id can be be retrieved by SHOW PROCESSLIST sql command.

#### NOTE
A thread_id from other connections can be determined by executing the SQL statement `SHOW PROCESSLIST`
The thread_id of the current connection the current connection is stored in [`connection_id`](#mariadb.connections.Connection.connection_id) attribute.

#### Connection.ping()

Checks if the connection to the database server is still available.

If auto reconnect was set to true, an attempt will be made to reconnect
to the database server in case the connection
was lost

If the connection is not available an InterfaceError will be raised.

#### Connection.reconnect()

tries to reconnect to a server in case the connection died due to timeout
or other errors. It uses the same credentials which were specified in
connect() method.

#### Connection.reset()

Resets the current connection and clears session state and pending
results. Open cursors will become invalid and cannot be used anymore.

#### Connection.rollback()

Causes the database to roll back to the start of any pending
transaction

Closing a connection without committing the changes first will
cause an implicit rollback to be performed.
Note that rollback() will not work as expected if autocommit mode
was set to True or the storage engine does not support transactions.”

#### Versionadded
Added in version 1.1.0.

#### Connection.select_db(new_db: str)

Gets the default database for the current connection.

The default database can also be obtained or changed by database
attribute.

#### Connection.show_warnings()

Shows error, warning and note messages from last executed command.

#### Connection.tpc_begin(xid)

Parameter:
: xid: xid object which was created by .xid() method of connection
  : class

Begins a TPC transaction with the given transaction ID xid.

This method should be called outside of a transaction
(i.e. nothing may have executed since the last .commit()
or .rollback()).
Furthermore, it is an error to call .commit() or .rollback() within
the TPC transaction. A ProgrammingError is raised, if the application
calls .commit() or .rollback() during an active TPC transaction.

#### Connection.tpc_commit(xid=None)

Optional parameter:”
xid: xid object which was created by .xid() method of connection class.

When called with no arguments, .tpc_commit() commits a TPC transaction
previously prepared with .tpc_prepare().

If .tpc_commit() is called prior to .tpc_prepare(), a single phase
commit is performed. A transaction manager may choose to do this if
only a single resource is participating in the global transaction.
When called with a transaction ID xid, the database commits the given
transaction. If an invalid transaction ID is provided,
a ProgrammingError will be raised.
This form should be called outside of a transaction, and
is intended for use in recovery.”

#### Connection.tpc_prepare()

Performs the first phase of a transaction started with .tpc_begin().
A ProgrammingError will be raised if this method was called outside of
a TPC transaction.

After calling .tpc_prepare(), no statements can be executed until
.tpc_commit() or .tpc_rollback() have been called.

#### Connection.tpc_recover()

Returns a list of pending transaction IDs suitable for use with
tpc_commit(xid) or .tpc_rollback(xid).

#### Connection.tpc_rollback(xid=None)

Parameter:
: xid: xid object which was created by .xid() method of connection
  : class

Performs the first phase of a transaction started with .tpc_begin().
A ProgrammingError will be raised if this method outside of a TPC
transaction.

After calling .tpc_prepare(), no statements can be executed until
.tpc_commit() or .tpc_rollback() have been called.

## Connection attributes

#### Connection.auto_reconnect

(read/write)

Enable or disable automatic reconnection to the server if the connection
is found to have been lost.

When enabled, client tries to reconnect to a database server in case
the connection to a database server died due to timeout or other errors.

#### Connection.autocommit

Toggles autocommit mode on or off for the current database connection.

Autocommit mode only affects operations on transactional table types.
Be aware that rollback() will not work, if autocommit mode was switched
on.

By default autocommit mode is set to False.”

#### Connection.character_set

Client character set.

For MariaDB Connector/Python it is always utf8mb4.

#### Versionadded
Added in version 1.1.0:.

#### Connection.client_capabilities

Client capability flags.

#### Connection.collation

Client character set collation

#### Connection.connection_id

Id of current connection

#### Connection.database

Get default database for connection.

#### Versionadded
Added in version 1.1.0.

#### Connection.open

Returns true if the connection is alive.

A ping command will be send to the server for this purpose,
which means this function might fail if there are still
non processed pending result sets.

#### Versionadded
Added in version 1.1.0.

#### Connection.server_capabilities

Server capability flags.

#### Versionadded
Added in version 1.1.0.

#### Connection.extended_server_capabilities

Extended server capability flags (only for MariaDB
database servers).

#### Connection.server_info

Server version in alphanumerical format (str)

#### Connection.server_name

Name or IP address of database server.

#### Connection.server_port

Database server TCP/IP port. This value will be 0 in case of a unix
socket connection.

#### Versionadded
Added in version 1.1.0.

#### Connection.server_status

Return server status flags

#### Connection.server_version

Server version in numerical format.

The form of the version number is
VERSION_MAJOR \* 10000 + VERSION_MINOR \* 100 + VERSION_PATCH

#### Connection.server_version_info

Returns numeric version of connected database server in tuple format.

#### Versionadded
Added in version 1.0.5.

#### Connection.tls_cipher

TLS cipher suite if a secure connection is used.

#### Connection.tls_version

TLS protocol version if a secure connection is used.

#### Versionadded
Added in version 1.1.11.

#### Connection.tls_peer_cert_info

Get peer certificate information.

#### Connection.unix_socket

Unix socket name.

#### Connection.user

Returns the user name for the current connection or empty
string if it can’t be determined, e.g. when using socket
authentication.

#### Connection.warnings

Returns the number of warnings from the last executed statement, or zero
if there are no warnings.
