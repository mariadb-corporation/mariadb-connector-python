Constants
====================

  Constants are declared in mariadb.constants module.
 
  For using constants of various types they have to be imported first:

.. code-block:: python

    from mariadb.constants import *

--------------
COMMAND
--------------

.. versionadded:: 1.1.0

   COMMAND constants are for internal use only.

--------------
CLIENT
--------------

.. versionadded:: 1.1.0

   For internal use only.

   CLIENT constants are used to check the capabilities of connected database server.

--------------
CURSOR
--------------

.. versionadded:: 1.1.0

   Cursor constants are used for server side cursors.

.. py:data:: CURSOR.NONE

   This is the default setting (no cursor)

.. py:data:: CURSOR.READ_ONLY

   Will create a server side read only cursor. The cursor is a forward cursor, which
   means it is not possible to scroll back.

--------------
FIELD_FLAG
--------------

.. versionadded:: 1.1.0

These constants represent the various field flags. As an addition
to the DBAPI 2.0 standard (PEP-249) these flags are returned as
8th element of the cursor description attribute.

.. py:data:: FIELD_FLAG.NOT_NULL

   column is defined as not NULL

.. py:data:: FIELD_FLAG.PRIMARY_KEY

   column is (part of) a primary key

.. py:data:: FIELD_FLAG.UNIQUE_KEY

   column is (part of) a unique key 

.. py:data:: FIELD_FLAG.MULTIPLE_KEY

   column is (part of) a key

.. py:data:: FIELD_FLAG.BLOB

   column contains a binary object

.. py:data:: FIELD_FLAG.UNSIGNED

   numeric column is defined as unsigned

.. py:data:: FIELD_FLAG.ZEROFILL

   column has zerofill attribute

.. py:data:: FIELD_FLAG.BINARY

   column is a binary

.. py:data:: FIELD_FLAG.ENUM

   column is defined as enum

.. py:data:: FIELD_FLAG.AUTO_INCREMENT

   column is an auto_increment column

.. py:data:: FIELD_FLAG.TIMESTAMP

   column is defined as time stamp

.. py:data:: FIELD_FLAG.SET

   column is defined as SET

.. py:data:: FIELD_FLAG.NO_DEFAULT

   column hasn't a default value

.. py:data:: FIELD_FLAG.ON_UPDATE_NOW

   column will be set to current timestamp on UPDATE

.. py:data:: FIELD_FLAG.NUMERIC

   column contains numeric value

.. py:data:: FIELD_FLAG.PART_OF_KEY

   column is part of a key

--------------
FIELD_TYPES
--------------

These constants represent the various field types. The field type
is returned as 2nd element of cursor description attribute.

.. py:data:: FIELD_TYPE.TINY

   column type is TINYINT  (1-byte integer)

.. py:data:: FIELD_TYPE.SHORT

   column type is SMALLINT (2-byte integer)

.. py:data:: FIELD_TYPE.LONG

   column tyoe is INT (4-byte integer)

.. py:data:: FIELD_TYPE.FLOAT

   column type is FLOAT (4-byte single precision)

.. py:data:: FIELD_TYPE.DOUBLE

   column type is DOUBLE (8-byte double precision)

.. py:data:: FIELD_TYPE.NULL

   column type is NULL

.. py:data:: FIELD_TYPE.TIMESTAMP

   column tyoe is TIMESTAMP

.. py:data:: FIELD_TYPE.LONGLONG

   column tyoe is BIGINT (8-byte Integer)

.. py:data:: FIELD_TYPE.INT24

   column type is MEDIUMINT (3-byte Integer)

.. py:data:: FIELD_TYPE.DATE

   column type is DATE

.. py:data:: FIELD_TYPE.TIME

   column type is TIME

.. py:data:: FIELD_TYPE.DATETIME

   column type is YEAR

.. py:data:: FIELD_TYPE.YEAR

