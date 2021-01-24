'''
MariaDB Connector/Python enables python programs to access MariaDB and MySQL 
atabases, using an API which is compliant with the Python DB API 2.0 (PEP-249).
It is written in C and uses MariaDB Connector/C client library for client
server communication.

Minimum supported Python version is 3.6
'''

from ._mariadb import (
    BINARY,
    Binary,
    connection,
    ConnectionPool,
    DATETIME,
    DataError,
    DatabaseError,
    Date,
    DateFromTicks,
    Error,
    IntegrityError,
    InterfaceError,
    InternalError,
    NUMBER,
    NotSupportedError,
    OperationalError,
    PoolError,
    ProgrammingError,
    ROWID,
    STRING,
    Time,
    TimeFromTicks,
    Timestamp,
    TimestampFromTicks,
    Warning,
    _CONNECTION_POOLS,
    __version__,
    __version_info__,
    apilevel,
    paramstyle,
    threadsafety,
    connect,
    fieldinfo,
    mariadbapi_version,
)

'''
test attribute
'''
test=1
