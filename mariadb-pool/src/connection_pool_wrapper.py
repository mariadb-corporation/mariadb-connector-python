# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Compatibility wrapper for mariadb_pool.ConnectionPool
Matches the C extension API for connection pooling.
"""

from typing import Callable, Any, Dict, Optional, TYPE_CHECKING, Union
from .pool import ConnectionPool as _PoolImpl, PoolConfig

# Import PoolError from shared exceptions
try:
    from mariadb_shared.exceptions import PoolError
except ImportError:
    # Fallback - import from pool module
    from .pool import PoolError

# Type hints for connection types
if TYPE_CHECKING:
    try:
        from mariadb.sync_connection import SyncConnection
    except ImportError:
        SyncConnection = Any
    
    try:
        from mariadb_c import Connection as CConnection
    except ImportError:
        CConnection = Any
MAX_POOL_SIZE = 64

class ConnectionPoolWrapper:
    """
    Compatibility wrapper for mariadb_pool.ConnectionPool
    Matches the 1.1 C extension API for connection pooling.
    """
    
    # Class-level registry for pools
    _registry: Dict[str, 'ConnectionPoolWrapper'] = {}
    
    def __init__(self, connection_factory: Callable, pool_name: Optional[str] = None, **kwargs: Any) -> None:
        """
        Initialize connection pool
        
        Args:
            connection_factory: Function to create new connections (e.g., mariadb.connect)
            pool_name: Name of the pool (for registry)
            **kwargs: Connection parameters and pool configuration
        """
        # pool_name is optional - if not provided, pool can be used directly
        # but won't be registered in the class registry
        if pool_name is not None:
            if pool_name in self._registry:
                raise PoolError(f"Pool '{pool_name}' already exists")
        
        self.pool_name = pool_name
        self.connection_factory = connection_factory
        
        # Separate pool config from connection params
        pool_config_keys = {
            'pool_size', 'pool_reset_connection', 'pool_validation_interval',
            'min_size', 'max_size', 'acquire_timeout', 'ping_threshold'
        }
        pool_kwargs = {}
        conn_kwargs = {}
        
        for key, value in kwargs.items():
            if key in pool_config_keys:
                pool_kwargs[key] = value
            else:
                conn_kwargs[key] = value
        
        # Create pool configuration
        config = PoolConfig()
        
        # Track which size parameters were explicitly set
        has_pool_size = 'pool_size' in pool_kwargs
        has_min_size = 'min_size' in pool_kwargs
        has_max_size = 'max_size' in pool_kwargs
        
        if has_pool_size:
            config.max_size = pool_kwargs['pool_size']
            config.min_size = pool_kwargs['pool_size']
        if has_min_size:
            config.min_size = pool_kwargs['min_size']
        if has_max_size:
            config.max_size = pool_kwargs['max_size']
            
        # If only min_size or max_size is set (but not both), make them equal
        if has_min_size and not has_max_size and not has_pool_size:
            config.max_size = config.min_size
        elif has_max_size and not has_min_size and not has_pool_size:
            config.min_size = config.max_size
            
        if 'acquire_timeout' in pool_kwargs:
            config.acquire_timeout = pool_kwargs['acquire_timeout']
        if 'pool_validation_interval' in pool_kwargs:
            config.validation_interval = pool_kwargs['pool_validation_interval']
        if 'ping_threshold' in pool_kwargs:
            config.ping_threshold = pool_kwargs['ping_threshold']

        if (config.max_size >= MAX_POOL_SIZE):
            config.max_size = MAX_POOL_SIZE
        if (config.min_size >= MAX_POOL_SIZE):
            config.min_size = MAX_POOL_SIZE
            
        config.reset_connection = bool(pool_kwargs.get('pool_reset_connection', True))
        
        # Create the actual pool
        self._pool = _PoolImpl(
            connection_factory=connection_factory,
            config=config,
            **conn_kwargs
        )
        
        # Register in class-level registry only if pool has a name
        if pool_name is not None:
            self._registry[pool_name] = self
    
    def get_connection(self) -> Union['SyncConnection', 'CConnection']:
        """Get a connection from the pool"""
        pool_conn = self._pool._acquire()
        return pool_conn.connection
    
    def add_connection(self, connection: Optional[Union['SyncConnection', 'CConnection']] = None) -> None:
        """Add a connection to the pool
        
        Args:
            connection: Optional connection to add to the pool.
                       If provided, adds the existing connection.
                       If None, creates a new connection.
        """
        from .pool import PooledConnection
        
        with self._pool._cond:
            # Check if pool is at max size
            if len(self._pool._all_connections) >= self._pool.config.max_size:
                raise PoolError(f"Pool has reached maximum size of {self._pool.config.max_size}")
            
            if connection is not None:
                # Add existing connection to pool
                pooled_conn = PooledConnection(connection, self._pool)
                connection._set_pooled_connection(pooled_conn)
            else:
                # Create and add a new connection
                conn = self.connection_factory(**self._pool.connection_params)
                pooled_conn = PooledConnection(conn, self._pool)
                conn._set_pooled_connection(pooled_conn)

            self._pool._all_connections.append(pooled_conn)
            pooled_conn.mark_idle()
            self._pool._free.append(pooled_conn)
            self._pool._cond.notify()
    
    def set_config(self, **kwargs: Any) -> None:
        """
        Set pool configuration
        
        Args:
            **kwargs: Connection parameters to update
        """
        # Update connection parameters
        self._pool._set_config(**kwargs)        

    def close(self) -> None:
        """Close the pool and all connections"""
        self._pool.close()
        # Unregister from class-level registry
        if self.pool_name in self._registry:
            del self._registry[self.pool_name]
    
    @property
    def connection_count(self) -> int:
        """Get total number of connections (used + idle)"""
        return len(self._pool._all_connections)
    
    @property
    def pool_reset_connection(self) -> bool:
        """Get reset_connection value"""
        return self._pool.config.reset_connection


    @property
    def pool_size(self) -> int:
        """Get maximum pool size"""
        return self._pool.config.max_size
    
    @property
    def max_size(self) -> int:
        """Get maximum pool size (alias for pool_size)"""
        return self._pool.config.max_size
    
    @classmethod
    def get_pool(cls, pool_name: str) -> Optional['ConnectionPoolWrapper']:
        """Get a pool by name from the registry"""
        return cls._registry.get(pool_name)
    
    @classmethod
    def get_all_pools(cls) -> Dict[str, 'ConnectionPoolWrapper']:
        """Get all registered pools"""
        return cls._registry.copy()
    
    @classmethod
    def clear_registry(cls) -> None:
        """Clear the pool registry (for testing)"""
        cls._registry.clear()
    
    def __enter__(self) -> 'ConnectionPoolWrapper':
        """Enter context manager"""
        return self
    
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        """Exit context manager and close pool"""
        self.close()
        return False
