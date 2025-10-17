'''
MariaDB Connector/Python module enables python programs to access MariaDB and
MySQL databases, using an API which is compliant with the Python DB API 2.0
(PEP-249).

This is a pure Python implementation. For better performance, install the
optional C extension: pip install mariadb-python[c-extension]
'''

from .exceptions import (
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
)

# Fix module names for proper error display
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
from .cursors import Cursor
from .connections import Connection
from . import constants

# Connection class selection - determined at module initialization
_ConnectionClass = None

def _select_connection_implementation():
    """
    Select the best connection implementation based on availability and environment variables.
    
    This function is called once at module initialization to determine which
    connection class to use for all subsequent connections.
    """
    global _ConnectionClass
    
    import os
    
    # Import the pure Python implementation (always available)
    from .connections import Connection as PythonConnection
    
    # Check for C extension availability
    # We only check if the module exists, not if it can be imported yet
    # The actual import will happen when needed
    c_extension_available = False
    try:
        import importlib.util
        spec = importlib.util.find_spec('mariadb_c.src')
        if spec is not None:
            # Module exists - assume it's available
            # We'll do the actual import later when needed
            c_extension_available = True
    except Exception:
        c_extension_available = False
    
    # Check environment variable preference
    impl_preference = os.environ.get('MARIADB_PYTHON_CONNECTOR', '').lower()
    
    # Select implementation (version info is now handled dynamically)
    if impl_preference == 'mariadb':
        # Force pure Python implementation
        _ConnectionClass = PythonConnection
    elif impl_preference == 'mariadb_c':
        # Force C extension
        if c_extension_available:
            # Defer the actual import until needed - just mark that we want C extension
            _ConnectionClass = 'mariadb_c'
        else:
            raise ImportError("C extension (mariadb_c) was requested but is not available. "
                            "The C extension appears to be a placeholder. "
                            "Use MARIADB_PYTHON_CONNECTOR=mariadb to use the pure Python implementation.")
    else:
        # Default behavior: prefer C extension if available, fallback to pure Python
        if c_extension_available:
            # Defer the actual import until needed - just mark that we want C extension
            _ConnectionClass = 'mariadb_c'
        else:
            # Use pure Python implementation
            _ConnectionClass = PythonConnection

# Note: _select_connection_implementation() will be called after version variables are defined

__all__ = ["DataError", "DatabaseError", "Error", "IntegrityError",
           "InterfaceError", "InternalError", "NotSupportedError",
           "OperationalError", "PoolError", "ProgrammingError",
           "Warning", "Connection", "__version__", "__version_type__", "__version_info__",
           "__author__", "Cursor", "fieldinfo", "constants",
           "connect", "mariadbapi_version", "client_version_info", "client_version", "_have_asan"]


def connect(*args, connectionclass=None, **kwargs):
    """
    Creates a MariaDB Connection object.

    By default, the pure Python Connection class will be used.
    If the C extension is installed and no connectionclass is specified,
    the C extension will be used for better performance.

    Parameter connectionclass specifies a subclass of
    mariadb.Connection object. If not specified, default will be used.
    This optional parameter was added in version 1.1.0.

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
    - **`local_infile`** - Enables or disables the use of LOAD DATA LOCAL INFILE statements.
    - **`compress`** (default: `False`) - Uses the compressed protocol for client server communication. If the server doesn't support compressed protocol, the default protocol will be used.
    - **`init_command`** - Command(s) which will be executed when connecting and reconnecting to the database server
    - **`default_file`** - Read options from the specified option file. If the file is an empty string, default configuration file(s) will be used
    - **`default_group`** - Read options from the specified group
    - **`plugin_dir`** - Directory which contains MariaDB client plugins.
    - **`reconnect`** - Enables or disables automatic reconnect. Available since version 1.1.4
    - **`ssl_key`** - Defines a path to a private key file to use for TLS. This option requires that you use the absolute path, not a relative path. The specified key must be in PEM format
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
        - `mariadb` - Force pure Python implementation
        - `mariadb_c` - Force C extension (raises error if not available)
        - Not set or other values - Default behavior (prefer C extension, fallback to pure Python)

    """
    # Handle connection pooling (simplified for now)
    # if kwargs and "pool_name" in kwargs:
    #     pool_name = kwargs["pool_name"]
    #     if pool_name not in _CONNECTION_POOLS:
    #         pool = ConnectionPool(**kwargs)
    #     else:
    #         pool = _CONNECTION_POOLS[pool_name]
    #     return pool.get_connection()

    # Use pre-selected connection class if none specified
    if connectionclass is None:
        connectionclass = _ConnectionClass
        
    # Handle deferred C extension import
    if connectionclass == 'mariadb_c':
        # Now it's safe to import the C extension wrapper after injection is complete
        import mariadb_c.src.connections
        connectionclass = mariadb_c.src.connections.Connection

    connection = connectionclass(*args, **kwargs)
    
    # Validate that it's a proper Connection instance
    # For now, just check if it's our Connection class
    if not hasattr(connection, 'cursor'):
        raise ProgrammingError(f"{connection} is not a valid mariadb Connection")
        
    return connection



