'''
MariaDB Connector/Python module enables python programs to access MariaDB and
MySQL databases, using an API which is compliant with the Python DB API 2.0
(PEP-249).

This is a pure Python implementation. For better performance, install the
optional C extension: pip install mariadb-python[c-extension]
'''

# Import exceptions from shared package to avoid circular dependencies
from mariadb_shared.exceptions import (
    DataError, DatabaseError, Error, IntegrityError,
    InterfaceError, InternalError, NotSupportedError,
    OperationalError, PoolError, ProgrammingError, Warning
)

# Set the module name for all exceptions to 'mariadb' for compatibility
DataError.__module__ = 'mariadb'
DatabaseError.__module__ = 'mariadb'
Error.__module__ = 'mariadb'
IntegrityError.__module__ = 'mariadb'
InterfaceError.__module__ = 'mariadb'
InternalError.__module__ = 'mariadb'
NotSupportedError.__module__ = 'mariadb'
OperationalError.__module__ = 'mariadb'
PoolError.__module__ = 'mariadb'
ProgrammingError.__module__ = 'mariadb'
Warning.__module__ = 'mariadb'

from .field import fieldinfo
from .dbapi20 import *   # noqa: F401,F403
# Import constants from shared package
from mariadb_shared import constants

# Import implementation selector early
from . import impl_selector  # noqa: F401 import early to stabilize side effects

# Re-export the selected implementation classes and implementation info
# Handle both pure Python (has SyncConnection) and C extension (has Connection)
if hasattr(impl_selector.sync_connection, 'SyncConnection'):
    SyncConnection = impl_selector.sync_connection.SyncConnection
else:
    # C extension uses Connection instead of SyncConnection
    SyncConnection = impl_selector.sync_connection.Connection

if impl_selector.async_connection:
    AsyncConnection = impl_selector.async_connection.AsyncConnection
else:
    AsyncConnection = None

SyncCursor = impl_selector.SyncCursor
AsyncCursor = impl_selector.AsyncCursor
__impl__ = impl_selector.__impl__

# Implementation selection happens at import time in impl_selector

__all__ = ["DataError", "DatabaseError", "Error", "IntegrityError",
           "InterfaceError", "InternalError", "NotSupportedError",
           "OperationalError", "PoolError", "ProgrammingError",
           "Warning", "SyncConnection", "AsyncConnection", "__version__", "__version_type__", "__version_info__",
           "__author__", "SyncCursor", "AsyncCursor", "fieldinfo", "constants",
           "connect", "asyncConnect", "mariadbapi_version", "client_version_info", "client_version", "_have_asan", "__impl__",
           "apilevel", "paramstyle", "threadsafety"]

