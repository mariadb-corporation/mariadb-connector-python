Release history
===============

MariaDB Connector/Python 1.1.6
------------------------------

Release date: Feb 20 2023

Notable changes:
^^^^^^^^^^^^^^^^

- :conpy:`247`: Added optional parameter "pool_invalidation_interval", which specifies the validation interval in milliseconds after which the status of a connection requested from the pool is checked. The default values is 500 milliseconds, a value of 0 means that the status will always be checked. 

Issues fixed:
^^^^^^^^^^^^^

- :conpy:`251`: Check if stmt was already initialized in cursor nextset() method.
- :conpy:`250`: Fixed calculation of connection pool size
- :conpy:`248`: Replace broken connections in connection pool
- :conpy:`246`: Rollback transaction if connection pool was created without pool_reset_connection option.
- :conpy:`245`: Implementation of LRU cache in connection pool.
- :conpy:`240`: Don't overwrite errormessage/stacktrace if an exception was generated during module initialization. 



MariaDB Connector/Python 1.1.5
------------------------------

Release date: Nov 7 2022

Notable changes:
^^^^^^^^^^^^^^^^

- Since Connector/C 3.2 is discontinued, minimum required version for MariaDB Connector/Python 1.1.5 is Connector/C 3.3.1
- :conpy:`220`: Added _get_socket() method
- Performance improvement: Instead of iterating via fetchone(), fetchall() and fetchmany() methods now load the data directly at once. 

Issues fixed:
^^^^^^^^^^^^^

- :conpy:`222`: Removed del() method from cursor
- :conpy:`224`: Fixed bulk_operation when reexecuted using same cursor
- :conpy:`225`: Fixed cursor.affected_rows property
- :conpy:`226`: Replaced deprecated distutils (PEP-632)
- :conpy:`227`: Replaced collections.named_tuple by PyStruct_Sequence (C-Python) 
- .conpy:`228`: Fixed Installation error (if C/C version < 3.2.4 was found)
- .conpy:`229`: Converter: added missing support for None conversions
- .conpy:`231`: Fixed memory leak

MariaDB Connector/Python 1.1.4
------------------------------

Release date: Aug 10 2022

Issues fixed:
^^^^^^^^^^^^^
- :conpy:`217`: Added reconnect keyword for connection
- Added CAPABILITY constants
- Code styling fixes (flake8) 
- :conpy:`218`: Allow None as data parameter in cursor->execute(). Kudos to Luciano Barcaro for providing a fix
- :conpy:`214`: Replaced cursor iterator by native Python iter() method. 

MariaDB Connector/Python 1.1.3
------------------------------
Release date: Jul 07 2022

Issues fixed:
^^^^^^^^^^^^^
    CONPY-209: Wrong unicode substitution in SELECT statement
    CONPY-210: Added missing error constants
    CONPY-212: unbuffered cursor.execute() doesn't work 

MariaDB Connector/Python 1.1.2
-------------------------------
Release date: Jun 27 2022

