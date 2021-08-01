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

.. automethod:: mariadb.connections.Connection.xid(format_id: int, global_transaction_id: str, brach_qualifier: str)

------------------
Connection methods 
------------------

.. versionadded:: 1.1.0
.. automethod:: mariadb.connections.Connection.begin

.. automethod:: mariadb.connections.Connection.commit

.. automethod:: mariadb.connections.Connection.change_user(user, password, database)

  If for any reason authorization fails an exception will be raised and the current user authentication will remain.

.. automethod:: mariadb.connections.Connection.close

.. automethod:: mariadb.connections.Connection.get_server_version

.. versionadded:: 1.0.5

.. automethod:: mariadb.connections.Connection.escape_string(escape_str)
 
.. automethod:: mariadb.connections.Connection.kill(thread_id)

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

.. autoattribute:: mariadb.connections.Connection.collation

.. autoattribute:: mariadb.connections.Connection.connection_id
 
.. autoattribute:: mariadb.connections.Connection.database
 
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