def connect(*args, connectionclass=None, **kwargs):
    """
    Creates a MariaDB Connection object (synchronous).

    The implementation (pure Python or C extension) is automatically selected
    based on availability and the MARIADB_PYTHON_CONNECTOR environment variable.

    Parameter connectionclass specifies a subclass of
    SyncConnection. If not specified, the default SyncConnection will be used.

    Connection parameters can be provided as:
    1. A URI string: mariadb://[user[:password]@][host][:port][/database][?option1=value1&option2=value2]
    2. A set of keyword arguments (see below)
    
    When using a URI string, keyword arguments can still be provided and will take priority over
    values in the URI.

    Connection parameters are provided as a set of keyword arguments:

    - **`host`** - The host name or IP address of the database server. If MariaDB Connector/Python was built with MariaDB Connector/C 3.3, it is also possible to provide a comma separated list of hosts for simple fail over in case of one or more hosts are not available.
    - **`user`, `username`** - The username used to authenticate with the database server
    - **`password`, `passwd`** - The password of the given user
    - **`database`, `db`** - Database (schema) name to use when connecting with the database server
    - **`unix_socket`** - The location of the unix socket file to use instead of using an IP port to connect. If socket authentication is enabled, this can also be used in place of a password.
    - **`port`** - Port number of the database server. If not specified, the default value of 3306 will be used.
    - **`connect_timeout`** - Connect timeout in seconds
    - **`read_timeout`** - Read timeout in seconds
    - **`write_timeout`** - Write timeout in seconds
    - **`local_infile`** - Enable or disable the use of LOAD DATA LOCAL INFILE statements
    - **`compress`** - Enable or disable protocol compression. If enabled, compression will be used if the server supports it
    - **`init_command`** - Command which will be executed when connecting and reconnecting to the server
    - **`default_file`** - Read default values from the given option file. On Windows the file must be an .ini file
    - **`default_group`** - Read default values from the given group. If not given, the default group name is the connection type
    - **`ssl_key`** - Defines a path to a private key file to use for TLS. This option requires that you use the absolute path, not a relative path. The private key must be in PEM format
    - **`ssl_cert`** - Defines a path to the X509 certificate file to use for TLS. This option requires that you use the absolute path, not a relative path. The X609 certificate must be in PEM format.
    - **`ssl_ca`** - Defines a path to a PEM file that should contain one or more X509 certificates for trusted Certificate Authorities (CAs) to use for TLS. This option requires that you use the absolute path, not a relative path.
    - **`ssl_capath`** - Defines a path to a directory that contains one or more PEM files that contains one X509 certificate for a trusted Certificate Authority (CA)
    - **`ssl_cipher`** - Defines a list of permitted cipher suites to use for TLS
    - **`ssl_crlpath`** - Defines a path to a PEM file that should contain one or more revoked X509 certificates to use for TLS. This option requires that you use the absolute path, not a relative path.
    - **`ssl_verify_cert`** - Enables server certificate verification.
    - **`ssl`** - The connection must use TLS security, or it will fail.
    - **`tls_version`** - A comma-separated list (without whitespaces) of TLS versions. Valid versions are TLSv1.0, TLSv1.1,TLSv1.2 and TLSv1.3. Added in version 1.1.7.
    - **`autocommit`** (default: `False`) - Specifies the autocommit settings. True will enable autocommit, False will disable it (default).
    - **`converter`** - Specifies a conversion dictionary, where keys are FIELD_TYPE values and values are conversion functions

    **Environment Variables:**
    - **`MARIADB_PYTHON_CONNECTOR`** - Controls which connector implementation to use:
        - `c` or `mariadb_c` - Force C extension (requires compilation)
        - `binary` or `mariadb_binary` - Force binary wheel (precompiled, bundled dependencies)
        - `python` or `mariadb` - Force pure Python implementation
        - Not set - Default behavior (try C extension first, then binary, fallback to pure Python)

    """
    # Parse URI if provided as first positional argument
    if args and len(args) > 0:
        first_arg = args[0]
        if isinstance(first_arg, str):
            from mariadb_shared.uri_parser import is_connection_uri, parse_connection_uri
            if is_connection_uri(first_arg):
                # Parse URI into parameters
                uri_params = parse_connection_uri(first_arg)
                # Merge with kwargs, giving priority to kwargs
                uri_params.update(kwargs)
                kwargs = uri_params
                # Remove the URI from args
                args = args[1:]
    
    # Compatibility feature: if SSL is provided as a dictionary,
    # map its content to ssl_* parameters (mariadb-c compatibility)
    if "ssl" in kwargs and not isinstance(kwargs["ssl"], bool):
        ssl = kwargs.pop("ssl", None)
        for key in ["ca", "cert", "capath", "key", "cipher"]:
            if key in ssl:
                kwargs["ssl_%s" % key] = ssl[key]
        kwargs["ssl"] = True
    
    # Check if pool_name is specified
    pool_name = kwargs.get('pool_name')
    if pool_name:
        if pool_name in _CONNECTION_POOLS:
            pool = _CONNECTION_POOLS[pool_name]
        else:
            pool = _get_connection_pool_class()(**kwargs)
        return pool.get_connection()
    
    # Use SyncConnection if no custom class specified
    if connectionclass is None:
        connectionclass = SyncConnection

    connection = connectionclass(*args, **kwargs)
    
    # Validate that it's a proper Connection instance
    if not hasattr(connection, 'cursor'):
        raise ProgrammingError(f"{connection} is not a valid mariadb Connection")
    
        
    return connection


