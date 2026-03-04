# Release history

## MariaDB Connector/Python 2.0.0rc2

Release date: Mar. 2026

**Notable changes:**

- [CONPY-2](https://jira.mariadb.org/browse/CONPY-2): Asynchronous support
- [CONPY-324](https://jira.mariadb.org/browse/CONPY-324): Enhanced Python Connector Distribution
- [CONPY-325](https://jira.mariadb.org/browse/CONPY-325): Add Type Hints to MariaDB Python Connector
- [CONPY-326](https://jira.mariadb.org/browse/CONPY-326): Add Connection URI Support to MariaDB Python Connector
- [CONPY-327](https://jira.mariadb.org/browse/CONPY-327): Asynchronous support for C implementation
- [CONPY-333](https://jira.mariadb.org/browse/CONPY-333): C implementation: columns metadata reading
- [CONPY-338](https://jira.mariadb.org/browse/CONPY-338): Unify binary protocol use
- [CONPY-335](https://jira.mariadb.org/browse/CONPY-335): Metadata: Store metadata as an object of arrays instead of an array of objects


## MariaDB Connector/Python 1.1.14

Release date: Oct 10 2025

**Bug fixes:**

- [CONPY-318](https://jira.mariadb.org/browse/CONPY-318): Segfault appears on mariadb-connector 1.1.13
- [CONPY-321](https://jira.mariadb.org/browse/CONPY-321): Exception handler in ConnectionPool.__init__ does not close all open connections and raises IndexError

## MariaDB Connector/Python 1.1.13

Release date: Jul 7 2025

## Notable changes

- If a cursor will be reused, methods execute(), executemany() and callproc() will aways reset the cursor to avoid possible memory leaks
- Fixed various memory leaks in unittest suite

## Bug fixes

* [CONPY-313](https://jira.mariadb.org/browse/CONPY-313): Raise NotSupportedError for unsupported float and Decimal values like "nan" and "inf"
* [CONPY-300](https://jira.mariadb.org/browse/CONPY-306): Fix crash when getting invalid unicode from server
* [CONPY-314](https://jira.mariadb.org/browse/CONPY-306): Always use binary protocol for callproc() method


## MariaDB Connector/Python 1.1.12

Release date: Feb 24 2025

**Notable changes:**
- [CONPY-299](https://jira.mariadb.org/browse/CONPY-299): Added support for VECTOR: Vectors can be directly used in parameters as float arrays without using tobytes() method or SQL Function Vec_FromText()

**Issues fixed:**

- [CONPY-295](https://jira.mariadb.org/browse/CONPY-295): Fix unsigned check when using executemany() method
- [CONPY-300](https://jira.mariadb.org/browse/CONPY-300): Documentation fix (ConnectionPool)
- [CONPY-302](https://jira.mariadb.org/browse/CONPY-302): Fix segfault when using threads()
- Fixed exception type for ER_BAD_FIELD_ERROR (now OperationalError instead of ProgrammingError)

## MariaDB Connector/Python 1.1.11

Release date: Nov 14 2024

**Issues fixed:**

- [CONPY-283](https://jira.mariadb.org/browse/CONPY-283): Incorrect result format after cursor.scroll()
- [CONPY-289](https://jira.mariadb.org/browse/CONPY-289): BIGINT out of range on bulk insert
- [CONPY-293](https://jira.mariadb.org/browse/CONPY-293): Fix gcc warnings

**Notable changes:**
- Added new connection attribute tls_peer_cert_info
- Added support for MariaDB Connector/C 3.4

## MariaDB Connector/Python 1.1.10

Release date: Feb 07 2024

**Issues fixed:**

- [CONPY-273](https://jira.mariadb.org/browse/CONPY-273): cursor.execute fails when running in sql_mode ANSI_QUOTES.
- [CONPY-278](https://jira.mariadb.org/browse/CONPY-278): Return updated connection_id in case of automatic reconnect
- [CONPY-279](https://jira.mariadb.org/browse/CONPY-279): Allow None values for password and database in change_user() method
- [CONPY-281](https://jira.mariadb.org/browse/CONPY-281): Use METH_O calling conventions for c functions which accept only one parameter

## MariaDB Connector/Python 1.1.9

Release date: Dec 22 2023

**Issues fixed:**

- [CONPY-273](https://jira.mariadb.org/browse/CONPY-273): Fixed crash in escape_string method (debug)
- [CONPY-274](https://jira.mariadb.org/browse/CONPY-274): Instead of releasing non freed objects (cursor and connection) in tp_dealloc, they are freed now in tp_finalize to avoid possible crashes
- [CONPY-276](https://jira.mariadb.org/browse/CONPY-276): Allow to retrieve data from buffered cursor if the connection was already closed before

## MariaDB Connector/Python 1.1.8

Release date: Oct 12 2023

**Notable changes:**

- [CONPY-271](https://jira.mariadb.org/browse/CONPY-271): Cusor object provides now a metadata attribute, which returns resultset metadata as a dictionary.  metadata attribute also contains information about extended field types like JSON, UUID, INET4/6 and geometry types.
- Added new constants mariadb.constants.EXT_FIELD_TYPE which describe extended field types.

**Issues fixed:**

- [CONPY-270](https://jira.mariadb.org/browse/CONPY-270): Data will be converted to Binary only if the character set is binary, the BINARY_FLAG will be ignored.
- [CONPY-269](https://jira.mariadb.org/browse/CONPY-269): If cursors rowcount attribute will be retrieved after the cursor was closed, rowcount now returns -1 instead of raising an exception. This is a workaround for a pandas bug.

## MariaDB Connector/Python 1.1.7

Release date: Jul 5 2023

**Notable changes:**

- [CONPY-253](https://jira.mariadb.org/browse/CONPY-253): The connection method now offers the option of specifying the version of the TLS protocol using tls_version.

**Issues fixed:**

- [CONPY-258](https://jira.mariadb.org/browse/CONPY-258): Fixed ValueError exception if ZEROFILL flag is defined.
- [CONPY-256](https://jira.mariadb.org/browse/CONPY-256): Fix indexing when moving a free connection to used connections to avoid returning the same connection twice. Kudos and thanks to G.Mech for reporting this bug and providing the fix.
- [CONPY-255](https://jira.mariadb.org/browse/CONPY-255): If all connections from a pool are in use, pool.get_connection now returns None instead of raising an exception.

## MariaDB Connector/Python 1.1.6

Release date: Feb 20 2023

**Notable changes:**

- [CONPY-247](https://jira.mariadb.org/browse/CONPY-247): Added optional parameter “pool_invalidation_interval”, which specifies the validation interval in milliseconds after which the status of a connection requested from the pool is checked. The default values is 500 milliseconds, a value of 0 means that the status will always be checked.

**Issues fixed:**

- [CONPY-251](https://jira.mariadb.org/browse/CONPY-251): Check if stmt was already initialized in cursor nextset() method.
- [CONPY-250](https://jira.mariadb.org/browse/CONPY-250): Fixed calculation of connection pool size
- [CONPY-248](https://jira.mariadb.org/browse/CONPY-248): Replace broken connections in connection pool
- [CONPY-246](https://jira.mariadb.org/browse/CONPY-246): Rollback transaction if connection pool was created without pool_reset_connection option.
- [CONPY-245](https://jira.mariadb.org/browse/CONPY-245): Implementation of LRU cache in connection pool.
- [CONPY-240](https://jira.mariadb.org/browse/CONPY-240): Don’t overwrite errormessage/stacktrace if an exception was generated during module initialization.

## MariaDB Connector/Python 1.1.5

Release date: Nov 7 2022

**Notable changes:**

- Since Connector/C 3.2 is discontinued, minimum required version for MariaDB Connector/Python 1.1.5 is Connector/C 3.3.1
- [CONPY-220](https://jira.mariadb.org/browse/CONPY-220): Added \_get_socket() method
- Performance improvement: Instead of iterating via fetchone(), fetchall() and fetchmany() methods now load the data directly at once.

**Issues fixed:**

- [CONPY-222](https://jira.mariadb.org/browse/CONPY-222): Removed del() method from cursor
- [CONPY-224](https://jira.mariadb.org/browse/CONPY-224): Fixed bulk_operation when reexecuted using same cursor
- [CONPY-225](https://jira.mariadb.org/browse/CONPY-225): Fixed cursor.affected_rows property
- [CONPY-226](https://jira.mariadb.org/browse/CONPY-226): Replaced deprecated distutils (PEP-632)
- [CONPY-227](https://jira.mariadb.org/browse/CONPY-227): Replaced collections.named_tuple by PyStruct_Sequence (C-Python)
- .conpy:228: Fixed Installation error (if C/C version < 3.2.4 was found)
- .conpy:229: Converter: added missing support for None conversions
- .conpy:231: Fixed memory leak

## MariaDB Connector/Python 1.1.4

Release date: Aug 10 2022

**Issues fixed:**

- [CONPY-217](https://jira.mariadb.org/browse/CONPY-217): Added reconnect keyword for connection
- Added CAPABILITY constants
- Code styling fixes (flake8)
- [CONPY-218](https://jira.mariadb.org/browse/CONPY-218): Allow None as data parameter in cursor->execute(). Kudos to Luciano Barcaro for providing a fix
- [CONPY-214](https://jira.mariadb.org/browse/CONPY-214): Replaced cursor iterator by native Python iter() method.

## MariaDB Connector/Python 1.1.3

Release date: Jul 07 2022

**Issues fixed:**

> - [CONPY-209](https://jira.mariadb.org/browse/CONPY-209): Wrong unicode substitution in SELECT statement
> - [CONPY-210](https://jira.mariadb.org/browse/CONPY-210): Added missing error constants
> - [CONPY-212](https://jira.mariadb.org/browse/CONPY-212): unbuffered cursor.execute() doesn’t work

## MariaDB Connector/Python 1.1.2

Release date: Jun 27 2022

**Notable changes:**

> - [CONPY-203](https://jira.mariadb.org/browse/CONPY-203): Error constants added
> - [CONPY-204](https://jira.mariadb.org/browse/CONPY-204): New connection method dump_debug_info(

**Issues fixed:**

> Removed utf8 part of internal parser and use binary objects for parameter substitution
> - [CONPY-205](https://jira.mariadb.org/browse/CONPY-205): Fixed inconsistent exceptions: All parameter exceptions are returned as ProgrammingError.
    > Fixed memory leak when using decimal parameters
> - [CONPY-201](https://jira.mariadb.org/browse/CONPY-201): Fixed build issues with Python 3.11 beta

## MariaDB Connector/Python 1.0.11

Release date: Apr 12 2022

**Issues fixed:**

> - [CONPY-194](https://jira.mariadb.org/browse/CONPY-194): executemany() does not work with returning clause
> - [CONPY-196](https://jira.mariadb.org/browse/CONPY-196): Missing decrement of reference pointer when closing cursor
> - [CONPY-198](https://jira.mariadb.org/browse/CONPY-198): Build fix for FreeBSD

## MariaDB Connector/Pyhon 1.0.10

Release date: Feb 18 2022

**Issues fixed:**

- - [CONPY-184](https://jira.mariadb.org/browse/CONPY-184): Display status of connection, cursor and pool class in string representation.
- - [CONPY-178](https://jira.mariadb.org/browse/CONPY-178): Repeated execution of cursors callproc() method hangs
- - [CONPY-175](https://jira.mariadb.org/browse/CONPY-175): Fixed crash in escape_string

## MariaDB Connector/Python 1.0.9

Release date: Dec 21 2021

**Issues fixed:**

- [CONPY-184](https://jira.mariadb.org/browse/CONPY-184): Display status of connection, cursor and pool class in string representation.
- [CONPY-178](https://jira.mariadb.org/browse/CONPY-178): Repeated execution of cursors callproc() method hangs
- [CONPY-175](https://jira.mariadb.org/browse/CONPY-175): Fixed crash in escape_string

## MariaDB Connector/Python 1.0.8

Release date: Oct 22 2021

**Issues fixed:**

- [CONPY-173](https://jira.mariadb.org/browse/CONPY-173): Fixed windows build for Python 3.10

## MariaDB Connector/Python 1.0.7

Release date: Jun 8 2021

**Issues fixed:**

- [CONPY-155](https://jira.mariadb.org/browse/CONPY-155): fixed crash in get_server_version method of connection class
- [CONPY-144](https://jira.mariadb.org/browse/CONPY-144): fixed crash in connection pool
- [CONPY-150](https://jira.mariadb.org/browse/CONPY-150): convert invalid date types (day, month or year=0) to NULL

## MariaDB Connector/Python 1.0.6

Release date: Feb 24 2021

**Issues fixed:**

- [CONPY-142](https://jira.mariadb.org/browse/CONPY-142): Fixed memory leak in connection class (server_version_info)
- [CONPY-138](https://jira.mariadb.org/browse/CONPY-138), [CONPY-141](https://jira.mariadb.org/browse/CONPY-141): When using binary protocol, convert data to binary object only if the character set is BINARY (63), not if the flag was set and character set is a non binary character set.
- Various build and travis related corrections/fixes.

## MariaDB Connector/Python 1.0.5

Release date: Nov 25th 2020

**Notable changes:**

- [CONPY-127](https://jira.mariadb.org/browse/CONPY-127): When establishing a new database connection the connect method now also supports None values instead of strings only.
- [CONPY-128](https://jira.mariadb.org/browse/CONPY-128): Added connection attribute server_version_info and (for compatibility) get_server_version() method. Both return a tuple, describing the version number of connected server in following format: (MAJOR_VERSION, MINOR_VERSION, PATCH_VERSION)
- [CONPY-133](https://jira.mariadb.org/browse/CONPY-133): The internal parser now supports the full MariaDB comment syntax

**Issues fixed:**

- [CONPY-126](https://jira.mariadb.org/browse/CONPY-126): Fixed memory leak in connection object
- [CONPY-130](https://jira.mariadb.org/browse/CONPY-130): Fixed DeprecationWarning: builtin type Row has no module attribute
- [CONPY-131](https://jira.mariadb.org/browse/CONPY-131): Fixed crash type_traverse() called for non-heap type Row (Python 3.6 only)
- [CONPY-132](https://jira.mariadb.org/browse/CONPY-132): Fixed memory leak in connection pool

## MariaDB Connector/Python 1.0.4

Release date: Oct 20th 2020

**Notable changes:**

Binary wheel packages are now availble for Windows on [http://pypi.org](http://pypi.org)

**Issues fixed:**

- [CONPY-123](https://jira.mariadb.org/browse/CONPY-123): Free pending result sets when closing cursor
- [CONPY-124](https://jira.mariadb.org/browse/CONPY-124): Fix build when building against Connector/C < 3.1.8
- [CONPY-125](https://jira.mariadb.org/browse/CONPY-125): Build fix: replace obsolete ULONG_LONG_MAX definitions

## MariaDB Connector/Python 1.0.3

Release date: Oct 7th 2020

**Notable changes:**

- [CONPY-117](https://jira.mariadb.org/browse/CONPY-117): Added support for data type conversion.

**Issues fixed:**

- [CONPY-116](https://jira.mariadb.org/browse/CONPY-116): Wrong type reporting for column type MYSQL_TYPE_JSON
- [CONPY-118](https://jira.mariadb.org/browse/CONPY-118): Removed statement allocation for text protocol
- [CONPY-119](https://jira.mariadb.org/browse/CONPY-119): Fixed memory leak when cursor result is dictionary

## MariaDB Connector/Python 1.0.2

Release date: Sept 18th 2020

**Issues fixed:**

- Fixed datetime initialization
- [CONPY-108](https://jira.mariadb.org/browse/CONPY-108): Fixed memory leak
- [CONPY-110](https://jira.mariadb.org/browse/CONPY-110): Fixed memory overrun when passing ssl keyword to connect() method.

## MariaDB Connector/Python 1.0.1

Release date: August 18th 2020

**Notable changes:**

- [CONPY-100](https://jira.mariadb.org/browse/CONPY-100): added binary option for cursor which allows to use binary protocol without passing parameters
- [CONPY-102](https://jira.mariadb.org/browse/CONPY-102): Default for autocommit is now off
- [CONPY-105](https://jira.mariadb.org/browse/CONPY-105): Behavior of rowcount and lastrowid atttributes now conforms to PEP-249

**Issues fixed:**

- [CONPY-82](https://jira.mariadb.org/browse/CONPY-82): Unlock mutex in case of ConnectionPool.add_connection failed
- [CONPY-83](https://jira.mariadb.org/browse/CONPY-83): Fixed missing reference increment in ConnectionPool class
- [CONPY-85](https://jira.mariadb.org/browse/CONPY-85): Fixed version checking in setup.py
- [CONPY-93](https://jira.mariadb.org/browse/CONPY-93): Release GIL before calling Python’s memory allocation routine
- [CONPY-94](https://jira.mariadb.org/browse/CONPY-94): Support python subclasses for data binding
- [CONPY-95](https://jira.mariadb.org/browse/CONPY-95): Added support for MYSQL_TYPE_BIT column type
- [CONPY-98](https://jira.mariadb.org/browse/CONPY-98): Return binary object when casting to binary
- [CONPY-99](https://jira.mariadb.org/browse/CONPY-99): Fixed memory leak in fetchall() method.
- [CONPY-101](https://jira.mariadb.org/browse/CONPY-101): Fixed negative reference count when using callproc() method.
- [CONPY-106](https://jira.mariadb.org/browse/CONPY-106): exception handling: type of exception depends now on error code instead of sqlstate
- [CONPY-107](https://jira.mariadb.org/browse/CONPY-107): convert negative time values to datetime.timedelta instances

## MariaDB Connector/Python 1.0.0

Release date: June 24th 2020

**Issues fixed:**

- [CONPY-69](https://jira.mariadb.org/browse/CONPY-69): Set default character set (utf8mb4) with authentication packet
- [CONPY-70](https://jira.mariadb.org/browse/CONPY-70): set_config() method needs to check the passed parameter and raise an exception if the parameter type is not a dictionary.
- [CONPY-72](https://jira.mariadb.org/browse/CONPY-72): When deallocating the connection pool class, we need to check beside pool_size if the array containing the connections is valid.
- [CONPY-76](https://jira.mariadb.org/browse/CONPY-76): Added aliases username, passwd and db to connection keywords.
- [CONPY-78](https://jira.mariadb.org/browse/CONPY-78): Since MaxScale doesn’t support bulk operations yet, we have to check servers extended capability flag to determine if this feature is supported or not.
- [CONPY-79](https://jira.mariadb.org/browse/CONPY-79): When inserting NULL values with executemany() method on a server which doesn’t support BULK statements NULL values weren’t inserted correctly.
- [CONPY-80](https://jira.mariadb.org/browse/CONPY-80): Parameters in set_config() method of ConnectionPool class have to be checked against the list of DSN keywords
- [CONPY-81](https://jira.mariadb.org/browse/CONPY-81): Fixed crash when switching between text and binary protocol with same cursor
- Fixed bug when inserting negative integer values with cursor.execute() method

{% @marketo/form formId="4316" %}
