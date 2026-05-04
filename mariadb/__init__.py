'''
MariaDB Connector/Python module enables python programs to access MariaDB and
MySQL databases, using an API which is compliant with the Python DB API 2.0
(PEP-249).

This is a pure Python implementation. For better performance, install the
optional C extension: pip install mariadb-python[c-extension]
'''

from typing import Any, Optional, Union, TYPE_CHECKING

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

if TYPE_CHECKING:
    try:
        from mariadb_c import Connection as CConnection
    except ImportError:
        CConnection = Any
    try:
        from mariadb_pool import ConnectionPoolWrapper, AsyncConnectionPoolWrapper
    except ImportError:
        ConnectionPoolWrapper = Any
        AsyncConnectionPoolWrapper = Any



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
           "connect", "asyncConnect", "create_pool", "create_async_pool", "mariadbapi_version", "client_version_info", "client_version", "_have_asan", "__impl__",
           "apilevel", "paramstyle", "threadsafety"]

def connect(*args: Any, connectionclass: Optional[type] = None, **kwargs: Any) -> Union['SyncConnection', 'CConnection']:  # type: ignore[valid-type]
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
    - **`unix_socket`** - The location of the unix socket file to use instead of using an IP port to connect. If socket authentication is enabled, this can also be used in place of a password. When `host` is ``localhost`` and this parameter is not set, the connector automatically tries ``/tmp/mysql.sock`` (mirroring libmariadb behaviour).
    - **`protocol`** - Force a specific transport protocol. Accepted values (case-insensitive string or integer):
        - ``'DEFAULT'`` / ``0`` — connector chooses automatically (default); Unix socket is used for ``localhost`` when available
        - ``'TCP'`` / ``1`` — force TCP/IP even when ``host`` is ``localhost``
        - ``'SOCKET'`` / ``2`` — force Unix socket (requires ``unix_socket`` to be set or auto-detected)
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
    return connection


async def asyncConnect(*args: Any, connectionclass: Optional[type] = None, **kwargs: Any) -> 'AsyncConnection':  # type: ignore[valid-type]
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

    # Windows + SSL: Force pure Python async due to SCHANNEL buffering issues
    # This workaround is needed until MariaDB Connector/C properly supports async SSL on Windows
    import platform
    connection_class = AsyncConnection
    if platform.system() == "Windows" and __impl__ != "python":
        # Check if SSL is enabled in kwargs (check all SSL-related parameters)
        ssl_param = kwargs.get('ssl', False)
        ssl_enabled = (
            ssl_param is True or
            isinstance(ssl_param, dict) or
            kwargs.get('ssl_ca') or
            kwargs.get('ssl_cert') or
            kwargs.get('ssl_key') or
            kwargs.get('ssl_capath') or
            kwargs.get('ssl_cipher') or
            kwargs.get('ssl_crlpath') or
            kwargs.get('ssl_verify_cert') or
            kwargs.get('tls_version') or
            kwargs.get('tls_fp')
        )
        if ssl_enabled:
            # Import pure Python async implementation
            try:
                from . import async_connection as async_conn_module
                connection_class = async_conn_module.AsyncConnection
            except ImportError:
                # Pure Python implementation unavailable (e.g. cachetools not installed).
                # Fall back to the C/binary implementation.
                pass

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
        return await pool.get_connection()  # type: ignore[no-any-return]

    # Use AsyncConnection if no custom class specified
    if connectionclass is None:
        connectionclass = connection_class  # Use the class selected by Windows+SSL workaround

    # Connect asynchronously using the classmethod
    return await connectionclass.connect(*args, **kwargs)  # type: ignore[union-attr, no-any-return]


# Stub for ASAN detection
_have_asan = False