async def asyncConnect(*args, connectionclass=None, **kwargs):
    """
    Creates a MariaDB AsyncConnection object and connects asynchronously.

    This function creates a native async connection that must be used with
    async/await syntax. It automatically calls connect() before returning.

    Parameter connectionclass specifies a subclass of AsyncConnection.
    If not specified, the default AsyncConnection will be used.

    Connection parameters can be provided as:
    1. A URI string: mariadb://[user[:password]@][host][:port][/database][?option1=value1&option2=value2]
    2. A set of keyword arguments (same as connect() function)
    
    Returns:
        AsyncConnection: A connected async connection object
        
    Example:
        async def main():
            conn = await mariadb.asyncConnect(
                user='root',
                password='secret',
                host='localhost',
                database='test'
            )
            cursor = conn.cursor()
            await cursor.execute("SELECT 1")
            result = await cursor.fetchone()
            await conn.close()
        
        asyncio.run(main())
    
    Note: Pool connections are not supported with asyncConnect.
    """
    # Check if AsyncConnection is available
    if AsyncConnection is None:
        raise NotSupportedError(
            "AsyncConnection is not available. "
            "This may occur if the pure Python async implementation could not be imported. "
            "Ensure Python 3.7+ is installed and the mariadb package is properly installed."
        )
    
    # Parse URI if provided as first positional argument
    if args and len(args) > 0:
        first_arg = args[0]
        if isinstance(first_arg, str):
            from mariadb_shared.uri_parser import is_connection_uri, parse_connection_uri
            if is_connection_uri(first_arg):
                # Parse URI into parameters
                uri_params = parse_connection_uri(first_arg)
                # Merge with kwargs, giving priority to kwargs
                uri_params.update(kwargs)
                kwargs = uri_params
                # Remove the URI from args
                args = args[1:]
    
    # Compatibility feature: if SSL is provided as a dictionary,
    # map its content to ssl_* parameters (mariadb-c compatibility)
    if "ssl" in kwargs and not isinstance(kwargs["ssl"], bool):
        ssl = kwargs.pop("ssl", None)
        for key in ["ca", "cert", "capath", "key", "cipher"]:
            if key in ssl:
                kwargs["ssl_%s" % key] = ssl[key]
        kwargs["ssl"] = True
    
    # Check if pool_name is specified
    pool_name = kwargs.get('pool_name')
    if pool_name:
        if pool_name in _ASYNC_CONNECTION_POOLS:
            pool = _ASYNC_CONNECTION_POOLS[pool_name]
        else:
            pool = _get_async_connection_pool_class()(**kwargs)
        return await pool.get_connection()

    # Use AsyncConnection if no custom class specified
    if connectionclass is None:
        connectionclass = AsyncConnection
    
    # Connect asynchronously using the classmethod
    return await connectionclass.connect(*args, **kwargs)


# Stub for ASAN detection
_have_asan = False

# Version information for the connector
def _parse_version_info(version_string):
    """
    Parse version string into numeric format
    
    Args:
        version_string: Version like "1.2.3-dev", "2.0.0.dev", or "2.0.0-ga"
        
    Returns:
        Tuple of (major, minor, patch[, suffix]) and numeric version (MMMMPP format)
    """
    import re
    
    # Extract major.minor.patch and optional suffix from version string
    # Handle formats like "1.2.3", "1.2.3-dev", "1.2.3.dev", "1.2.3-ga", etc.
    match = re.match(r'^(\d+)\.(\d+)\.(\d+)(?:[.-](.+))?$', version_string)
    if match:
        major = int(match.group(1))
        minor = int(match.group(2))
        patch = int(match.group(3))
        suffix = match.group(4)  # Optional suffix (dev, ga, etc.)
        
        # Convert to tuple format - include suffix if present
        if suffix:
            version_tuple = (major, minor, patch, suffix)
        else:
            version_tuple = (major, minor, patch)
        
        # Convert to 6-digit format: MMMMPP (2 digits each)
        version_numeric = major * 10000 + minor * 100 + patch
        
        return version_tuple, version_numeric
    else:
        # Fallback for invalid version strings
        return (0, 0, 0), 0

# Load base version from release_info.py (generated at build time)
mariadbapi_version = None
try:
    from .release_info import __version__ as _base_version
except ImportError:
    # Fallback if release_info.py doesn't exist (development mode)
    # Try to get from package metadata
    try:
        from importlib.metadata import version
        _base_version = version('mariadb')
    except ImportError:
        try:
            from importlib_metadata import version
            _base_version = version('mariadb')
        except ImportError:
            # Final fallback
            _base_version = "2.0.0.dev"

# Parse version info
version_tuple, version_numeric = _parse_version_info(_base_version)

# For compatibility
client_version_info = version_tuple
client_version = version_numeric

__author__ = "MariaDB Corporation"

# Connection pool support (lazy import)
_CONNECTION_POOLS = {}
_ASYNC_CONNECTION_POOLS = {}

# Cache for pool classes (lazy loaded)
_ConnectionPoolClass = None
_AsyncConnectionPoolClass = None

