The connection class
====================

.. sectionauthor:: Georg Richter <georg@mariadb.com>

.. class:: connection

    Handles the connection to a MariaDB or MySQL database server. It encapsulates
    a database session.

    Connections are created using the factory function
    `mariadb.connect()`.

    .. method:: cursor(\*\*kwargs)

    Returns a new cursor object using the current connection.

    Supported parameters:

    - `named_tuple` -- when set to `True` results from fetch methods will be returned as named tuple.
    - `cursor_type` -- when set to `CURSOR_TYPE_READ_ONLY`, server side cursor will be used.
    - `prefetch_size` -- The number of rows prefetched. This option will be ignored, if *cursor_type* is not `CURSOR_TYPE_READ_ONLY`
    - `buffered` -- when set to `True` the entire result set from a SELECT/SHOW statement will be stored in client memory
    - `prepared` -- when set to `True` cursor will remain in prepared state after the first *execute()* method was called. Further calls to *execute()* method will ignore the sql statement.

    .. method:: xid(format_id, global_transaction_id, branch_qualifier)

       Returns a transaction ID object suitable for passing to the tpc
       methods of this connection

    .. method:: commit()
    
    Commit any pending transaction to the database.
    
    .. note:: 

       This method has no effect, when autocommit was set to True,
       or the storage engine in use doesn't support transactions.

    .. method:: change_user(user, password, database)

       Changes the *user* and default *database* of the current connection.
       In order to successfully change users a valid username and password
       parameters must be provided and that user must have sufficient
       permissions to access the desired database.

       If for any reason authorization fails, the current user authentication will remain.

    .. method:: close()

       Close the connection now (rather than whenever .__del__() is called).
       
       The connection will be unusable from this point forward; an Error
       (or subclass) exception will be raised if any operation is attempted
       with the connection. The same applies to all cursor objects trying to
       use the connection. If the connection was obtained by *ConnectionPool*,
       the connection will not be closed but returned to the pool.

    .. method: connect(\*\*kwargs)

       Establishes a connection to a database server.
       object.
 
       The connection parameters have to be provided as a set of keyword arguments::
 
          connection.connect(user="myuser", host="localhost", database="test", password="secret")
 
       The supported connection parameters are:
 
       - user -- username used to authenticate with the database server
       - password -- password to authenticate
       - host -- host name or IP address of the database server
       - database -- database (schema) name to used when connecting with the database server
       - unix_socket -- location of the unix socket file
       - port -- port number of the database server. If not specified the default value (=3306) will be used.
       - charset -- default character set to be used
       - connect_timeout -- connect timeout in seconds
       - read_timeout -- read timeout in seconds
       - write_timeout -- write timeout in seconds
       - local_infile -- Enables or disables the use of LOAD DATA LOCAL INFILE statements.
       - compress -- Uses the compressed protocol for client server communication. If the
           server doesn't support compressed protocol, the default protocol will
           be used
       - init_command -- Command(s) which will be executed when connecting and reconnecting to
           the database server
       - default_file -- Read options from the specified option file. If the file is an empty
           string, default configuration file(s) will be used
       - default_group -- Read options from the specified group
       - ssl_key -- Defines a path to a private key file to use for TLS. This option
           requires that you use the absolute path, not a relative path. The specified key must be in PEM format
       - ssl_cert -- Defines a path to the X509 certificate file to use for TLS.
           This option requires that you use the absolute path, not a relative path. The X609 certificate must be in PEM format.
       - ssl_ca -- Defines a path to a PEM file that should contain one or more X509
           certificates for trusted Certificate Authorities (CAs) to use for TLS.
           This option requires that you use the absolute path, not a relative
           path.
       - ssl_cipher -- Defines a list of permitted cipher suites to use for TLS
       - ssl_crl_path -- Defines a path to a PEM file that should contain one or more revoked
           X509 certificates to use for TLS. This option requires that you use
           the absolute path, not a relative path.
       - ssl_verify_server_cert -- Enables server certificate verification.
       - ssl_enforce -- Always use a secure TLS connection

    .. method:: escape_string(string)
       
       This function is used to create a legal SQL string that you can use in
       an SQL statement. The given string is encoded and returned as an escaped string.

    .. method:: kill(thread_id)

       This function is used to ask the server to terminate a database connection, specified
       by the *thread_id* parameter. This value must be retrieved by 'SHOW PROCESSLIST' sql command.

    .. method:: ping()

       Checks if the connection to the database server is still available.
      
       .. note::

           If auto reconnect was set to true, an attempt will be made to reconnect
           to the database server in case the connection  was lost

       If the connection is not available an InterfaceError will be raised.

    .. method:: reconnect()

       tries to reconnect to a server in case the connection died due to timeout
       or other errors. It uses the same credentials which were specified in
       *connect()* method.

    .. method:: reset()

       tries to reconnect to a server in case the connection died due to timeout
       or other errors. It uses the same credentials which were specified in
       connect() method.

    .. method:: rollback()

       Causes the database to roll back to the start of any pending transaction
       
       Closing a connection without committing the changes first will cause an
       implicit rollback to be performed.

       .. note::

           rollback() will not work as expected if autocommit mode was set to True
           or the storage engine does not support transactions.


    .. method:: tpc_begin(xid)

       Begins a TPC transaction with the given transaction ID xid, which
       was created by xid() method.

       This method should be called outside of a transaction
       (i.e. nothing may have executed since the last .commit()
       or .rollback()).

       Furthermore, it is an error to call commit() or rollback() within
       the TPC transaction. A ProgrammingError is raised, if the application
       calls commit() or rollback() during an active TPC transaction.

    .. method:: tpc_commit(xid)

       When called with no arguments, tpc_commit() commits a TPC transaction
       previously prepared with tpc_prepare().

       If tpc_commit() is called prior to tpc_prepare(), a single phase commit
       is performed. A transaction manager may choose to do this if only a
       single resource is participating in the global transaction.

       When called with a transaction ID xid, the database commits the given
       transaction. If an invalid transaction ID is provided, a ProgrammingError
       will be raised. This form should be called outside of a transaction, and
       is intended for use in recovery.

    .. method:: tpc_prepare([ xid])

       Performs the first phase of a transaction started with tpc_begin().

       A ProgrammingError will be raised if this method outside of a TPC
       transaction.

       After calling tpc_prepare(), no statements can be executed until
       tpc_commit() or tpc_rollback() have been called.
   
     .. method:: tpc_recover()

       Returns a list of pending transaction IDs suitable for use with
       tpc_commit(xid) or tpc_rollback(xid).
   
    .. method:: tpc_rollback([ xid])
       
       When called with no arguments, .tpc_rollback() rolls back a TPC
       transaction. It may be called before or after .tpc_prepare().
       
       When called with a transaction ID xid, it rolls back the given
       transaction.

    .. data:: auto_reconnect

       Enable or disable automatic reconnection to the server if the connection
       is found to have been lost.
       
       When enabled, client tries to reconnect to a database server in case
       the connection to a database server died due to timeout or other errors.

    .. data:: autocommit

       Toggles autocommit mode on or off for the current database connection.
       
       Autocommit mode only affects operations on transactional table types.
       Be aware that rollback() will not work, if autocommit mode was switched
       on.
       
       By default autocommit mode is set to False.

    .. data:: |  character_set

       Returns the character set used for the connection
   
    .. data:: collation

       Returns character set collation used for the connection
  
    .. data:: connection_id
       
       Returns the (thread) id for the current connection.
      
       If reconnect was set to True, the id might change if the client
       reconnects to the database server
   
    .. data:: database
       
       Returns or sets the default database for the current connection
       
       If the used datbase will not change, the preffered way is to specify
       the default database in connect() method.

    .. data:: server_info
       
       Returns the alphanumeric version of connected database. Tthe numeric version
       can be obtained via server_version() property.
   
    .. data:: server_name

       Returns name or IP address of database server
  
    .. data:: server_port

       Returns the database server TCP/IP port
  
    .. data:: server_version
       
       Returns numeric version of connected database server. The form of the version
       number is VERSION_MAJOR * 10000 + VERSION_MINOR * 100 + VERSION_PATCH
   
    .. data:: tls_cipher

       Returns TLS cipher suite in use by connection
   
    .. data:: tls_version

       Returns TLS protocol version used by connection
   
    .. data:: unix_socket

       Returns Unix socket name

    .. data:: user

       Returns user name for the current connection

    .. data:: warnings

       Returns the number of warnings from the last executed statement, or zero
       if there are no warnings.
       
       .. note::

           If SQL_MODE TRADITIONAL is enabled an error instead of a warning will be
           returned. To retrieve warnings use the cursor method execute("SHOW WARNINGS".