.. py:data:: FIELD_TYPE.VARCHAR

   column type is YEAR

.. py:data:: FIELD_TYPE.BIT

   column type is BIT

.. py:data:: FIELD_TYPE.JSON

   column type is JSON

.. py:data:: FIELD_TYPE.NEWDECIMAL

   column type is DECIMAL

.. py:data:: FIELD_TYPE.ENUM

   column type is ENUM

.. py:data:: FIELD_TYPE.SET

   column type is SET

.. py:data:: FIELD_TYPE.TINY_BLOB

   column type is TINYBLOB (max. length of 255 bytes)

.. py:data:: FIELD_TYPE.MEDIUM_BLOB

   column type is MEDIUMBLOB (max. length of 16,777,215 bytes)

.. py:data:: FIELD_TYPE.LONG_BLOB

   column type is LONGBLOB (max. length 4GB bytes)

.. py:data:: FIELD_TYPE.BLOB

   column type is BLOB (max. length of 65.535 bytes)

.. py:data:: FIELD_TYPE.VAR_STRING

   column type is VARCHAR (variable length)

.. py:data:: FIELD_TYPE.STRING

   column tyoe is CHAR (fixed length)

.. py:data:: FIELD_TYPE.GEOMETRY

   column type is GEOMETRY

--------------
INDICATORS
--------------

Indicator values are used in executemany() method of cursor class to
indicate special values when connected to a MariaDB server 10.2 or newer.

.. py:data:: INDICATOR.NULL

indicates a NULL value

.. py:data:: INDICATOR.DEFAULT

indicates to use default value of column

.. py:data:: INDICATOR.IGNORE

indicates to ignore value for column for UPDATE statements.
If set, the column will not be updated.

.. py:data:: INDICATOR.IGNORE_ROW

indicates not to update the entire row.

---------------
INFO
---------------

.. versionadded:: 1.1.0

For internal use only

---------------
TPC_STATE
---------------

.. versionadded:: 1.1.0

For internal use only

---------------
STATUS
---------------
.. versionadded:: 1.1.0

The STATUS constants are used to check the server status of
the current connection.

  Example:

  .. code-block:: python

      cursor.callproc("my_storedprocedure", (1,"foo"))

      if (connection.server_status & STATUS.SP_OUT_PARAMS):
          print("retrieving output parameters from store procedure")
          ...
      else:
          print("retrieving data from stored procedure")
          ....
      

.. py:data:: STATUS.IN_TRANS

   Pending transaction

.. py:data:: STATUS.AUTOCOMMIT

   Server operates in autocommit mode

.. py:data:: STATUS.MORE_RESULTS_EXIST

   The result from last executed statement contained two or more result
   sets which can be retrieved by cursors nextset() method.

.. py:data:: STATUS.QUERY_NO_GOOD_INDEX_USED

   The last executed statement didn't use a good index.

.. py:data:: STATUS.QUERY_NO_INDEX_USED

   The last executed statement didn't use an index.

.. py:data:: STATUS.CURSOR_EXISTS

   The last executed statement opened a server side cursor.

.. py:data:: STATUS.LAST_ROW_SENT

   For server side cursors this flag indicates end of a result set.

.. py:data:: STATUS.DB_DROPPED

   The current database in use was dropped and there is no default
   database for the connection anymore.

.. py:data:: STATUS.NO_BACKSLASH_ESCAPES

   Indicates that SQL mode NO_BACKSLASH_ESCAPE is active, which means
   that the backslash character '\' becomes an ordinary character.

.. py:data:: STATUS.QUERY_WAS_SLOW

   The previously executed statement was slow (and needs to be optimized).

.. py:data:: STATUS.PS_OUT_PARAMS

   The current result set contains output parameters of a stored procedure.

.. py:data:: STATUS.SESSION_STATE_CHANGED

   The session status has been changed.

.. py:data:: STATUS.ANSI_QUOTES

   SQL mode ANSI_QUOTES is active,
