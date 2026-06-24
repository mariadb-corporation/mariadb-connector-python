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
            from importlib_metadata import version  # type: ignore[no-redef]
            __version__ = version('mariadb-pool')
        except ImportError:
            # Final fallback - use development version to indicate release_info.py generation failed
            __version__ = "2.0.0.dev1"

# Parse version info
# Handles "1.2.3", "1.2.3-dev", "1.2.3.dev", "2.0.0rc1", etc.
__version_info__: tuple
try:
    import re
    match = re.match(r'^(\d+)\.(\d+)\.(\d+)([.-](.+)|([a-zA-Z].*))?$', __version__)
    if match:
        suffix = match.group(5) or match.group(6)
        if suffix:
            __version_info__ = (int(match.group(1)), int(match.group(2)), int(match.group(3)), suffix)
        else:
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
