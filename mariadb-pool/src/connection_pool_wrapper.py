#
# Copyright (C) 2020-2021 Georg Richter and MariaDB Corporation AB

# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Library General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.

# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Library General Public License for more details.

# You should have received a copy of the GNU Library General Public
# License along with this library; if not see <http://www.gnu.org/licenses>
# or write to the Free Software Foundation, Inc.,
# 51 Franklin St., Fifth Floor, Boston, MA 02110, USA
#

"""
Compatibility wrapper for mariadb_pool.ConnectionPool
Matches the C extension API for connection pooling.
"""

from typing import Callable, Any, Dict, Optional
from .pool import ConnectionPool as _PoolImpl, PoolConfig

# Import PoolError from shared exceptions
try:
    from mariadb_shared.exceptions import PoolError
except ImportError:
    # Fallback - import from pool module
    from .pool import PoolError

MAX_POOL_SIZE = 64

class ConnectionPoolWrapper:
    """
    Compatibility wrapper for mariadb_pool.ConnectionPool
    Matches the C extension API for connection pooling.
    """
    
    # Class-level registry for pools
    _registry: Dict[str, 'ConnectionPoolWrapper'] = {}
    
    def __init__(self, connection_factory: Callable, pool_name: str = None, **kwargs):
        """
        Initialize connection pool
        
        Args:
            connection_factory: Function to create new connections (e.g., mariadb.connect)
            pool_name: Name of the pool (for registry)
            **kwargs: Connection parameters and pool configuration
        """
        if not pool_name:
            raise PoolError("pool_name is required")
        
        if pool_name in self._registry:
            raise PoolError(f"Pool '{pool_name}' already exists")
        
        self.pool_name = pool_name
        self.connection_factory = connection_factory
        
        # Separate pool config from connection params
        pool_config_keys = {
            'pool_size', 'pool_reset_connection', 'pool_validation_interval',
            'min_size', 'max_size', 'acquire_timeout'
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
        if 'pool_size' in pool_kwargs:
            config.max_size = pool_kwargs['pool_size']
            config.min_size = pool_kwargs['pool_size']
        if 'min_size' in pool_kwargs:
            config.min_size = pool_kwargs['min_size']
        if 'acquire_timeout' in pool_kwargs:
            config.acquire_timeout = pool_kwargs['acquire_timeout']
        if 'max_size' in pool_kwargs:
            config.max_size = pool_kwargs['max_size']
        if 'pool_validation_interval' in pool_kwargs:
            config.validation_interval = pool_kwargs['pool_validation_interval']

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
        
        # Register in class-level registry
        self._registry[pool_name] = self
    
    def get_connection(self):
        """Get a connection from the pool"""
        pool_conn = self._pool.acquire()
        return pool_conn.connection
    
    def add_connection(self, connection: Optional[Any] = None):
        """Add a connection to the pool
        
        Args:
            connection: Optional connection to add to the pool.
                       If provided, adds the existing connection.
                       If None, creates a new connection.
        """
        from .pool import PooledConnection
        
        with self._pool._lock:
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
            self._pool._pool.put_nowait(pooled_conn)
    
    def set_config(self, **kwargs):
        """
        Set pool configuration
        
        Args:
            **kwargs: Connection parameters to update
        """
        # Update connection parameters
        self._pool._set_config(**kwargs)        

    def close(self):
        """Close the pool and all connections"""
        self._pool.close()
        # Unregister from class-level registry
        if self.pool_name in self._registry:
            del self._registry[self.pool_name]
    
    @property
    def connection_count(self):
        """Get total number of connections (used + idle)"""
        return len(self._pool._all_connections)
    
    @property
    def pool_reset_connection(self):
        """Get reset_connection value"""
        return self._pool.config.reset_connection


    @property
    def pool_size(self):
        """Get maximum pool size"""
        return self._pool.config.max_size
    
    @property
    def max_size(self):
        """Get maximum pool size (alias for pool_size)"""
        return MAX_POOL_SIZE
    
    @classmethod
    def get_pool(cls, pool_name: str) -> 'ConnectionPoolWrapper':
        """Get a pool by name from the registry"""
        return cls._registry.get(pool_name)
    
    @classmethod
    def get_all_pools(cls) -> Dict[str, 'ConnectionPoolWrapper']:
        """Get all registered pools"""
        return cls._registry.copy()
    
    @classmethod
    def clear_registry(cls):
        """Clear the pool registry (for testing)"""
        cls._registry.clear()
