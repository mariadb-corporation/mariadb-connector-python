Release history
===============

MariaDB Connector/Python 1.0.7
------------------------------

Release date: Jun 8 2021

Issues fixed:
^^^^^^^^^^^^^

- CONPY-155: fixed crash in get_server_version method of connection class
- CONPY-144: fixed crash in connection pool
- CONPY-150: convert invalid date types (day, month or year=0) to NULL 

MariaDB Connector/Python 1.0.6
------------------------------

Release date: Feb 24 2021

Issues fixed:
^^^^^^^^^^^^^

- CONC-142: Fixed memory leak in connection class (server_version_info)
- CONC-138, CONC-141: When using binary protocol, convert data to binary object only if the character set is BINARY (63), not if the flag was set and character set is a non binary character set.
- Various build and travis related corrections/fixes. 

MariaDB Connector/Python 1.0.5
------------------------------

Release date: Nov 25th 2020

Notable changes:
^^^^^^^^^^^^^^^^

- CONPY-127: When establishing a new database connection the connect method now also supports None values instead of strings only.
- CONPY-128: Added connection attribute server_version_info and (for compatibility) get_server_version() method. Both return a tuple, describing the version number of connected server in following format: (MAJOR_VERSION, MINOR_VERSION, PATCH_VERSION)
- CONPY-133: The internal parser now supports the full MariaDB comment syntax 

Issues fixed:
^^^^^^^^^^^^^

- CONPY-126: Fixed memory leak in connection object
- CONPY-130: Fixed DeprecationWarning: builtin type Row has no module attribute
- CONPY-131: Fixed crash type_traverse() called for non-heap type Row (Python 3.6 only)
- CONPY-132: Fixed memory leak in connection pool 

MariaDB Connector/Python 1.0.4
------------------------------

Release date: Oct 20th 2020

Notable changes:
^^^^^^^^^^^^^^^^

Binary wheel packages are now availble for Windows on http://pypi.org

Issues fixed:
^^^^^^^^^^^^^

- CONPY-123: Free pending result sets when closing cursor
- CONPY-124: Fix build when building against Connector/C < 3.1.8
- CONPY-125: Build fix: replace obsolete ULONG_LONG_MAX definitions

MariaDB Connector/Python 1.0.3
------------------------------

Release date: Oct 7th 2020

Notable changes:
^^^^^^^^^^^^^^^^

- CONPY-117: Added support for data type conversion.

Issues fixed:
^^^^^^^^^^^^^

- CONPY-116: Wrong type reporting for column type MYSQL_TYPE_JSON
- CONPY-118: Removed statement allocation for text protocol
- CONPY-119: Fixed memory leak when cursor result is dictionary

MariaDB Connector/Python 1.0.2
------------------------------

Release date: Sept 18th 2020

Issues fixed:
^^^^^^^^^^^^^

- Fixed datetime initialization
- CONPY-108: Fixed memory leak
- CONPY-110: Fixed memory overrun when passing ssl keyword to connect() method.

MariaDB Connector/Python 1.0.1
------------------------------

Release date: August 18th 2020

Notable changes:
^^^^^^^^^^^^^^^^

- CONPY-100: added binary option for cursor which allows to use binary protocol without passing parameters
- CONPY-102: Default for autocommit is now off
- CONPY-105: Behavior of rowcount and lastrowid atttributes now conforms to PEP-249

Issues fixed:
^^^^^^^^^^^^^

- CONPY-82: Unlock mutex in case of ConnectionPool.add_connection failed
- CONPY-83: Fixed missing reference increment in ConnectionPool class
- CONPY-85: Fixed version checking in setup.py
- CONPY-93: Release GIL before calling Python's memory allocation routine
- CONPY-94: Support python subclasses for data binding 
- CONPY-95: Added support for MYSQL_TYPE_BIT column type
- CONPY-98: Return binary object when casting to binary
- CONPY-99: Fixed memory leak in fetchall() method.
- CONPY-101: Fixed negative reference count when using callproc() method.
- CONPY-106: exception handling: type of exception depends now on error code instead of sqlstate
- CONPY-107: convert negative time values to datetime.timedelta instances

MariaDB Connector/Python 1.0.0
------------------------------

Release date: June 24th 2020

Issues fixed:
^^^^^^^^^^^^^

- CONPY-69: Set default character set (utf8mb4) with authentication packet 
- CONPY-70: set_config() method needs to check the passed parameter and raise an exception if the parameter type is not a dictionary.
- CONPY-72: When deallocating the connection pool class, we need to check beside pool_size if the array containing the connections is valid.
- CONPY-76: Added aliases username, passwd and db to connection keywords.
- CONPY-78: Since MaxScale doesn't support bulk operations yet, we have to check servers extended capability flag to determine if this feature is supported or not.
- CONPY-79: When inserting NULL values with executemany() method on a server which doesn't support BULK statements NULL values weren't inserted correctly.
- CONPY-80: Parameters in set_config() method of ConnectionPool class have to be checked against the list of DSN keywords
- CONPY-81: Fixed crash when switching between text and binary protocol with same cursor
- Fixed bug when inserting negative integer values with cursor.execute() method