Notable changes:
^^^^^^^^^^^^^^^^
    CONPY-203: Error constants added
    CONPY-204: New connection method dump_debug_info(

Issues fixed:
^^^^^^^^^^^^^
    Removed utf8 part of internal parser and use binary objects for parameter substitution
    CONPY-205: Fixed inconsistent exceptions: All parameter exceptions are returned as ProgrammingError. 
    Fixed memory leak when using decimal parameters
    CONPY-201: Fixed build issues with Python 3.11 beta 


MariaDB Connector/Python 1.0.11
-------------------------------

Release date: Apr 12 2022

Issues fixed:
^^^^^^^^^^^^^

    CONPY-194: executemany() does not work with returning clause
    CONPY-196: Missing decrement of reference pointer when closing cursor
    CONPY-198: Build fix for FreeBSD 

MariaDB Connector/Pyhon 1.0.10
------------------------------

Release date: Feb 18 2022

Issues fixed:
^^^^^^^^^^^^^

- CONPY-184: Display status of connection, cursor and pool class in string representation.
- CONPY-178: Repeated execution of cursors callproc() method hangs
- CONPY-175: Fixed crash in escape_string 

MariaDB Connector/Python 1.0.9
------------------------------

Release date: Dec 21 2021

Issues fixed:
^^^^^^^^^^^^^

- :conpy:`184`: Display status of connection, cursor and pool class in string representation.
- :conpy:`178`: Repeated execution of cursors callproc() method hangs
- :conpy:`175`: Fixed crash in escape_string 

MariaDB Connector/Python 1.0.8
------------------------------

Release date: Oct 22 2021

Issues fixed:
^^^^^^^^^^^^^

- :conpy:`173`: Fixed windows build for Python 3.10


MariaDB Connector/Python 1.0.7
------------------------------

Release date: Jun 8 2021

Issues fixed:
^^^^^^^^^^^^^

- :conpy:`155`: fixed crash in get_server_version method of connection class
- :conpy:`144`: fixed crash in connection pool
- :conpy:`150`: convert invalid date types (day, month or year=0) to NULL 

MariaDB Connector/Python 1.0.6
------------------------------

Release date: Feb 24 2021

Issues fixed:
^^^^^^^^^^^^^

- :conpy:`142`: Fixed memory leak in connection class (server_version_info)
- :conpy:`138`, :conpy:`141`: When using binary protocol, convert data to binary object only if the character set is BINARY (63), not if the flag was set and character set is a non binary character set.
- Various build and travis related corrections/fixes. 

MariaDB Connector/Python 1.0.5
------------------------------

Release date: Nov 25th 2020

Notable changes:
^^^^^^^^^^^^^^^^

- :conpy:`127`: When establishing a new database connection the connect method now also supports None values instead of strings only.
- :conpy:`128`: Added connection attribute server_version_info and (for compatibility) get_server_version() method. Both return a tuple, describing the version number of connected server in following format: (MAJOR_VERSION, MINOR_VERSION, PATCH_VERSION)
- :conpy:`133`: The internal parser now supports the full MariaDB comment syntax 

Issues fixed:
^^^^^^^^^^^^^

- :conpy:`126`: Fixed memory leak in connection object
- :conpy:`130`: Fixed DeprecationWarning: builtin type Row has no module attribute
- :conpy:`131`: Fixed crash type_traverse() called for non-heap type Row (Python 3.6 only)
- :conpy:`132`: Fixed memory leak in connection pool 

MariaDB Connector/Python 1.0.4
------------------------------

Release date: Oct 20th 2020

Notable changes:
^^^^^^^^^^^^^^^^

Binary wheel packages are now availble for Windows on http://pypi.org

Issues fixed:
^^^^^^^^^^^^^

- :conpy:`123`: Free pending result sets when closing cursor
- :conpy:`124`: Fix build when building against Connector/C < 3.1.8
- :conpy:`125`: Build fix: replace obsolete ULONG_LONG_MAX definitions

MariaDB Connector/Python 1.0.3
------------------------------

Release date: Oct 7th 2020

Notable changes:
^^^^^^^^^^^^^^^^

- :conpy:`117`: Added support for data type conversion.

Issues fixed:
^^^^^^^^^^^^^

- :conpy:`116`: Wrong type reporting for column type MYSQL_TYPE_JSON
- :conpy:`118`: Removed statement allocation for text protocol
- :conpy:`119`: Fixed memory leak when cursor result is dictionary

MariaDB Connector/Python 1.0.2
------------------------------

Release date: Sept 18th 2020

Issues fixed:
^^^^^^^^^^^^^

- Fixed datetime initialization
- :conpy:`108`: Fixed memory leak
- :conpy:`110`: Fixed memory overrun when passing ssl keyword to connect() method.

MariaDB Connector/Python 1.0.1
------------------------------

Release date: August 18th 2020

Notable changes:
^^^^^^^^^^^^^^^^

- :conpy:`100`: added binary option for cursor which allows to use binary protocol without passing parameters
- :conpy:`102`: Default for autocommit is now off
- :conpy:`105`: Behavior of rowcount and lastrowid atttributes now conforms to PEP-249

Issues fixed:
^^^^^^^^^^^^^

- :conpy:`82`: Unlock mutex in case of ConnectionPool.add_connection failed
- :conpy:`83`: Fixed missing reference increment in ConnectionPool class
- :conpy:`85`: Fixed version checking in setup.py
- :conpy:`93`: Release GIL before calling Python's memory allocation routine
- :conpy:`94`: Support python subclasses for data binding 
- :conpy:`95`: Added support for MYSQL_TYPE_BIT column type
- :conpy:`98`: Return binary object when casting to binary
- :conpy:`99`: Fixed memory leak in fetchall() method.
- :conpy:`101`: Fixed negative reference count when using callproc() method.
- :conpy:`106`: exception handling: type of exception depends now on error code instead of sqlstate
- :conpy:`107`: convert negative time values to datetime.timedelta instances

MariaDB Connector/Python 1.0.0
------------------------------

Release date: June 24th 2020

Issues fixed:
^^^^^^^^^^^^^

- :conpy:`69`: Set default character set (utf8mb4) with authentication packet 
- :conpy:`70`: set_config() method needs to check the passed parameter and raise an exception if the parameter type is not a dictionary.
- :conpy:`72`: When deallocating the connection pool class, we need to check beside pool_size if the array containing the connections is valid.
- :conpy:`76`: Added aliases username, passwd and db to connection keywords.
- :conpy:`78`: Since MaxScale doesn't support bulk operations yet, we have to check servers extended capability flag to determine if this feature is supported or not.
- :conpy:`79`: When inserting NULL values with executemany() method on a server which doesn't support BULK statements NULL values weren't inserted correctly.
- :conpy:`80`: Parameters in set_config() method of ConnectionPool class have to be checked against the list of DSN keywords
- :conpy:`81`: Fixed crash when switching between text and binary protocol with same cursor
- Fixed bug when inserting negative integer values with cursor.execute() method
