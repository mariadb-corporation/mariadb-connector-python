# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Compatibility wrapper for mariadb_pool.ConnectionPool
Matches the C extension API for connection pooling.
"""

from types import TracebackType
from typing import Callable, Any, Dict, Literal, Optional, Type, TYPE_CHECKING
from .pool import (ConnectionPool as _PoolImpl, PoolConfig,
                   POOL_OPTION_NAMES)

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

    # Shared ABC implemented by both pure-Python and C connections.
    from mariadb_shared.sync_connection_common import SyncConnectionCommon
# Keyword arguments which configure the pool itself: everything else is passed
# to the connection factory and is therefore part of the connection
# configuration. Naming, typing and reconciliation live in
# PoolConfig.from_options(), so every entry point behaves identically.
POOL_CONFIG_KEYS = POOL_OPTION_NAMES

# Keyword aliases accepted by connect(). The alias takes precedence over its
# canonical counterpart, like in Configuration.from_dict().
_CONN_ALIASES = (('username', 'user'), ('passwd', 'password'),
                 ('db', 'database'))


def connection_args(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns the connection relevant keyword arguments: pool_name and pool
    configuration keywords are removed, unset (None) values are ignored and
    aliases are resolved, so that two sets of keyword arguments describing the
    same connection compare equal.
    """

    args = {key: value for (key, value) in kwargs.items()
            if value is not None and key != 'pool_name'
            and key not in POOL_CONFIG_KEYS}
    for (alias, key) in _CONN_ALIASES:
        if alias in args:
            args[key] = args.pop(alias)
    return args


class ConnectionPoolWrapper:
    """
    Compatibility wrapper for mariadb_pool.ConnectionPool
    Matches the 1.1 C extension API for connection pooling.
    """
    
    # Class-level registry for pools
    _registry: Dict[str, 'ConnectionPoolWrapper'] = {}
    
    def __init__(self, connection_factory: Callable[..., 'SyncConnectionCommon'], pool_name: Optional[str] = None, **kwargs: Any) -> None:
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
        pool_kwargs = {}
        conn_kwargs = {}

        for key, value in kwargs.items():
            if key in POOL_CONFIG_KEYS:
                pool_kwargs[key] = value
            else:
                conn_kwargs[key] = value
        
        config = PoolConfig.from_options(**pool_kwargs)

        # Create the actual pool
        self._pool = _PoolImpl(
            connection_factory=connection_factory,
            config=config,
            **conn_kwargs
        )
        
        # Register in class-level registry only if pool has a name
        if pool_name is not None:
            self._registry[pool_name] = self
    
    def _check_conn_args(self, kwargs: Dict[str, Any]) -> None:
        """
        Check that the given connection arguments match the connection
        configuration of the pool and raise a PoolError if they don't.

        All connection arguments of the pool have to be provided: the order of
        the arguments, aliases (username, passwd, db) and pool keyword
        arguments don't matter, everything else has to be identical.

        Internally used by mariadb.connect() when a connection is requested
        from an already existing pool.
        """

        args = connection_args(kwargs)
        pool_args = connection_args(self._pool.connection_params)
        if args != pool_args:
            # report the names of the differing arguments, but not their
            # values, since these can contain the password
            diff = sorted(key for key in set(args) | set(pool_args)
                          if args.get(key) != pool_args.get(key))
            raise PoolError(
                f"Connection argument(s) {', '.join(diff)} don't match the "
                f"connection configuration of pool '{self.pool_name}'")

    def get_connection(self) -> 'SyncConnectionCommon':
        """Get a connection from the pool"""
        pool_conn = self._pool._acquire()
        return pool_conn.connection
    
    def add_connection(self, connection: Optional['SyncConnectionCommon'] = None) -> None:
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
    
    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> Literal[False]:
        """Exit context manager and close pool"""
        self.close()
        return False
