# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Async compatibility wrapper for mariadb_pool.AsyncConnectionPool
Matches the 1.1 C extension API for connection pooling (async version).
"""

from types import TracebackType
from typing import Awaitable, Callable, Any, Dict, Optional, Type, TYPE_CHECKING

from mariadb import AsyncConnection
from .pool import AsyncConnectionPool as _AsyncPoolImpl, PoolConfig
from .connection_pool_wrapper import POOL_CONFIG_KEYS

# Import PoolError from shared exceptions
try:
    from mariadb_shared.exceptions import PoolError
except ImportError:
    # Fallback - import from pool module
    from .pool import PoolError
if TYPE_CHECKING:
    try:
        from mariadb.async_connection import AsyncConnection
    except ImportError:
        AsyncConnection = Any


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
    
    def __init__(self, connection_factory: Callable[..., Awaitable[AsyncConnection]], pool_name: Optional[str] = None, **kwargs: Any) -> None:
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
        pool_kwargs = {}
        conn_kwargs = {}
        
        for key, value in kwargs.items():
            if key in POOL_CONFIG_KEYS:
                pool_kwargs[key] = value
            else:
                conn_kwargs[key] = value
        
        config = PoolConfig.from_options(**pool_kwargs)

        # Create the actual async pool
        self._pool = _AsyncPoolImpl(
            connection_factory=connection_factory,
            config=config,
            **conn_kwargs
        )
        
        # Register in class-level registry only if pool has a name
        if pool_name is not None:
            self._registry[pool_name] = self
    
    async def open(self) -> None:
        """Open the pool and establish initial connections"""
        await self._pool.open()
    
    async def get_connection(self) -> AsyncConnection:
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
        pooled_conn = await self._pool._acquire()
        return pooled_conn.connection
    
    async def add_connection(self, connection: Optional[AsyncConnection] = None) -> None:
        """Add a connection to the pool
        
        Args:
            connection: Optional connection to add to the pool.
                       If provided, adds the existing connection.
                       If None, creates a new connection.
        """
        from .pool import AsyncPooledConnection
        
        async with self._pool._cond:
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
            self._pool._free.append(pooled_conn)
            self._pool._cond.notify()
    
    def set_config(self, **kwargs: Any) -> None:
        """
        Set pool configuration
        
        Args:
            **kwargs: Connection parameters to update
        """
        # Update connection parameters
        self._pool.connection_params.update(kwargs)

    async def close(self) -> None:
        """Close the pool and all connections"""
        await self._pool.close()
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
    def get_pool(cls, pool_name: str) -> Optional['AsyncConnectionPoolWrapper']:
        """Get a pool by name from the registry"""
        return cls._registry.get(pool_name)
    
    @classmethod
    def get_all_pools(cls) -> Dict[str, 'AsyncConnectionPoolWrapper']:
        """Get all registered pools"""
        return cls._registry.copy()
    
    @classmethod
    def clear_registry(cls) -> None:
        """Clear the pool registry (for testing)"""
        cls._registry.clear()
    
    async def __aenter__(self) -> 'AsyncConnectionPoolWrapper':
        """Enter async context manager"""
        await self.open()
        return self
    
    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> bool:
        """Exit async context manager and close pool"""
        await self.close()
        return False
