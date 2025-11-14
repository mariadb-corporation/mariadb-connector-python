'''
MariaDB Connector/Python module enables python programs to access MariaDB and
MySQL databases, using an API which is compliant with the Python DB API 2.0
(PEP-249).
'''

# Import exceptions from shared package to avoid circular dependencies
from mariadb_shared.exceptions import (
    Error,
    Warning,
    InterfaceError,
    DatabaseError,
    InternalError,
    NotSupportedError,
    OperationalError,
    ProgrammingError,
    IntegrityError,
    DataError
)
from .cursors import Cursor
from .connections import Connection
# disable for now, until tests are in place
# from mariadb_c.pooling import *

# Version information for the C extension connector
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

# Load version from build-time generated release_info.py (ensures version sync)
try:
    from .release_info import __version__ as _base_version
except ImportError:
    # Fallback if release_info.py doesn't exist (development mode)
    # Try to get from package metadata
    try:
        from importlib.metadata import version
        _base_version = version('mariadb_c')
    except ImportError:
        try:
            from importlib_metadata import version
            _base_version = version('mariadb_c')
        except ImportError:
            # Final fallback - use hardcoded version that matches root project
            _base_version = "2.0.0.dev"

# Parse version info
version_tuple, version_numeric = _parse_version_info(_base_version)

# Set version variables for C extension
# Append '-c' suffix to the version string (after any existing suffix)
if len(version_tuple) == 4:
    # Has suffix like 'dev', append '-c' to make it 'dev-c'
    __version__ = f"{version_tuple[0]}.{version_tuple[1]}.{version_tuple[2]}.{version_tuple[3]}-c"
else:
    # No suffix, just append '-c'
    __version__ = _base_version + "-c"

__version_info__ = version_tuple  # Use tuple, not numeric
__version_type__ = "c"
__author__ = "MariaDB Corporation"

# For compatibility
mariadbapi_version = _base_version
client_version_info = version_tuple
client_version = version_numeric

__all__ = ["DataError", "DatabaseError", "Error", "IntegrityError",
           "InterfaceError", "InternalError", "NotSupportedError",
           "OperationalError", "ProgrammingError",
           "Warning", "Connection", "__version__", "__version_type__", "__version_info__",
           "__author__", "Cursor", "fieldinfo", "_have_asan", "connect"]


def connect(*args, connectionclass=Connection, **kwargs):
    """
    Creates a MariaDB Connection object.

    By default, the standard connectionclass mariadb_c.connections.Connection
    will be created.

    Parameter connectionclass specifies a subclass of
    mariadb_c.Connection object. If not specified, default will be used.
    This optional parameter was added in version 1.1.0.

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
    
    connection = connectionclass(*args, **kwargs)
    if not isinstance(connection, Connection):
        raise ProgrammingError("%s is not an instance of "
                                       "mariadb_c.Connection" % connection)
    return connection


# Parse version info using the same logic as main package
client_version_info, client_version = _parse_version_info(mariadbapi_version)
