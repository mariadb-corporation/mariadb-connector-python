.. _extensions:

Extensions to the DB API
========================

.. sectionauthor:: Georg Richter <georg@mariadb.com>

Constants
---------
For using constants of various types they have to be imported first:

.. code-block:: python

    from mariadb.constants import *


Cursor types
^^^^^^^^^^^^

MariaDB Connector/Python defines the following cursor types for server side cursors:

.. data:: mariadb.constants.CURSOR.NONE

    Don't use a server side cursor (default)

.. data:: mariadb.constants.CURSOR.READ_ONLY

    Use a read-only server side cursor.

Indicators
^^^^^^^^^^

Indicators hold supplementary information when you are modify (insert/update/delete) data with cursors `executemany` method. There are several distinct uses for indicator variables: 

.. data:: INDICATOR.NULL

    A null value will be inserted or updated

.. data:: INDICATOR.DEFAULT

    The default value of a column will be inserted or updated

.. data:: INDICATOR.IGNORE

    Don't update column at all

.. data:: INDICATOR.IGNORE_ROW

    Don't update or delete row

Capability flags
^^^^^^^^^^^^^^^^

These flags are used when establishing a connection or to check if the database is
capabable of a certain feature.

.. data:: CLIENT.MYSQL

    not in use/supported by MariaDB Server

.. data:: CLIENT.FOUND_ROWS

    return the number of matched rows instead of number of changed rows

.. data:: CLIENT.NO_SCHEMA

    forbids the use of database.tablename.columnname syntax and forces SQL parser
    to generate an error.

.. data:: CLIENT.LOCAL_FILES

    Allows LOAD DATA LOCAL INFILE statements (if not disabled on server).

.. data:: CLIENT_COMPRESS

    Use compressed protocol

.. data:: CLIENT_IGNORE_SPACE

    Allows spaces after function names. This implies, that all function names will
    become reserved words.

.. data:: CLIENT_MULTI_RESULZS

    Indicates that the client is able to handle multiple result sets.

