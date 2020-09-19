.. _extensions:

Extensions to the DB API
========================

.. sectionauthor:: Georg Richter <georg@mariadb.com>

Constants
---------
For using constants of various types they have to be imported first:

.. code-block:: python

    from mariadb.constants import *


Cursor
^^^^^^

MariaDB Connector/Python defines the following cursor types for server side cursors:

.. data:: mariadb.constants.CURSOR.NONE

    Don't use a server side cursor (default)

.. data:: mariadb.constants.CURSOR.READ_ONLY

    Use a read-only server side cursor.

Indicators
^^^^^^^^^^

Indicators hold supplementary information when you are modify (insert/update/delete) data with cursors `executemany` method. There are several distinct uses for indicator variables: 

.. data:: mariadb.constants.INDICATOR.NULL

    A null value will be inserted or updated

.. data:: mariadb.constants.INDICATOR.DEFAULT

    The default value of a column will be inserted or updated

.. data:: mariadb.constants.INDICATOR.IGNORE

    Don't update column at all

.. data:: mariadb.constants.INDICATOR.IGNORE_ROW

    Don't update or delete row

Capability flags
^^^^^^^^^^^^^^^^

These flags are used when establishing a connection or to check if the database is
capabable of a certain feature.

.. data:: mariadb.constants.CLIENT.MYSQL

    not in use/supported by MariaDB Server

.. data:: mariadb.constants.CLIENT.FOUND_ROWS

    return the number of matched rows instead of number of changed rows

.. data:: mariadb.constants.CLIENT.NO_SCHEMA

    forbids the use of database.tablename.columnname syntax and forces SQL parser
    to generate an error.

.. data:: mariadb.constants.CLIENT.LOCAL_FILES

    Allows LOAD DATA LOCAL INFILE statements (if not disabled on server).

.. data:: mariadb.constants.CLIENT.COMPRESS

    Use compressed protocol

.. data:: mariadb.constants.CLIENT.IGNORE_SPACE

    Allows spaces after function names. This implies, that all function names will
    become reserved words.

.. data:: mariadb.constants.CLIENT.MULTI_RESULTS

    Indicates that the client is able to handle multiple result sets.

Field types
^^^^^^^^^^^

.. data:: mariadb.constants.FIELD_TYPE.DECIMAL

   Old decimal format: Not in use anymore, instead of use NEWDECIMAL.

.. data:: mariadb.constants.FIELD_TYPE.TINY

   Represents SQL type TINYINT

.. data:: mariadb.constants.FIELD_TYPE.SHORT

   Represents SQL type SMALLINT

.. data:: mariadb.constants.FIELD_TYPE.LONG

   Represents SQL type INT

.. data:: mariadb.constants.FIELD_TYPE.FLOAT

   Represents SQL type FLOAT

.. data:: mariadb.constants.FIELD_TYPE.DOUBLE

   Represents SQL type DOUBLE

.. data:: mariadb.constants.FIELD_TYPE.NULL

   Represents SQL type NULL

.. data:: mariadb.constants.FIELD_TYPE.TIMESTAMP

   Represents SQL type TIMESTAMP

.. data:: mariadb.constants.FIELD_TYPE.LONGLONG

   Represents SQL type BIGINT

.. data:: mariadb.constants.FIELD_TYPE.INT24

   Represents SQL type MEDIUMINT

.. data:: mariadb.constants.FIELD_TYPE.DATETIME

   Represents SQL type DATETIME

.. data:: mariadb.constants.FIELD_TYPE.YEAR

   Represents SQL type YEAR

.. data:: mariadb.constants.FIELD_TYPE.NEWDATE

   Represents SQL type DATE

.. data:: mariadb.constants.FIELD_TYPE.VARCHAR

   Represents SQL type VARCHAR

.. data:: mariadb.constants.FIELD_TYPE.BIT

   Represents SQL type BIT

.. data:: mariadb.constants.FIELD_TYPE.JSON

   Represents SQL type JSON

.. data:: mariadb.constants.FIELD_TYPE.NEWDECIMAL

   Represents SQL type DECIMAL

.. data:: mariadb.constants.FIELD_TYPE.ENUM

   Represents SQL type ENUM

.. data:: mariadb.constants.FIELD_TYPE.SET

   Represents SQL type SET

.. data:: mariadb.constants.FIELD_TYPE.TINY_BLOB

   Represents SQL type TINYBLOB or TINYTEXT

.. data:: mariadb.constants.FIELD_TYPE.MEDIUM_BLOB

   Represents SQL type MEDIUMBLOB or MEDIUMTEXT

.. data:: mariadb.constants.FIELD_TYPE.LONG_BLOB

   Represents SQL type LONGBLOB or LONGTEXT

.. data:: mariadb.constants.FIELD_TYPE.BLOB

   Represents SQL type BLOB or TEXT

.. data:: mariadb.constants.FIELD_TYPE.GEOMETRY

   Represents SQL type GEOMETRY