# Version information for the connector
def _parse_version_info(version_string: str) -> tuple:
    """
    Parse version string into numeric format

    Args:
        version_string: Version like "1.2.3-dev", "2.0.0.dev", or "2.0.0-ga"

    Returns:
        Tuple of (major, minor, patch[, suffix]) and numeric version (MMMMPP format)
    """
    import re

    # Extract major.minor.patch and optional suffix from version string
    # Handle formats like "1.2.3", "1.2.3-dev", "1.2.3.dev", "1.2.3-ga",
    # "2.0.0rc1", "2.0.0a1", "2.0.0b2", etc.
    match = re.match(r'^(\d+)\.(\d+)\.(\d+)([.-](.+)|([a-zA-Z].*))?$', version_string)
    if match:
        major = int(match.group(1))
        minor = int(match.group(2))
        patch = int(match.group(3))
        # group(5): suffix after a '.' or '-' separator (e.g. "dev19" from "2.0.0.dev19")
        # group(6): suffix attached directly (e.g. "rc1" from "2.0.0rc1")
        suffix = match.group(5) or match.group(6)

        # Convert to tuple format - include suffix if present
        if suffix:
            version_tuple = (major, minor, patch, suffix)
        else:
            version_tuple = (major, minor, patch)  # type: ignore[assignment]

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
            from importlib_metadata import version as version_func
            _base_version = version_func('mariadb')
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
def __getattr__(name: str) -> Any:
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

def _get_current_version() -> str:
    """Get version based on current implementation selection"""
    if __impl__ == 'c':
        # C extension is selected
        try:
            import mariadb_c
            return mariadb_c.__version__  # type: ignore[no-any-return]
        except (ImportError, AttributeError):
            return _base_version + "+c"
    elif __impl__ == 'binary':
        # Binary wheel is selected
        try:
            import mariadb_binary
            return mariadb_binary.__version__  # type: ignore[no-any-return]
        except (ImportError, AttributeError):
            return _base_version + "+binary"
    else:
        # Pure Python implementation
        return _base_version + "+native"

def _get_current_version_type() -> str:
    """Get version type based on current implementation selection"""
    if __impl__ == 'c':
        return "c"
    elif __impl__ == 'binary':
        return "binary"
    else:
        return "native"

def _get_current_version_info() -> tuple:
    """Get version info based on current implementation selection"""
    current = _get_current_version()
    # Strip PEP 440 local label (+native, +c, +binary) and implementation
    # suffixes (-c) so _parse_version_info gets a clean X.Y.Z[prerelease] string.
    base = current.split('+')[0]
    if base.endswith('-c'):
        base = base[:-2]
    parsed, _ = _parse_version_info(base)
    return parsed  # type: ignore[no-any-return]


def create_pool(
    min_size: Optional[int] = None,
    max_size: int = 10,
    max_idle_time: float = 600.0,
    max_lifetime: float = 3600.0,
    validation_interval: float = 30.0,
    acquire_timeout: float = 30.0,
    enable_health_check: bool = True,
    reset_connection: bool = False,
    ping_threshold: float = 0.25,
    **connection_params: Any
) -> Any:
    """
    Create a synchronous connection pool with clean separation of pool and connection options.

    Pool Configuration Parameters:
        min_size (int): Minimum number of connections in the pool (default: same as max_size)
        max_size (int): Maximum number of connections in the pool (default: 10)
        max_idle_time (float): Maximum time (seconds) a connection can be idle (default: 600.0)
        max_lifetime (float): Maximum lifetime (seconds) of a connection (default: 3600.0)
        validation_interval (float): Interval (seconds) between health checks (default: 30.0)
        acquire_timeout (float): Timeout (seconds) when acquiring a connection (default: 30.0)
        enable_health_check (bool): Enable periodic health checks (default: True)
        reset_connection (bool): Reset connection state on release (default: False)
        ping_threshold (float): Ping if connection idle > threshold seconds (default: 0.25, 0 = disabled)

    Connection Parameters:
        **connection_params: Additional connection parameters (ssl_ca, ssl_cert, etc.)

    Returns:
        ConnectionPool: A configured connection pool

    Example:
        pool = mariadb.create_pool(
            host='localhost',
            user='root',
            password='secret',
            database='test',
            min_size=5,
            max_size=20,
            ping_threshold=0.25
        )

        with pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()

        pool.close()
    """
    try:
        from mariadb_pool import ConnectionPool, PoolConfig
    except ImportError:
        raise ImportError(
            "Connection pooling is not available. "
            "Install mariadb-pool: pip install mariadb[pool]"
        )

    # Build PoolConfig from pool-specific parameters
    pool_config = PoolConfig(
        min_size=min_size if min_size is not None else max_size,
        max_size=max_size,
        max_idle_time=max_idle_time,
        max_lifetime=max_lifetime,
        validation_interval=validation_interval,
        acquire_timeout=acquire_timeout,
        enable_health_check=enable_health_check,
        reset_connection=reset_connection,
        ping_threshold=ping_threshold
    )

    # Create pool with mariadb.connect as factory
    return ConnectionPool(
        connection_factory=connect,
        config=pool_config,
        **connection_params
    )


