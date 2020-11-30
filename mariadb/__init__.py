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
    Date,
    DateFromTicks,
    Error,
    IntegrityError,
    InterfaceError,
    InternalError,
    NotSupportedError,
    OperationalError,
    PoolError,
    ProgrammingError,
    Time,
    TimeFromTicks,
    Timestamp,
    TimestampFromTicks,
    Warning,
    _CONNECTION_POOLS,
    __version__,
    __version_info__,
    connect,
    fieldinfo,
    mariadbapi_version,
)

apilevel = '2.0'
paramstyle = 'qmark'
threadsafety = True

from mariadb.constants import FIELD_TYPE

class DbApiType(frozenset):

    def __eq__(self, field_type):
        if (isinstance(field_type, DbApiType)):
            return not self.difference(field_type)
        return field_type in self

BINARY = DbApiType([FIELD_TYPE.GEOMETRY,
                    FIELD_TYPE.LONG_BLOB,
                    FIELD_TYPE.MEDIUM_BLOB,
                    FIELD_TYPE.TINY_BLOB,
                    FIELD_TYPE.BLOB])

STRING = DbApiType([FIELD_TYPE.ENUM,
                    FIELD_TYPE.JSON,
                    FIELD_TYPE.STRING,
                    FIELD_TYPE.VARCHAR,
                    FIELD_TYPE.VAR_STRING])

NUMBER = DbApiType([FIELD_TYPE.DECIMAL,
                    FIELD_TYPE.DOUBLE,
                    FIELD_TYPE.FLOAT,
                    FIELD_TYPE.INT24,
                    FIELD_TYPE.LONG,
                    FIELD_TYPE.LONGLONG,
                    FIELD_TYPE.NEWDECIMAL,
                    FIELD_TYPE.SHORT,
                    FIELD_TYPE.TINY,
                    FIELD_TYPE.YEAR])

DATE = DbApiType([FIELD_TYPE.DATE])
TIME = DbApiType([FIELD_TYPE.TIME])
DATETIME = TIMESTAMP = DbApiType([FIELD_TYPE.DATETIME,
                                          FIELD_TYPE.TIMESTAMP])
ROWID = DbApiType()

'''
test attribute
'''
test=1
