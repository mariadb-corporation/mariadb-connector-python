Release history
===============

Stable releases (GA)
--------------------

MariaDB Connector/Python 1.0.0
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Release date: June 24th 2020

Notable Updates:
  - CONPY-81: Fixed crash when switching between text and binary protocol with same cursor
  - CONPY-80: Parameters in set_config() method of ConnectionPool class have to be checked against the list of DSN keywords
  - CONPY-79: When inserting NULL values with executemany() method on a server which doesn't support BULK statements NULL values weren't inserted correctly.
  - CONPY-78: Since MaxScale doesn't support bulk operations yet, we have to check servers extended capability flag to determine if this feature is supported or not.
  - CONPY-76: Added aliases username, passwd and db to connection keywords.
  - CONPY-70: set_config() method needs to check the passed parameter and raise an exception if the parameter type is not a dictionary.
  - CONPY-72: When deallocating the connection pool class, we need to check beside pool_size if the array containing the connections is valid.
  - Fixed bug when inserting negative integer values with cursor.execute() method
  - CONPY-69: Set default character set (utf8mb4) with authentication packet 
