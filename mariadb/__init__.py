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
from mariadb.cursors import Cursor
from mariadb.release_info import __version__ as __version__ 
from mariadb.release_info import __version_info__ as __version_info__ 
from mariadb.release_info import __author__ as __author__
from mariadb.connections import Connection
# disable for now, until tests are in place
# from mariadb.pooling import *

def connect(*args, connectionclass= mariadb.connections.Connection, **kwargs):
    """
    Creates a MariaDB Connection object.

    By default the standard connectionclass mariadb.connections.Connection will
    be created.

    Connection parameters are provided as a set of keyword arguments:

        host: string
            The host name or IP address of the database server
        user: string
        username: string
            The username used to authenticate with the database server
        password: string
        passwd: string
            The password of the given user
        database: string
        db: string
            database (schema) name to use when connecting with the database
            server
        unix_socket: string
            The location of the unix socket file to use instead of using an IP port
            to connect. If socket authentication is enabled, this can also be used
            in place of a password.
        port: integer
            port number of the database server. If not specified the default
            value of 3306 will be used.
        connect_timeout: integer
            connect timeout in seconds
        read_timeout: integer
            read timeout in seconds
        write_timeout: integer
            write timeout in seconds
        local_infile: boolean
            Eenables or disables the use of LOAD DATA LOCAL INFILE statements.
        compress: boolean
            Uses the compressed protocol for client server communication. If the
            server doesn't support compressed protocol, the default protocol will
            be used
        init_command: string
            Command(s) which will be executed when connecting and reconnecting to
            the database server
        default_file: string
            Read options from the specified option file. If the file is an empty
            string, default configuration file(s) will be used
        default_group: string
            Read options from the specified group
        plugin_dir:
            Directory which contains MariaDB client plugins.
        ssl_key: string
            Defines a path to a private key file to use for TLS. This option
            requires that you use the absolute path, not a relative path. The
            specified key must be in PEM format
        ssl_cert: string
            Defines a path to the X509 certificate file to use for TLS.
            This option requires that you use the absolute path, not a relative
            path. The X609 certificate must be in PEM format.
        ssl_ca: string
            Defines a path to a PEM file that should contain one or more X509
            certificates for trusted Certificate Authorities (CAs) to use for TLS.
            This option requires that you use the absolute path, not a relative
            path.
        ssl_capath: string
            Defines a path to a directory that contains one or more PEM files that
            contains one X509 certificate for a trusted Certificate Authority (CA)
        ssl_cipher: string
            Defines a list of permitted cipher suites to use for TLS
        ssl_crlpath: string
            Defines a path to a PEM file that should contain one or more revoked
            X509 certificates to use for TLS. This option requires that you use
            the absolute path, not a relative path.
        ssl_verify_cert: boolean
            Enables server certificate verification.
        ssl: Boolean
            The connection must use TLS security or it will fail.
        autocommit: Boolean or None
            Specifies the autocommit settings: None will use the server default,
            True will enable autocommit, False will disable it (default).

    """
    if kwargs:
        if "pool_name" in kwargs:
            if not kwargs["pool_name"] in mariadb._CONNECTION_POOLS:
                pool= mariadb.ConnectionPool(**kwargs)
            else:
                pool= mariadb._CONNECTION_POOLS[kwargs["pool_name"]]
            c= pool.get_connection()
            return c

    connection= connectionclass(*args, **kwargs)
    if not isinstance(connection, mariadb.connections.Connection):
         raise mariadb.ProgrammingError("%s is not an instance of mariadb.Connection" % connection)
    return connection


Connection= connect

client_version_info= tuple(int(x, 10) for x in mariadb.mariadbapi_version.split('.'))
client_version= client_version_info[0] * 10000 + client_version_info[1] * 1000 + client_version_info[2]
