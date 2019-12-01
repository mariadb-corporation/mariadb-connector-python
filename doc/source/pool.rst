The ConnectionPool class
========================

.. sectionauthor:: Georg Richter <georg@mariadb.com>

.. class:: ConnectionPool

    MariaDB Connector/Python supports simple connection pooling.
    A connection pool holds a number of open connections and handles thread safety
    when providing connections to threads.

    The size of a connection pool is configurable at creation time, but cannot be
    changed afterwards. The maximum size of a connection pool is limited to 64 connections.

    .. method:: add_connection(connection)

       Adds a connection object to the connection pool.

       In case that pool doesn't have a free slot or is not configured a PoolError
       exception will be raised.

    .. method:: get_connection()

       Returns a connection from the connection pool or raises a PoolError if no 
       connection is available.

    .. method:: set_config(\*\*kwargs)

       Sets the connection configuration for the connection pool. 

    .. data:: max_size

       Returns the maximum allowed size of the pool

    .. data:: pool_size

       Returns the size of connection pool

    .. data:: pool_name

       Returns the name of the pool.
       
