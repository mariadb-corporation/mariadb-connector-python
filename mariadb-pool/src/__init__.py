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
    from .release_info import __version__ as _base_version
except ImportError:
    try:
        from importlib.metadata import version
        _base_version = version('mariadb-pool')
    except ImportError:
        _base_version = "2.0.0.dev"
__version__ : str = _base_version


# Parse version info
# Handles "1.2.3", "1.2.3-dev", "1.2.3.dev", "2.0.0rc1", etc.
__version_info__: tuple[int, int, int, str] | tuple[int, int, int]
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
    POOL_OPTION_NAMES,
)
from .connection_pool_wrapper import ConnectionPoolWrapper

__all__ = [
    'ConnectionPool',
    'AsyncConnectionPool',
    'ConnectionPoolWrapper',
    'PoolConfig',
    'PoolError',
    'POOL_OPTION_NAMES'
]
