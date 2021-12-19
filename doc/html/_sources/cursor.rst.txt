The cursor class
====================
.. sectionauthor:: Georg Richter <georg@mariadb.com>

.. autoclass:: mariadb.cursors.Cursor 

--------------
Cursor methods
--------------

.. automethod:: mariadb.cursors.Cursor.callproc

  Example:

  .. code-block:: python 

    >>>cursor.execute("CREATE PROCEDURE p1(IN i1 VAR  CHAR(20), OUT o2 VARCHAR(40))"
                      "BEGIN"
                      "  SELECT 'hello'"
                      "  o2:= 'test'"
                      "END")
    >>>cursor.callproc('p1', ('foo', 0))
    >>> cursor.sp_outparams
    False
    >>> cursor.fetchone()
    ('hello',)
    >>> cursor.nextset()
    True
    >>> cursor.sp_outparams
    True
    >>> cursor.fetchone()
    ('test',)

.. automethod:: mariadb.cursors.Cursor.execute

.. automethod:: mariadb.cursors.Cursor.executemany
   
  Example:

  The following example will insert 3 rows:

  .. code-block:: python 

    data= [
        (1, 'Michael', 'Widenius')
        (2, 'Diego', 'Dupin')
        (3, 'Lawrin', 'Novitsky')
    ]
    cursor.executemany("INSERT INTO colleagues VALUES (?, ?, ?)", data)

  To insert special values like NULL or a column default, you need to specify indicators:

  - INDICATOR.NULL is used for NULL values
  - INDICATOR.IGNORE is used to skip update of a column.
  - INDICATOR.DEFAULT is used for a default value (insert/update)
  - INDICATOR.ROW is used to skip update/insert of the entire row.

  .. note::

    - All values for a column must have the same data type.
    - Indicators can only be used when connecting to a MariaDB Server 10.2 or newer. MySQL servers don't support this feature.


.. automethod:: mariadb.cursors.Cursor.fetchall

.. automethod:: mariadb.cursors.Cursor.fetchmany

.. automethod:: mariadb.cursors.Cursor.fetchone

.. automethod:: mariadb.cursors.Cursor.next

.. automethod:: mariadb.cursors.Cursor.nextset

.. automethod:: mariadb.cursors.Cursor.scroll

.. automethod:: mariadb.cursors.Cursor.setinputsizes()

.. automethod:: mariadb.cursors.Cursor.setoutputsize()

-----------------
Cursor attributes
-----------------

.. autoattribute:: mariadb.cursors.Cursor.arraysize

  This read/write attribute specifies the number of rows to fetch at a time with .fetchmany(). It defaults to 1 meaning to fetch a single row at a time

.. autoattribute:: mariadb.cursors.Cursor.buffered

.. autoattribute:: mariadb.cursors.Cursor.closed

.. autoattribute:: mariadb.cursors.Cursor.connection

.. autoattribute:: mariadb.cursors.Cursor.description

  .. note::

    The 8th parameter 'field_flags' is an extension to the PEP-249 DB API standard.
    In combination with the type element field, it can be determined for example,
    whether a column is a BLOB or TEXT field:

  .. code-block:: python

    if cursor.description[0][1] == FIELD_TYPE.BLOB:
        if cursor.description[0][7] == FIELD_FLAG.BINARY:
            print("column is BLOB")
        else:
            print("column is TEXT") 
   

.. autoattribute:: mariadb.cursors.Cursor.lastrowid

.. autoattribute:: mariadb.cursors.Cursor.sp_outparams


.. versionadded:: 1.1.0

.. autoattribute:: mariadb.cursors.Cursor.paramcount

.. autoattribute:: mariadb.cursors.Cursor.rowcount

  .. note::

    For unbuffered cursors (default) the exact number of rows can only be 
    determined after all rows were fetched.

  Example:

  .. code-block:: python

    >>> cursor=conn.cursor()
    >>> cursor.execute("SELECT 1")
    >>> cursor.rowcount
    -1
    >>> rows= cursor.fetchall()
    >>> cursor.rowcount
    1
    >>> cursor=conn.cursor(buffered=True)
    >>> cursor.execute("SELECT 1")
    >>> cursor.rowcount
    1

.. autoattribute:: mariadb.cursors.Cursor.statement

.. autoattribute:: mariadb.cursors.Cursor.warnings

  .. note::

    Warnings can be retrieved by the show_warnings() method of connection class.
