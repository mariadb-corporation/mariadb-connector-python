# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Async compatibility wrapper for mariadb_pool.AsyncConnectionPool
Matches the 1.1 C extension API for connection pooling (async version).
"""

from typing import Callable, Any, Dict, Optional
from .pool import AsyncConnectionPool as _AsyncPoolImpl, PoolConfig

# Import PoolError from shared exceptions
try:
    from mariadb_shared.exceptions import PoolError
except ImportError:
    # Fallback - import from pool module
    from .pool import PoolError

MAX_POOL_SIZE = 64


class AsyncConnectionPoolWrapper:
    """
    Async compatibility wrapper for mariadb_pool.AsyncConnectionPool
    Matches the 1.1 C extension API for connection pooling (async version).
    
    Usage:
        pool = AsyncConnectionPoolWrapper(
            connection_factory=mariadb.asyncConnect,
            pool_name="mypool",
            host="localhost",
            user="root"
        )
        await pool.open()
        conn = await pool.get_connection()
        await conn.close()
        await pool.close()
    """
    
    # Class-level registry for pools
    _registry: Dict[str, 'AsyncConnectionPoolWrapper'] = {}
    
    def __init__(self, connection_factory: Callable, pool_name: str = None, **kwargs):
        """
        Initialize async connection pool
        
        Args:
            connection_factory: Async function to create new connections (e.g., mariadb.asyncConnect)
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

        if (config.max_size >= MAX_POOL_SIZE):
            config.max_size = MAX_POOL_SIZE
        if (config.min_size >= MAX_POOL_SIZE):
            config.min_size = MAX_POOL_SIZE
            
        config.reset_connection = bool(pool_kwargs.get('pool_reset_connection', True))
        
        # Create the actual async pool
        self._pool = _AsyncPoolImpl(
            connection_factory=connection_factory,
            config=config,
            **conn_kwargs
        )
        
        # Register in class-level registry only if pool has a name
        if pool_name is not None:
            self._registry[pool_name] = self
    
    async def open(self):
        """Open the pool and establish initial connections"""
        await self._pool.open()
    
    async def get_connection(self):
        """
        Get a connection from the pool
        
        Usage:
            conn = await pool.get_connection()
            try:
                async with conn.cursor() as cursor:
                    await cursor.execute("SELECT * FROM users")
            finally:
                await conn.close()  # Returns connection to pool
        
        Or use connection as context manager:
            conn = await pool.get_connection()
            async with conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("SELECT * FROM users")
            # Connection automatically returned to pool
        
        Returns:
            Connection from the pool
        """
        pooled_conn = await self._pool.acquire()
        return pooled_conn.connection
    
    async def add_connection(self, connection: Optional[Any] = None):
        """Add a connection to the pool
        
        Args:
            connection: Optional connection to add to the pool.
                       If provided, adds the existing connection.
                       If None, creates a new connection.
        """
        from .pool import AsyncPooledConnection
        
        async with self._pool._lock:
            # Check if pool is at max size
            if len(self._pool._all_connections) >= self._pool.config.max_size:
                raise PoolError(f"Pool has reached maximum size of {self._pool.config.max_size}")
            
            if connection is not None:
                # Add existing connection to pool
                pooled_conn = AsyncPooledConnection(connection, self._pool)
                connection._set_pooled_connection(pooled_conn)
            else:
                # Create and add a new connection
                conn = await self.connection_factory(**self._pool.connection_params)
                pooled_conn = AsyncPooledConnection(conn, self._pool)
                conn._set_pooled_connection(pooled_conn)

            self._pool._all_connections.append(pooled_conn)
            pooled_conn.mark_idle()
            await self._pool._pool.put(pooled_conn)
    
    def set_config(self, **kwargs):
        """
        Set pool configuration
        
        Args:
            **kwargs: Connection parameters to update
        """
        # Update connection parameters
        self._pool.connection_params.update(kwargs)

    async def close(self):
        """Close the pool and all connections"""
        await self._pool.close()
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
        return self._pool.config.max_size
    
    @classmethod
    def get_pool(cls, pool_name: str) -> 'AsyncConnectionPoolWrapper':
        """Get a pool by name from the registry"""
        return cls._registry.get(pool_name)
    
    @classmethod
    def get_all_pools(cls) -> Dict[str, 'AsyncConnectionPoolWrapper']:
        """Get all registered pools"""
        return cls._registry.copy()
    
    @classmethod
    def clear_registry(cls):
        """Clear the pool registry (for testing)"""
        cls._registry.clear()
    
    async def __aenter__(self):
        """Enter async context manager"""
        await self.open()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context manager and close pool"""
        await self.close()
        return False