async def create_async_pool(
    min_size: Optional[int] = None,
    max_size: int = 10,
    max_idle_time: float = 600.0,
    max_lifetime: float = 3600.0,
    validation_interval: float = 30.0,
    acquire_timeout: float = 30.0,
    enable_health_check: bool = True,
    reset_connection: bool = False,
    ping_threshold: float = 0.25,
    **connection_params: Any
) -> Any:
    """
    Create an asynchronous connection pool with clean separation of pool and connection options.

    This function automatically calls pool.open() to pre-fill the pool with connections.

    Pool Configuration Parameters:
        min_size (int): Minimum number of connections in the pool (default: same as max_size)
        max_size (int): Maximum number of connections in the pool (default: 10)
        max_idle_time (float): Maximum time (seconds) a connection can be idle (default: 600.0)
        max_lifetime (float): Maximum lifetime (seconds) of a connection (default: 3600.0)
        validation_interval (float): Interval (seconds) between health checks (default: 30.0)
        acquire_timeout (float): Timeout (seconds) when acquiring a connection (default: 30.0)
        enable_health_check (bool): Enable periodic health checks (default: True)
        reset_connection (bool): Reset connection state on release (default: False)
        ping_threshold (float): Ping if connection idle > threshold seconds (default: 0.25, 0 = disabled)

    Connection Parameters:
        **connection_params: Additional connection parameters (ssl_ca, ssl_cert, etc.)

    Returns:
        AsyncConnectionPool: A configured and opened async connection pool

    Example:
        async def main():
            pool = await mariadb.create_async_pool(
                host='localhost',
                user='root',
                password='secret',
                database='test',
                min_size=5,
                max_size=20,
                ping_threshold=0.25
            )

            conn = await pool.get_connection()
            cursor = conn.cursor()
            await cursor.execute("SELECT 1")
            result = await cursor.fetchone()
            await conn.close()

            await pool.close()

        asyncio.run(main())
    """
    try:
        from mariadb_pool import AsyncConnectionPool, PoolConfig
    except ImportError:
        raise ImportError(
            "Async connection pooling is not available. "
            "Install mariadb-pool: pip install mariadb[pool]"
        )

    # Build PoolConfig from pool-specific parameters
    pool_config = PoolConfig(
        min_size=min_size if min_size is not None else max_size,
        max_size=max_size,
        max_idle_time=max_idle_time,
        max_lifetime=max_lifetime,
        validation_interval=validation_interval,
        acquire_timeout=acquire_timeout,
        enable_health_check=enable_health_check,
        reset_connection=reset_connection,
        ping_threshold=ping_threshold
    )

    # Create pool with mariadb.asyncConnect as factory
    pool = AsyncConnectionPool(
        connection_factory=asyncConnect,
        config=pool_config,
        **connection_params
    )

    # Pre-fill the pool with connections
    await pool.open()

    return pool


def _get_connection_pool_class() -> type['ConnectionPoolWrapper']:
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

        def __init__(self, uri_or_pool_name: Any = None, uri: Any = None, pool_name: Any = None, **kwargs: Any) -> None:
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

        def close(self) -> None:
            """Close and unregister from _CONNECTION_POOLS"""
            pool_name = self.pool_name
            super().close()
            if pool_name in _CONNECTION_POOLS:
                del _CONNECTION_POOLS[pool_name]

    return ConnectionPool


def _get_async_connection_pool_class() -> type['AsyncConnectionPoolWrapper']:
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

        def __init__(self, uri_or_pool_name: Any = None, uri: Any = None, pool_name: Any = None, **kwargs: Any) -> None:
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

        async def close(self) -> None:
            """Close and unregister from _CONNECTION_POOLS"""
            pool_name = self.pool_name
            await super().close()
            if pool_name in _ASYNC_CONNECTION_POOLS:
                del _ASYNC_CONNECTION_POOLS[pool_name]

    return AsyncConnectionPool


# Implementation selection is handled by impl_selector module at import time
