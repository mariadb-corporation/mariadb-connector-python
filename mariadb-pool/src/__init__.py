"""
MariaDB Connection Pool

This module provides advanced connection pooling capabilities for MariaDB
Connector/Python, including:
- Dynamic pool sizing
- Connection health checking
- Load balancing
- Connection lifecycle management
"""

# Load version from build-time generated release_info.py (ensures version sync)
try:
    from .release_info import __version__
except ImportError:
    # Fallback if release_info.py doesn't exist (development mode)
    # Try to get from package metadata
    try:
        from importlib.metadata import version
        __version__ = version('mariadb-pool')
    except ImportError:
        try:
            from importlib_metadata import version
            __version__ = version('mariadb-pool')
        except ImportError:
            # Final fallback - use hardcoded version that matches root project
            __version__ = "2.0.0.dev1"

# Parse version info
try:
    import re
    match = re.match(r'^(\d+)\.(\d+)\.(\d+)', __version__)
    if match:
        __version_info__ = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    else:
        __version_info__ = (2, 0, 0)
except Exception:
    __version_info__ = (2, 0, 0)

"""
mariadb_pool - Connection pooling for MariaDB Connector/Python
"""

from .pool import (
    ConnectionPool,
    AsyncConnectionPool,
    PoolConfig,
    PoolError,
)
from .connection_pool_wrapper import ConnectionPoolWrapper
from .async_connection_pool_wrapper import AsyncConnectionPoolWrapper

__all__ = [
    'ConnectionPool',
    'AsyncConnectionPool',
    'ConnectionPoolWrapper',
    'AsyncConnectionPoolWrapper',
    'PoolConfig',
    'PoolError'
]

__version__ = '2.0.0.dev1'