# Stub for ASAN detection
_have_asan = False

# Version information for the connector
def _parse_version_info(version_string):
    """
    Parse version string into numeric format
    
    Args:
        version_string: Version like "1.2.3-dev" or "2.0.0-ga"
        
    Returns:
        Tuple of (major, minor, patch) and numeric version (MMMMPP format)
    """
    import re
    
    # Extract major.minor.patch from version string
    # Handle formats like "1.2.3", "1.2.3-dev", "1.2.3-ga", etc.
    match = re.match(r'^(\d+)\.(\d+)\.(\d+)', version_string)
    if match:
        major = int(match.group(1))
        minor = int(match.group(2))
        patch = int(match.group(3))
        
        # Convert to 6-digit format: MMMMPP (2 digits each)
        version_info = major * 10000 + minor * 100 + patch
        
        return (major, minor, patch), version_info
    else:
        # Fallback for invalid version strings
        return (0, 0, 0), 0

# Load base version from _version.py (generated at build time)
mariadbapi_version = None
try:
    from ._version import __version__ as _base_version
except ImportError:
    # Fallback if _version.py doesn't exist (development mode)
    _base_version = "0.0.0-dev"

# Parse version info
version_tuple, version_numeric = _parse_version_info(_base_version)

# For compatibility
client_version_info = version_tuple
client_version = version_numeric

__author__ = "MariaDB Corporation"

# Dynamic version properties that reflect the actual implementation being used
def __getattr__(name):
    """
    Dynamic attribute access for version info.
    Returns version information based on the actual implementation being used.
    """
    if name == '__version__':
        return _get_current_version()
    elif name == '__version_type__':
        return _get_current_version_type()
    elif name == '__version_info__':
        return _get_current_version_info()
    else:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

def _get_current_version():
    """Get version based on current implementation selection"""
    if _ConnectionClass == 'mariadb_c':
        # C extension is selected
        try:
            import mariadb_c
            return mariadb_c.__version__
        except (ImportError, AttributeError):
            return _base_version + "-c"
    elif hasattr(_ConnectionClass, '__module__') and 'mariadb_c' in str(_ConnectionClass.__module__):
        # C extension connection class is loaded
        try:
            import mariadb_c
            return mariadb_c.__version__
        except (ImportError, AttributeError):
            return _base_version + "-c"
    else:
        # Pure Python implementation
        return _base_version + "-native"

def _get_current_version_type():
    """Get version type based on current implementation selection"""
    if _ConnectionClass == 'mariadb_c':
        return "c"
    elif hasattr(_ConnectionClass, '__module__') and 'mariadb_c' in str(_ConnectionClass.__module__):
        return "c"
    else:
        return "native"

def _get_current_version_info():
    """Get version info based on current implementation selection"""
    return version_numeric

# Initialize the connection implementation
_select_connection_implementation()