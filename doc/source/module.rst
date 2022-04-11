.. _module:

The MariaDB Connector/Python module
===================================

.. sectionauthor:: Georg Richter <georg@mariadb.com>

.. automodule:: mariadb


Constructors 
------------

----------
Connection
----------

.. autofunction:: mariadb.connect(connectionclass=mariadb.connections.Connection, **kwargs)

.. note::
    For a description of configuration file handling and settings please read the chapter `Configuration files <https://github.com/mariadb-corporation/mariadb-connector-c/wiki/config_files#configuration-options>`_ of the MariaDB Connector/C documentation.

Example:

.. testcode::

      import mariadb

      connection= mariadb.connect(user="example_user", host="localhost", database="test", password="GHbe_Su3B8")

      print(connection.character_set)

Output:

.. testoutput::

    utf8mb4

---------------
Connection Pool
---------------

.. autofunction:: mariadb.ConnectionPool(**kwargs)

-----------------
Type constructors
-----------------

.. autofunction:: mariadb.Binary()

.. autofunction:: mariadb.Date(year, month, day)

.. autofunction:: mariadb.DateFromTicks(ticks)

.. autofunction:: mariadb.Time(hour, minute, second)

.. autofunction:: mariadb.TimeFromTicks(ticks)

.. autofunction:: mariadb.Timestamp(year, month, day, hour, minute, second)

.. autofunction:: mariadb.TimestampFromTicks(ticks)

Attributes
----------

.. attribute:: apilevel

    String constant stating the supported DB API level. The value for `mariadb` is
    ``2.0``.

.. attribute:: threadsafety

    Integer constant stating the level of thread safety. For `mariadb` the value is 1,
    which means threads can share the module but not the connection.

.. attribute:: paramstyle

    String constant stating the type of parameter marker. For `mariadb` the value is
    `qmark`. For compatibility reasons `mariadb` also supports the `format` and
    `pyformat` paramstyles with the limitation that they can't be mixed inside a SQL statement.

.. attribute:: mariadbapi_version

    String constant stating the version of the used MariaDB Connector/C library.

.. versionadded:: 1.1.0
.. attribute:: client_version

    Returns the version of MariaDB Connector/C library in use as an integer.
    The number has the following format:
    MAJOR_VERSION * 10000 + MINOR_VERSION * 1000 + PATCH_VERSION

.. versionadded:: 1.1.0
.. attribute:: client_version_info

    Returns the version of MariaDB Connector/C library as a tuple in the
    following format:
    (MAJOR_VERSION, MINOR_VERSION, PATCH_VERSION)


Exceptions
----------

Compliant to DB API 2.0 MariaDB Connector/C provides information about errors
through the following exceptions:

.. autoexception:: mariadb.DataError

.. autoexception:: mariadb.DatabaseError

.. autoexception:: mariadb.InterfaceError

.. autoexception:: mariadb.Warning

.. autoexception:: mariadb.PoolError

.. autoexception:: mariadb.OperationalError

.. autoexception:: mariadb.IntegrityError

.. autoexception:: mariadb.InternalError

.. autoexception:: mariadb.ProgrammingError

.. autoexception:: mariadb.NotSupportedError

------------
Type objects 
------------

..
     _Note: Type objects are handled as constants, therefore we can't
     use autodata.

MariaDB Connector/Python type objects are immutable sets for type settings
and defined in DBAPI 2.0 (PEP-249).

Example:

.. testcode::

    import mariadb
    from mariadb.constants import FIELD_TYPE

    print(FIELD_TYPE.GEOMETRY == mariadb.BINARY)
    print(FIELD_TYPE.DATE == mariadb.DATE)
    print(FIELD_TYPE.VARCHAR == mariadb.BINARY)

Output:

.. testoutput::

    True
    True
    False

.. data:: STRING

    This type object is used to describe columns in a database that are
    string-based (e.g. CHAR1).

.. data:: BINARY

    This type object is used to describe (long) binary columns in a database
    (e.g. LONG, RAW, BLOBs).

.. data:: NUMBER

    This type object is used to describe numeric columns in a database.

.. data:: DATETIME

    This type object is used to describe date/time columns in a database.

.. data:: ROWID

    This type object is not supported in MariaDB Connector/Python and represents
    an empty set.
