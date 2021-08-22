========================
The ConnectionPool class
========================

.. sectionauthor:: Georg Richter <georg@mariadb.com>

.. autoclass:: mariadb.ConnectionPool

.. testcode::

    import mariadb

    pool= mariadb.ConnectionPool(pool_name="mypool")
    print(pool.max_size)

.. testoutput::

----------------------
ConnectionPool methods
----------------------

.. automethod:: mariadb.ConnectionPool.add_connection

.. automethod:: mariadb.ConnectionPool.close

.. automethod:: mariadb.ConnectionPool.get_connection

.. automethod:: mariadb.ConnectionPool.set_config

-------------------------
ConnectionPool attributes
-------------------------

.. versionadded:: 1.1.0
.. autoattribute:: mariadb.ConnectionPool.connection_count

.. autoattribute:: mariadb.ConnectionPool.max_size

.. autoattribute:: mariadb.ConnectionPool.pool_size

.. autoattribute:: mariadb.ConnectionPool.pool_name
       
.. versionadded:: 1.1.0
.. autoattribute:: mariadb.ConnectionPool.pool_reset_connection