# Dynamic version properties that reflect the actual implementation being used
def __getattr__(name):
    """
    Dynamic attribute access for version info and optional pooling support.
    Returns version information based on the actual implementation being used.
    """
    global _ConnectionPoolClass, _AsyncConnectionPoolClass
    
    if name == '__version__':
        return _get_current_version()
    elif name == '__version_type__':
        return _get_current_version_type()
    elif name == '__version_info__':
        return _get_current_version_info()
    elif name == 'ConnectionPool':
        # Lazy import and cache compatibility wrapper
        if _ConnectionPoolClass is None:
            _ConnectionPoolClass = _get_connection_pool_class()
        return _ConnectionPoolClass
    elif name == 'AsyncConnectionPool':
        # Lazy import and cache async connection pool
        if _AsyncConnectionPoolClass is None:
            _AsyncConnectionPoolClass = _get_async_connection_pool_class()
        return _AsyncConnectionPoolClass
    else:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

def _get_current_version():
    """Get version based on current implementation selection"""
    if __impl__ == 'c':
        # C extension is selected
        try:
            import mariadb_c
            return mariadb_c.__version__
        except (ImportError, AttributeError):
            return _base_version + "+c"
    elif __impl__ == 'binary':
        # Binary wheel is selected
        try:
            import mariadb_binary
            return mariadb_binary.__version__
        except (ImportError, AttributeError):
            return _base_version + "+binary"
    else:
        # Pure Python implementation
        return _base_version + "+native"

def _get_current_version_type():
    """Get version type based on current implementation selection"""
    if __impl__ == 'c':
        return "c"
    elif __impl__ == 'binary':
        return "binary"
    else:
        return "native"

def _get_current_version_info():
    """Get version info based on current implementation selection"""
    return version_tuple


def _get_connection_pool_class():
    """
    Get ConnectionPool class from mariadb_pool package.
    """
    try:
        from mariadb_pool import ConnectionPoolWrapper
    except ImportError:
        raise AttributeError(
            "ConnectionPool is not available. "
            "Install mariadb-pool: pip install mariadb[pool]"
        )
    
    # Create a wrapper class that injects mariadb.connect and manages _CONNECTION_POOLS
    class ConnectionPool(ConnectionPoolWrapper):
        """
        Wrapper around ConnectionPoolWrapper that automatically uses mariadb.connect
        
        Supports URI format: mariadb://[user[:password]@][host][:port][/database][?options]
        """
        
        def __init__(self, uri_or_pool_name=None, uri=None, pool_name=None, **kwargs):
            """Initialize with mariadb.connect as factory and register in _CONNECTION_POOLS
            
            Args:
                uri_or_pool_name: Either a URI string or pool_name (first positional argument)
                uri: Optional URI string for connection parameters (deprecated, use first arg)
                pool_name: Name of the pool (can be in URI query params or as kwarg)
                **kwargs: Connection parameters and pool configuration
                
            Examples:
                # URI with pool_name in query params
                pool = ConnectionPool("mariadb://user:pass@host/db?pool_name=mypool")
                
                # Traditional style
                pool = ConnectionPool(pool_name="mypool", uri="mariadb://user:pass@host/db")
                
                # pool_name as first arg, connection params as kwargs
                pool = ConnectionPool("mypool", host="localhost", user="root", database="test")
            """
            # Handle first positional argument
            if uri_or_pool_name is not None:
                from mariadb_shared.uri_parser import is_connection_uri, parse_connection_uri
                if is_connection_uri(uri_or_pool_name):
                    # First arg is a URI
                    uri_params = parse_connection_uri(uri_or_pool_name)
                    # Extract pool_name from URI params if present
                    if 'pool_name' in uri_params and pool_name is None:
                        pool_name = uri_params.pop('pool_name')
                    # Merge with kwargs, giving priority to kwargs
                    uri_params.update(kwargs)
                    kwargs = uri_params
                else:
                    # First arg is pool_name
                    if pool_name is None:
                        pool_name = uri_or_pool_name
            
            # Parse URI parameter if provided (backward compatibility)
            if uri is not None:
                from mariadb_shared.uri_parser import is_connection_uri, parse_connection_uri
                if is_connection_uri(uri):
                    uri_params = parse_connection_uri(uri)
                    # Extract pool_name from URI params if present
                    if 'pool_name' in uri_params and pool_name is None:
                        pool_name = uri_params.pop('pool_name')
                    # Merge with kwargs, giving priority to kwargs
                    uri_params.update(kwargs)
                    kwargs = uri_params
                
            # pool_name is optional - if not provided, pool can be used directly
            # but won't be registered in _CONNECTION_POOLS
            if pool_name is not None:
                if pool_name in _CONNECTION_POOLS:
                    raise PoolError(f"Pool '{pool_name}' already exists")
            
            # Remove pool_name from kwargs if present (to avoid duplicate argument)
            kwargs.pop('pool_name', None)
            
            super().__init__(connection_factory=connect, pool_name=pool_name, **kwargs)
            
            # Only register named pools
            if pool_name is not None:
                _CONNECTION_POOLS[pool_name] = self
        
        def close(self):
            """Close and unregister from _CONNECTION_POOLS"""
            pool_name = self.pool_name
            super().close()
            if pool_name in _CONNECTION_POOLS:
                del _CONNECTION_POOLS[pool_name]
    
    return ConnectionPool


