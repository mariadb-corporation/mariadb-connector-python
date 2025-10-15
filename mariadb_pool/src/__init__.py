"""
MariaDB Advanced Connection Pool

This module provides advanced connection pooling capabilities for MariaDB
Connector/Python, including:
- Dynamic pool sizing
- Connection health checking
- Load balancing
- Connection lifecycle management
- Pool statistics and monitoring
"""

__version__ = "1.0.0"
__version_info__ = (1, 0, 0)
__author__ = "Georg Richter"

from mariadb_pool.pool import (
    ConnectionPool,
    PoolConfig,
    PoolStats,
    PoolError,
)

__all__ = [
    "ConnectionPool",
    "PoolConfig",
    "PoolStats",
    "PoolError",
    "__version__",
    "__version_info__",
    "__author__",
]
