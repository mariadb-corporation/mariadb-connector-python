'''
MariaDB Connector/Python module enables python programs to access MariaDB and
MySQL databases, using an API which is compliant with the Python DB API 2.0
(PEP-249).

This is a pure Python implementation. For better performance, install the
optional C extension: pip install mariadb-python[c-extension]
'''

import warnings

from typing import Any, Dict, TYPE_CHECKING, cast

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
# Common ABCs implemented by BOTH the pure-Python and C connection classes;
# connect()/asyncConnect() may return either depending on the selected impl.
from mariadb_shared.sync_connection_common import SyncConnectionCommon
from mariadb_shared.async_connection_common import AsyncConnectionCommon

# Import implementation selector early
from . import impl_selector  # noqa: F401 import early to stabilize side effects

if TYPE_CHECKING:
    # mariadb_pool is optional, so we import its types only for type checking
    from mariadb_shared.pool_types import (
        ConnectionPoolWrapper,
        ConnectionPool as _ConnectionPoolImpl,
        AsyncConnectionPool as _AsyncConnectionPoolImpl,
    )



# Re-export the selected implementation classes and implementation info.
# Annotate the type: impl_selector exposes these as Any, but a concrete class
# type lets callers like connect() narrow correctly — assigning an Any into a
# `type | None` target would otherwise re-widen it back to include None.
# Handle both pure Python (has SyncConnection) and C extension (has Connection)
SyncConnection: type[SyncConnectionCommon]
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
           "Warning", "SyncConnection", "AsyncConnection", "__version__", "__version_info__",
           "__author__", "SyncCursor", "AsyncCursor", "fieldinfo", "constants",
           "connect", "asyncConnect", "create_pool", "create_async_pool", "mariadbapi_version", "client_version_info", "client_version", "_have_asan", "__impl__",
           "apilevel", "paramstyle", "threadsafety"]

