The cursor class
====================

.. sectionauthor:: Georg Richter <georg@mariadb.com>

.. class:: cursor

    Cursors can be used to execute SQL commands within a database session. Cursors
    objects are created by the connection.cursor() method.

    Cursors are bound to the connection for their entire lifetime. If a connection was
    closed or dropped all cursor objects bound to this connection became invalid.

    To check if a cursor is still valid, the *close* attribute needs to be checked.

--------------
Cursor methods
--------------

.. method:: execute(statement[, data [, \*\*kwargs]])
       
   Parameters in SQL statement may be provided as sequence or mapping and will be bound
   to variables in the operation. Variables are specified as question
   marks (paramstyle='qmark'), however for compatibility reasons |MCP|
   also supports the 'format' and 'pyformat' paramstyles
   with the restriction, that different paramstyles can't be mixed within.
   a statement

   A reference to the operation will be retained by the cursor.
   If the cursor was created with attribute prepared=True the statement
   string for following execute operations will be ignored:
   This is most effective for algorithms where the same operation is used,
   but different parameters are bound to it (many times).

   By default result sets will not be buffered, so further operations on the
   same connection will fail, unless the entire result set was read. For buffering
   the entire result set an additional parameter *buffered=True* must be specified.

.. method:: callproc(procedure_name, args=())

   Executes a stored procedure. The args sequence must contain an entry for
   each parameter the procedure expects.
   Input/Output or Output parameters have to be retrieved by .fetch methods,
   the .sp_outparams attribute indicates if the result set contains output
   parameters.
   
   Example::
   
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

.. method:: executemany(statement, data)
   
   Exactly behaves like .execute() but accepts a list of tuples, where each
   tuple represents data of a row within a table.
   .executemany() only supports DML (insert, update, delete) statements.
   
   The following example will insert 3 rows:::
   
       data= [
          (1, 'Michael', 'Widenius')
          (2, 'Diego', 'Dupin')
          (3, 'Lawrin', 'Novitsky')
       ]
       cursor.execute("INSERT INTO colleagues VALUES (?, ?, ?)", data)

   .. note::
      Indicator objects can only be used when connecting to a MariaDB Server 10.2 or
      newer. Older versions of MariaDB and MySQL servers don't support this feature.

.. method:: fetchall()

   Fetches all rows of a pending result set and returns a list of tuples.

   If the cursor was created with option *named_tuple=True* the result will be a list of named tuples.

.. method:: fetchmany(size)

   Fetch the next set of rows of a query result, returning a list of tuples
   An empty list is returned when no more rows are available.
   
   The number of rows to fetch per call is specified by the *size* parameter.
   If it is not given, the cursor's arraysize determines the number of
   rows to be fetched.

   If the cursor was created with option *named_tuple=True* the result will be a list of named tuples.

.. method:: fetchone()

   Fetches next row of a pending result set and returns a tuple.

   If the cursor was created with option *named_tuple=True* the result will be a named tuple.

.. method:: fieldcount()

   Returns the number of fields (columns) within a result set.

.. method:: next()

   Return the next row from the currently executing SQL statement
   using the same semantics as fetchone().

.. method:: nextset()

   Will make the cursor skip to the next available result set,
   discarding any remaining rows from the current set.

.. method:: scroll(value[, mode='relative'])

   Scroll the cursor in the result set to a new position according to mode.
   
   If mode is relative, value is taken as offset to the current
   position in the result set, if set to absolute (defult), value states an absolute
   target position.

.. method: setinputsizes()

   Required by PEP-249. Does nothing in MariaDB Connector/Python

.. method: setoutputsize()

   Required by PEP-249. Does nothing in MariaDB Connector/Python

-----------------
Cursor attributes
-----------------

.. data:: arraysize

   This read/write attribute specifies the number of rows to fetch at a time with .fetchmany(). It defaults to 1 meaning to fetch a single row at a time

.. data:: buffered

   When set to *True* all result sets are immediately transferred and the connection
   between client and server is no longer blocked. Default value is False.

.. data:: closed

   Indicates if the cursor is closed (e.g. if connection dropped) and can't be reused.

.. data:: connection

   Returns a reference to the connection object on which the cursor was created.

.. data:: description

   This read-only attribute is a sequence of 7-item sequences.

   Each of these sequences contains information describing one result column:

   - name
   - type_code
   - display_size
   - internal_size
   - precision
   - scale
   - null_ok
  
   This attribute will be None for operations that do not return rows or if the cursor has
   not had an operation invoked via the .execute*() method yet 

.. data:: lastrowid

   This read only attribute of the ID generated by a query on a table with a column having
   the AUTO_INCREMENT attribute or the value for the last usage of
   LAST_INSERT_ID(expr). If the last query wasn't an INSERT or UPDATE
   statement or if the modified table does not have a column with the
   AUTO_INCREMENT attribute and LAST_INSERT_ID was not used, the returned
   value will be zero

.. data:: sp_outparams

   This read-only attribute undicates if the current result set contains inout
   or out parameters from a previously executed stored procedure.

.. data:: rowcount

   This read-only attribute specifies the number of rows that the last
   execute*() produced (for DQL statements like SELECT) or affected
   (for DML statements like UPDATE or INSERT).
   The return value is -1 in case no .execute*() has been performed
   on the cursor or the rowcount of the last operation cannot be
   determined by the interface.

.. data:: statement

   This ready only attribute returns the last executed SQL statement.

.. data:: warnings

   Returns the number of warnings from the last executed statement, or zero
   if there are no warnings.
   
   .. note::

       If SQL_MODE TRADITIONAL is enabled an error instead of a warning will be
       returned. To retrieve warnings use the cursor method execute("SHOW WARNINGS").