def _get_async_connection_pool_class():
    """
    Get AsyncConnectionPool class from mariadb_pool package.
    """
    try:
        from mariadb_pool import AsyncConnectionPoolWrapper
    except ImportError:
        raise AttributeError(
            "AsyncConnectionPool is not available. "
            "Install mariadb-pool: pip install mariadb[pool]"
        )
    
    # Create a wrapper class that injects mariadb.asyncConnect and manages _CONNECTION_POOLS
    class AsyncConnectionPool(AsyncConnectionPoolWrapper):
        """
        Wrapper around AsyncConnectionPoolWrapper that automatically uses mariadb.asyncConnect
        
        Supports pool_name for registry in mariadb._CONNECTION_POOLS
        """
        
        def __init__(self, uri_or_pool_name=None, uri=None, pool_name=None, **kwargs):
            """Initialize with mariadb.asyncConnect as factory and register in _CONNECTION_POOLS
            
            Args:
                uri_or_pool_name: Either a URI string or pool_name (first positional argument)
                uri: Optional URI string for connection parameters (deprecated, use first arg)
                pool_name: Name of the pool (can be in URI query params or as kwarg)
                **kwargs: Connection parameters and pool configuration
                
            Examples:
                # URI with pool_name in query params
                pool = AsyncConnectionPool("mariadb://user:pass@host/db?pool_name=mypool")
                
                # Traditional style
                pool = AsyncConnectionPool(pool_name="mypool", uri="mariadb://user:pass@host/db")
                
                # pool_name as first arg, connection params as kwargs
                pool = AsyncConnectionPool("mypool", host="localhost", user="root", database="test")
            """
            # Handle first positional argument
            if uri_or_pool_name is not None:
                from mariadb_shared.uri_parser import is_connection_uri, parse_connection_uri
                if is_connection_uri(uri_or_pool_name):
                    # First arg is a URI
                    uri_params = parse_connection_uri(uri_or_pool_name)
                    # Extract pool_name from URI params if present
                    if 'pool_name' in uri_params and pool_name is None:
                        pool_name = uri_params.pop('pool_name')
                    # Merge with kwargs, giving priority to kwargs
                    uri_params.update(kwargs)
                    kwargs = uri_params
                else:
                    # First arg is pool_name
                    if pool_name is None:
                        pool_name = uri_or_pool_name
            
            # Parse URI parameter if provided (backward compatibility)
            if uri is not None:
                from mariadb_shared.uri_parser import is_connection_uri, parse_connection_uri
                if is_connection_uri(uri):
                    uri_params = parse_connection_uri(uri)
                    # Extract pool_name from URI params if present
                    if 'pool_name' in uri_params and pool_name is None:
                        pool_name = uri_params.pop('pool_name')
                    # Merge with kwargs, giving priority to kwargs
                    uri_params.update(kwargs)
                    kwargs = uri_params
                
            # pool_name is optional - if not provided, pool can be used directly
            # but won't be registered in _CONNECTION_POOLS
            if pool_name is not None:
                if pool_name in _ASYNC_CONNECTION_POOLS:
                    raise PoolError(f"Pool '{pool_name}' already exists")
            
            # Remove pool_name from kwargs if present (to avoid duplicate argument)
            kwargs.pop('pool_name', None)
            
            super().__init__(connection_factory=asyncConnect, pool_name=pool_name, **kwargs)
            
            # Only register named pools
            if pool_name is not None:
                _ASYNC_CONNECTION_POOLS[pool_name] = self
        
        async def close(self):
            """Close and unregister from _CONNECTION_POOLS"""
            pool_name = self.pool_name
            await super().close()
            if pool_name in _ASYNC_CONNECTION_POOLS:
                del _ASYNC_CONNECTION_POOLS[pool_name]
    
    return AsyncConnectionPool


# Implementation selection is handled by impl_selector module at import time