def connect(*args: Any, connectionclass: type | None = None, **kwargs: Any) -> SyncConnectionCommon:
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
    - **`unix_socket`** - The location of the unix socket file to use instead of using an IP port to connect. If socket authentication is enabled, this can also be used in place of a password. When `host` is ``localhost`` and this parameter is not set, the connector auto-detects the Linux distribution (via ``/etc/os-release``) and uses the same default socket path that libmariadb is compiled with on that distro — mirroring the C connector's behaviour. Concretely: ``/run/mysqld/mysqld.sock`` on Debian/Ubuntu/Arch/Alpine, ``/var/lib/mysql/mysql.sock`` on Fedora/RHEL/CentOS, ``/run/mysql/mysql.sock`` on openSUSE/SLES. On non-Linux platforms (Windows, macOS) or unknown distros no auto-detection happens and the connection falls back to TCP. ``/tmp/mysql.sock`` is intentionally NOT probed (the ``/tmp`` directory is world-writable, which would allow a non-privileged attacker to plant a fake socket); pass ``unix_socket='/tmp/mysql.sock'`` explicitly if you really want that path.
    - **`protocol`** - Force a specific transport protocol. Accepted values (case-insensitive string or integer):
        - ``'DEFAULT'`` / ``0`` — connector chooses automatically (default); Unix socket is used for ``localhost`` when available
        - ``'TCP'`` / ``1`` — force TCP/IP even when ``host`` is ``localhost``
        - ``'SOCKET'`` / ``2`` — force Unix socket (requires ``unix_socket`` to be set or auto-detected)
    - **`port`** - Port number of the database server. If not specified, the default value of 3306 will be used.
    - **`read_timeout`** *(C extension only)* - Read (receive) timeout in seconds passed directly to libmariadb. In the pure-Python connector use ``socket_timeout`` instead.
    - **`write_timeout`** *(C extension only)* - Write (send) timeout in seconds passed directly to libmariadb. In the pure-Python connector use ``socket_timeout`` instead.
    - **`socket_timeout`** - I/O timeout in seconds (default: none, i.e. blocking — matching the C extension, PyMySQL and mysql-connector). Primary timeout parameter for the pure-Python connector. In the C extension it is mapped to ``read_timeout`` and ``write_timeout`` when those are not explicitly set.
    - **`connect_timeout`** - Connect timeout in seconds
    - **`read_timeout`** - Read timeout in seconds
    - **`write_timeout`** - Write timeout in seconds
    - **`local_infile`** - Enable or disable the use of LOAD DATA LOCAL INFILE statements
    - **`compress`** - Enable or disable protocol compression. If enabled, compression will be used if the server supports it
    - **`init_command`** - Command which will be executed when connecting and reconnecting to the server
    - **`default_file`** - Read connection options from a MariaDB/MySQL option file. Option files are read only if this or `default_group` is set; the default (`None`) reads nothing. A path reads only that file; an empty string `""` reads the default files instead (`/etc/my.cnf`, `/etc/mysql/my.cnf`, `$MARIADB_HOME` or `$MYSQL_HOME`, then `~/.my.cnf`). On Windows the file must be an `.ini` file. Explicit connection arguments take precedence over option-file values.
    - **`default_group`** - An additional option-file group to read, on top of the always-read `[client]`, `[client-server]` and `[client-mariadb]` groups. Setting it (even without `default_file`) triggers reading of the default option files.
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
    - **`client_flag`** - Extra client capability flags to OR into the connection (same mechanism as PyMySQL's ``client_flag``). Most capabilities are negotiated automatically; use this to opt into ones that are off by default. In particular, **multi-statements** — running several ``;``-separated statements in one ``execute()`` — are disabled by default (matching the C extension, libmariadb and PyMySQL); pass ``client_flag=mariadb.constants.CAPABILITY.MULTI_STATEMENTS`` to enable them.
    - **`max_allowed_columns`** (default: `65535`) - Upper bound for the number of columns a server may announce for a result set. The column count is a length encoded integer, so a malicious proxy could announce an arbitrarily large number of columns to make the client allocate the corresponding metadata and run out of memory; the command is rejected with an OperationalError before allocating. A MariaDB/MySQL table is limited to 4096 columns (1017 for InnoDB), so the default leaves ample room for wide joins. With the C extension the limit is passed to libmariadb (MARIADB_OPT_MAX_COLUMNS, requires MariaDB Connector/C 3.3.20, 3.4.10 or newer).

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
    # map its content to ssl_* parameters (mariadb-c compatibility).
    if "ssl" in kwargs and isinstance(kwargs["ssl"], dict):
        ssl = kwargs.pop("ssl")
        for key in ["ca", "cert", "capath", "key", "cipher"]:
            if key in ssl:
                kwargs["ssl_%s" % key] = ssl[key]
        kwargs["ssl"] = True

    # Check if pool_name is specified
    pool_name = kwargs.get('pool_name')
    if pool_name:
        # 1.1 compatibility feature: the pool is registered globally and is
        # not owned by the caller
        warnings.warn(
            "The pool_name argument of connect() is deprecated and will be "
            "removed in 2.1. Use mariadb.ConnectionPool() or "
            "mariadb.create_pool() and obtain connections with their "
            "get_connection() method instead.",
            DeprecationWarning, stacklevel=2)
        if pool_name in _CONNECTION_POOLS:
            pool = _CONNECTION_POOLS[pool_name]
            pool._check_conn_args(kwargs)
        else:
            pool = _get_connection_pool_class()(**kwargs)
        return pool.get_connection()

    # Use SyncConnection if no custom class specified
    if connectionclass is None:
        connectionclass = SyncConnection

    connection = connectionclass(*args, **kwargs)
    return cast(SyncConnectionCommon, connection)


async def asyncConnect(*args: Any, connectionclass: type | None = None, **kwargs: Any) -> AsyncConnectionCommon:
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
    # map its content to ssl_* parameters (mariadb-c compatibility). Only a dict
    # is expanded here; bool/int/str values flow through to the boolean validator
    # in Configuration.from_dict (pure-Python) / the mariadb_c wrapper (C ext).
    if "ssl" in kwargs and isinstance(kwargs["ssl"], dict):
        ssl = kwargs.pop("ssl")
        for key in ["ca", "cert", "capath", "key", "cipher"]:
            if key in ssl:
                kwargs["ssl_%s" % key] = ssl[key]
        kwargs["ssl"] = True

    # Pools are not supported here: a named pool would either be created as a
    # side effect of connecting, or the connection arguments would be ignored
    # in favour of the configuration of an already existing pool.
    if 'pool_name' in kwargs:
        raise ProgrammingError(
            "pool_name is not supported by asyncConnect(). Use "
            "mariadb.create_async_pool() and obtain connections from the "
            "returned pool with its acquire() method."
        )

    # Use AsyncConnection if no custom class specified
    if connectionclass is None:
        connectionclass = connection_class  # Use the class selected by Windows+SSL workaround

    # Connect asynchronously using the classmethod
    return cast(AsyncConnectionCommon, await connectionclass.connect(*args, **kwargs))  # type: ignore[union-attr]


# Stub for ASAN detection
_have_asan = False

# Version information for the connector
def _parse_version_info(version_string: str) -> tuple[tuple[int, int, int, str] | tuple[int, int, int], int]:
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

# mariadbapi_version reports the version of the underlying MariaDB Connector/C
# (libmariadb) as returned by mysql_get_client_info(). It is only meaningful
# when a native implementation (C extension or binary wheel) is loaded; those
# modules re-export the value from their _mariadb C extension. The pure Python
# connector has no libmariadb, so it stays None.
mariadbapi_version = getattr(impl_selector.sync_connection, "mariadbapi_version", None)

# Load base version from release_info.py (generated at build time)
try:
    from .release_info import __version__ as _base_version
except ImportError:
    try:
        from importlib.metadata import version
        _base_version = version('mariadb')
    except ImportError:
        _base_version = "2.0.0.dev"

# Parse version info
version_tuple, version_numeric = _parse_version_info(_base_version)

# For compatibility
client_version_info = version_tuple
client_version = version_numeric

__author__ : str = "MariaDB Corporation"
__version__ : str = _base_version
__version_info__ : tuple[int, int, int, str] | tuple[int, int, int] = _parse_version_info(_base_version)[0]

# Connection pool support (lazy import)
_CONNECTION_POOLS: 'Dict[str, ConnectionPoolWrapper]' = {}

# Cache for pool classes (lazy loaded)
_ConnectionPoolClass = None

# Dynamic version properties that reflect the actual implementation being used
def __getattr__(name: str) -> Any:
    """
    Dynamic attribute access for version info and optional pooling support.
    Returns version information based on the actual implementation being used.
    """
    global _ConnectionPoolClass

    if name == 'ConnectionPool':
        # Lazy import and cache compatibility wrapper
        if _ConnectionPoolClass is None:
            _ConnectionPoolClass = _get_connection_pool_class()
        return _ConnectionPoolClass
    else:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def _pool_option_names() -> 'frozenset[str]':
    """
    The set of pool option names, from the single table in mariadb_pool.

    Resolved lazily: mariadb-pool is an optional dependency, so this is only
    reachable on the pool code paths. It is opaque to mypy (follow_imports =
    "skip"), hence the cast.
    """
    from mariadb_pool import POOL_OPTION_NAMES  # pyright: ignore[reportMissingImports]
    return cast('frozenset[str]', POOL_OPTION_NAMES)


def _resolve_pool_params(
    uri: str | None,
    explicit: 'Dict[str, Any]',
    connection_params: 'Dict[str, Any]',
) -> 'tuple[Dict[str, Any], Dict[str, Any]]':
    """
    Resolve pool configuration and connection parameters from a URI and kwargs.

    Pool-config values may be supplied as keyword arguments or in the URI query
    string; connection parameters likewise come from the URI and/or kwargs.
    Precedence in both cases: explicit keyword argument > URI value > default.

    Args:
        uri: Optional connection URI; ``None`` means no URI was supplied.
        explicit: Pool-config keyword arguments as passed to the factory; a value
            of ``None`` means "not supplied" and falls back to URI/default.
        connection_params: Connection keyword arguments (``**connection_params``).

    Returns:
        A ``(pool_config_kwargs, connection_params)`` tuple.

    Raises:
        ValueError: If ``uri`` is supplied but is not a connection URI, or if
            ``pool_name`` is supplied.
        PoolError: If a pool option holds a value that cannot be converted.
    """
    pool_options = _pool_option_names()
    uri_pool: 'Dict[str, Any]' = {}
    uri_conn: 'Dict[str, Any]' = {}
    if uri is not None:
        from mariadb_shared.uri_parser import is_connection_uri, parse_connection_uri
        if not is_connection_uri(uri):
            raise ValueError(
                f"Invalid connection URI: {uri!r}. The first positional argument must "
                "be a URI starting with 'mariadb://' or 'mysql://'; pass connection "
                "and pool options as keyword arguments instead."
            )
        for key, value in parse_connection_uri(uri).items():
            # Pool options are typed by PoolConfig.from_options(); the generic
            # URI parser must not touch them, since it leaves ping_threshold a
            # string and turns min_size=0 into False.
            if key in pool_options:
                uri_pool[key] = value
            else:
                uri_conn[key] = value

    # Connection params: explicit kwargs override URI values.
    uri_conn.update(connection_params)

    # A pool option may also arrive through **connection_params: the factories
    # name the canonical options in their signature, but the 1.1 spellings
    # (pool_size, pool_reset_connection, pool_validation_interval) are accepted
    # too rather than being forwarded to the connection factory and dropped.
    for key in [key for key in uri_conn if key in pool_options]:
        uri_pool[key] = uri_conn.pop(key)

    # pool_name would be handed to the connection factory, and connect() treats it
    # as a request for a named pool — so every connection this pool created would
    # in fact be borrowed from a second, registered pool.
    if 'pool_name' in uri_conn:
        raise ValueError(
            "pool_name is not supported by create_pool()/create_async_pool(), "
            "which return the pool object directly instead of registering it "
            "by name. Naming a pool is deprecated; keep the returned object."
        )

    # Pool config: explicit keyword argument > **kwargs spelling > URI query.
    # An option left unset is omitted entirely, so PoolConfig.from_options()
    # applies the default and reconciles the size bounds.
    resolved: 'Dict[str, Any]' = dict(uri_pool)
    resolved.update({key: value for key, value in explicit.items()
                     if value is not None})

    return resolved, uri_conn


def create_pool(
    uri: str | None = None,
    *,
    min_size: int | None = None,
    max_size: int | None = None,
    max_idle_time: float | None = None,
    max_lifetime: float | None = None,
    acquire_timeout: float | None = None,
    enable_health_check: bool | None = None,
    reset_connection: bool | None = None,
    ping_threshold: float | None = None,
    **connection_params: Any
) -> '_ConnectionPoolImpl':
    """
    Create a synchronous connection pool with clean separation of pool and connection options.

    Connection parameters can be provided as:
    1. A URI string as the first positional argument:
       mariadb://[user[:password]@][host][:port][/database][?option1=value1&option2=value2]
    2. A set of connection keyword arguments (host, user, password, ...)

    Pool-configuration options may also be supplied in the URI query string, e.g.
    ``mariadb://root@localhost/test?min_size=5&max_size=20``. Precedence for every
    option is: explicit keyword argument > URI value > default.

    Pool Configuration Parameters (keyword-only, or URI query string):
        pool_size (int): 1.1 spelling of a fixed-size pool; sets min_size and
            max_size together, an explicitly given bound wins over it
        min_size (int): Minimum number of connections in the pool (default: same as max_size)
        max_size (int): Maximum number of connections in the pool (default: 10)
        max_idle_time (float): Maximum time (seconds) a connection can be idle (default: 600.0)
        max_lifetime (float): Maximum lifetime (seconds) of a connection (default: 3600.0)
        acquire_timeout (float): Timeout (seconds) when acquiring a connection (default: 30.0)
        enable_health_check (bool): Enable periodic health checks (default: True)
        reset_connection (bool): Reset connection state on release (default: False),
            also accepted as 1.1's pool_reset_connection, whose 1.1 default was True
        ping_threshold (float): When taking a connection from the pool, ping it
            only if it has been idle longer than this (milliseconds,
            default: 500, 0 = always ping). This is 1.1's
            pool_validation_interval, under which name it is also accepted.

    Connection Parameters:
        uri (str): Optional connection URI (first positional argument)
        **connection_params: Additional connection parameters (ssl_ca, ssl_cert, etc.)

    Returns:
        ConnectionPool: A configured connection pool

    Raises:
        ValueError: If the first positional argument is not a connection URI.

    Example:
        pool = mariadb.create_pool(
            host='localhost',
            user='root',
            password='secret',
            database='test',
            min_size=5,
            max_size=20,
            ping_threshold=500
        )

        # or with a URI (pool options may live in the query string)
        pool = mariadb.create_pool(
            "mariadb://root:secret@localhost/test?min_size=5&max_size=20"
        )

        with pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()

        pool.close()
    """
    try:
        from mariadb_pool import ConnectionPool, PoolConfig  # pyright: ignore[reportMissingImports]
    except ImportError:
        raise ImportError(
            "Connection pooling is not available. "
            "Install mariadb-pool: pip install mariadb[pool]"
        )

    # Resolve pool config and connection params from URI + kwargs.
    pool_config_kwargs, connection_params = _resolve_pool_params(
        uri,
        {
            'min_size': min_size,
            'max_size': max_size,
            'max_idle_time': max_idle_time,
            'max_lifetime': max_lifetime,
            'acquire_timeout': acquire_timeout,
            'enable_health_check': enable_health_check,
            'reset_connection': reset_connection,
            'ping_threshold': ping_threshold,
        },
        connection_params,
    )
    pool_config = PoolConfig.from_options(**pool_config_kwargs)

    # Create pool with mariadb.connect as factory
    return cast('_ConnectionPoolImpl', ConnectionPool(
        connection_factory=connect,
        config=pool_config,
        **connection_params
    ))


async def create_async_pool(
    uri: str | None = None,
    *,
    min_size: int | None = None,
    max_size: int | None = None,
    max_idle_time: float | None = None,
    max_lifetime: float | None = None,
    acquire_timeout: float | None = None,
    enable_health_check: bool | None = None,
    reset_connection: bool | None = None,
    ping_threshold: float | None = None,
    **connection_params: Any
) -> '_AsyncConnectionPoolImpl':
    """
    Create an asynchronous connection pool with clean separation of pool and connection options.

    This function automatically calls pool.open() to pre-fill the pool with connections.

    Connection parameters can be provided as:
    1. A URI string as the first positional argument:
       mariadb://[user[:password]@][host][:port][/database][?option1=value1&option2=value2]
    2. A set of connection keyword arguments (host, user, password, ...)

    Pool-configuration options may also be supplied in the URI query string, e.g.
    ``mariadb://root@localhost/test?min_size=5&max_size=20``. Precedence for every
    option is: explicit keyword argument > URI value > default.

    Pool Configuration Parameters (keyword-only, or URI query string):
        pool_size (int): 1.1 spelling of a fixed-size pool; sets min_size and
            max_size together, an explicitly given bound wins over it
        min_size (int): Minimum number of connections in the pool (default: same as max_size)
        max_size (int): Maximum number of connections in the pool (default: 10)
        max_idle_time (float): Maximum time (seconds) a connection can be idle (default: 600.0)
        max_lifetime (float): Maximum lifetime (seconds) of a connection (default: 3600.0)
        acquire_timeout (float): Timeout (seconds) when acquiring a connection (default: 30.0)
        enable_health_check (bool): Enable periodic health checks (default: True)
        reset_connection (bool): Reset connection state on release (default: False),
            also accepted as 1.1's pool_reset_connection, whose 1.1 default was True
        ping_threshold (float): When taking a connection from the pool, ping it
            only if it has been idle longer than this (milliseconds,
            default: 500, 0 = always ping). This is 1.1's
            pool_validation_interval, under which name it is also accepted.

    Connection Parameters:
        uri (str): Optional connection URI (first positional argument)
        **connection_params: Additional connection parameters (ssl_ca, ssl_cert, etc.)

    Returns:
        AsyncConnectionPool: A configured and opened async connection pool

    Raises:
        ValueError: If the first positional argument is not a connection URI.

    Example:
        async def main():
            pool = await mariadb.create_async_pool(
                host='localhost',
                user='root',
                password='secret',
                database='test',
                min_size=5,
                max_size=20,
                ping_threshold=500
            )

            # or with a URI (pool options may live in the query string)
            pool = await mariadb.create_async_pool(
                "mariadb://root:secret@localhost/test?min_size=5&max_size=20"
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
        from mariadb_pool import AsyncConnectionPool, PoolConfig  # pyright: ignore[reportMissingImports]
    except ImportError:
        raise ImportError(
            "Async connection pooling is not available. "
            "Install mariadb-pool: pip install mariadb[pool]"
        )

    # Resolve pool config and connection params from URI + kwargs.
    pool_config_kwargs, connection_params = _resolve_pool_params(
        uri,
        {
            'min_size': min_size,
            'max_size': max_size,
            'max_idle_time': max_idle_time,
            'max_lifetime': max_lifetime,
            'acquire_timeout': acquire_timeout,
            'enable_health_check': enable_health_check,
            'reset_connection': reset_connection,
            'ping_threshold': ping_threshold,
        },
        connection_params,
    )
    pool_config = PoolConfig.from_options(**pool_config_kwargs)

    # Create pool with mariadb.asyncConnect as factory
    pool = AsyncConnectionPool(
        connection_factory=asyncConnect,
        config=pool_config,
        **connection_params
    )

    # Pre-fill the pool with connections
    await pool.open()

    return cast('_AsyncConnectionPoolImpl', pool)


def _get_connection_pool_class() -> type['ConnectionPoolWrapper']:
    """
    Get ConnectionPool class from mariadb_pool package.
    """
    try:
        from mariadb_pool import ConnectionPoolWrapper  # pyright: ignore[reportMissingImports]
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

        def __init__(self, uri_or_pool_name: str | None = None, uri: str | None = None, pool_name: Any = None, **kwargs: Any) -> None:
            """Initialize with mariadb.connect as factory and register in _CONNECTION_POOLS

            Args:
                uri_or_pool_name: Either a URI string or pool_name (first positional argument)
                uri: Optional URI string for connection parameters (deprecated, use first arg)
                pool_name: Optional name of the pool, deprecated (can be in URI
                    query params or as kwarg)
                **kwargs: Connection parameters and pool configuration

            Examples:
                pool = ConnectionPool("mariadb://user:pass@host/db")

                pool = ConnectionPool(uri="mariadb://user:pass@host/db")

                pool = ConnectionPool(host="localhost", user="root", database="test")
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
                # Naming a pool registers it globally, so any code in the
                # process can obtain a connection from it just by knowing the
                # name. Warned about here rather than in the base class, so the
                # reported location is the caller's and not this file's.
                warnings.warn(
                    "The pool_name argument is deprecated and will be removed "
                    "in 2.1, together with the pool registry it fills: a named "
                    "pool can be reached by any code in the process that knows "
                    "the name. Keep the pool object instead, or create it with "
                    "mariadb.create_pool().",
                    DeprecationWarning, stacklevel=2)
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


# Implementation selection is handled by impl_selector module at import time
