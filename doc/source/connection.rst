====================
The connection class
====================

.. sectionauthor:: Georg Richter <georg@mariadb.com>

.. autoclass:: mariadb.connections.Connection

-----------------------
Connection constructors 
-----------------------

.. automethod:: mariadb.connections.Connection.cursor

.. versionadded:: 1.0.1
.. automethod:: mariadb.connections.Connection.xid

------------------
Connection methods 
------------------

.. versionadded:: 1.1.0
.. automethod:: mariadb.connections.Connection.begin

.. automethod:: mariadb.connections.Connection.commit

.. automethod:: mariadb.connections.Connection.change_user(user, password, database)

.. automethod:: mariadb.connections.Connection.close

.. automethod:: mariadb.connections.Connection.cursor

.. automethod:: mariadb.connections.Connection.get_server_version

.. versionadded:: 1.0.5
.. automethod:: mariadb.connections.Connection.escape_string

.. testcode::

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

*Output*:

.. testoutput::

    This string contains the following special characters: \\,\"


.. automethod:: mariadb.connections.Connection.kill

  .. note::
    A thread_id from other connections can be determined by executing the SQL statement ``SHOW PROCESSLIST``
    The thread_id of the current connection the current connection is stored in :data:`connection_id` attribute.

.. automethod:: mariadb.connections.Connection.ping()

.. automethod:: mariadb.connections.Connection.reconnect

.. automethod:: mariadb.connections.Connection.reset

.. automethod:: mariadb.connections.Connection.rollback()

.. versionadded:: 1.1.0
.. automethod:: mariadb.connections.Connection.select_db

.. automethod:: mariadb.connections.Connection.show_warnings

.. automethod:: mariadb.connections.Connection.tpc_begin

.. automethod:: mariadb.connections.Connection.tpc_commit

.. automethod:: mariadb.connections.Connection.tpc_prepare

.. automethod:: mariadb.connections.Connection.tpc_recover

.. automethod:: mariadb.connections.Connection.tpc_rollback

---------------------
Connection attributes
---------------------

.. autoattribute:: mariadb.connections.Connection.auto_reconnect

.. autoattribute:: mariadb.connections.Connection.autocommit

.. autoattribute:: mariadb.connections.Connection.character_set

.. versionadded:: 1.1.0:
.. autoattribute:: mariadb.connections.Connection.client_capabilities

.. autoattribute:: mariadb.connections.Connection.collation

.. autoattribute:: mariadb.connections.Connection.connection_id

.. autoattribute:: mariadb.connections.Connection.database

.. versionadded:: 1.1.0
.. autoattribute:: mariadb.connections.Connection.open

.. versionadded:: 1.1.0
.. autoattribute:: mariadb.connections.Connection.server_capabilities

.. versionadded:: 1.1.0
.. autoattribute:: mariadb.connections.Connection.extended_server_capabilities

.. autoattribute:: mariadb.connections.Connection.server_info

.. autoattribute:: mariadb.connections.Connection.server_name

.. autoattribute:: mariadb.connections.Connection.server_port

.. versionadded:: 1.1.0
.. autoattribute:: mariadb.connections.Connection.server_status

.. autoattribute:: mariadb.connections.Connection.server_version

.. autoattribute:: mariadb.connections.Connection.server_version_info

.. versionadded:: 1.0.5
.. autoattribute:: mariadb.connections.Connection.tls_cipher

.. autoattribute:: mariadb.connections.Connection.tls_version

.. autoattribute:: mariadb.connections.Connection.unix_socket

.. autoattribute:: mariadb.connections.Connection.user

.. autoattribute:: mariadb.connections.Connection.warnings
