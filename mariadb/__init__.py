'''
MariaDB Connector/Python enables python programs to access MariaDB and MySQL 
atabases, using an API which is compliant with the Python DB API 2.0 (PEP-249).
It is written in C and uses MariaDB Connector/C client library for client
server communication.

Minimum supported Python version is 3.6
'''

from ._mariadb import (
    Binary,
    ConnectionPool,
    DataError,
    DatabaseError,
    Error,
    IntegrityError,
    InterfaceError,
    InternalError,
    NotSupportedError,
    OperationalError,
    PoolError,
    ProgrammingError,
    Warning,
    _CONNECTION_POOLS,
    __version__,
    __version_info__,
    connect,
    mariadbapi_version,
)

from .field import fieldinfo


from mariadb.dbapi20 import *

'''
test attribute
'''
test=1

