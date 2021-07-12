'''
MariaDB Connector/Python enables python programs to access MariaDB and MySQL 
atabases, using an API which is compliant with the Python DB API 2.0 (PEP-249).
It is written in C and uses MariaDB Connector/C client library for client
server communication.

Minimum supported Python version is 3.6
'''

from ._mariadb import (
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
    mariadbapi_version,
)

from .field import fieldinfo

_POOLS= _CONNECTION_POOLS= {}

from mariadb.dbapi20 import *
from mariadb.connectionpool import *
from mariadb.cursor import Cursor
from mariadb.async_connections import *
from mariadb.release_info import __version__ as __version__ 
from mariadb.release_info import __version_info__ as __version_info__ 
from mariadb.release_info import __author__ as __author__
# disable for now, until tests are in place
# from mariadb.pooling import *

def Binary(obj):
    """This method constructs an object capable of holding a binary (long)
       string value."""
    return bytes(obj)

def connect(*args, **kwargs):
    from mariadb.connections import Connection
    if kwargs:
        if "pool_name" in kwargs:
            if not kwargs["pool_name"] in mariadb._CONNECTION_POOLS:
                pool= mariadb.ConnectionPool(**kwargs)
            else:
                pool= mariadb._CONNECTION_POOLS[kwargs["pool_name"]]
            c= pool.get_connection()
            return c
        is_async= kwargs.get("asynchronous", False)
        if is_async:
            return AsyncConnection(*args, **kwargs)

    return Connection(*args, **kwargs)

Connection= connect
