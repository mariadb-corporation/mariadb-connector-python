# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Advanced Connection Pool Implementation
"""

import threading
import asyncio
import time
import queue
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Dict
from contextlib import contextmanager, asynccontextmanager

# Import PoolError from shared exceptions
try:
    from mariadb_shared.exceptions import PoolError
    from mariadb_shared.constants.STATUS import IN_TRANS
except ImportError:
    # Fallback for standalone usage
    class PoolError(Exception):
        """Exception raised for pool-related errors"""
        pass


@dataclass
class PoolConfig:
    """
    Configuration for connection pool
    
    Attributes:
        min_size: Minimum number of connections in the pool
        max_size: Maximum number of connections in the pool
        max_idle_time: Maximum time (seconds) a connection can be idle before being closed
        max_lifetime: Maximum lifetime (seconds) of a connection
        validation_interval: Interval (seconds) between connection validations
        acquire_timeout: Timeout (seconds) when acquiring a connection
        enable_health_check: Enable periodic health checks on idle connections
    """
    min_size: int = 10
    max_size: int = 10
    max_idle_time: float = 600.0  # 10 minutes
    max_lifetime: float = 3600.0  # 1 hour
    validation_interval: float = 30.0  # 30 seconds
    acquire_timeout: float = 30.0  # 30 seconds
    enable_health_check: bool = True
    reset_connection: bool = False


class BasePooledConnection:
    """
    Base wrapper for a pooled connection
    
    Tracks connection metadata and lifecycle
    """
    
    def __init__(self, connection: Any, pool: Any):
        self.connection = connection
        self.pool = pool
        self.created_at = time.time()
        self.last_used = time.time()
        self.use_count = 0
        self.in_use = False
        
    def mark_in_use(self):
        """Mark connection as in use"""
        self.in_use = True
        self.use_count += 1
        self.last_used = time.time()
        
    def mark_idle(self):
        """Mark connection as idle"""
        self.in_use = False
        self.last_used = time.time()
        
    def is_expired(self, max_lifetime: float, max_idle_time: float) -> bool:
        """Check if connection has expired"""
        now = time.time()
        age = now - self.created_at
        idle_time = now - self.last_used
        
        return age > max_lifetime or (not self.in_use and idle_time > max_idle_time)


class PooledConnection(BasePooledConnection):
    """Sync pooled connection wrapper"""
    
    def is_healthy(self) -> bool:
        """
        Check if connection is healthy
        """
        try:
            self.connection.ping()
            return True
        except Exception:
            return False
    
    def return_to_pool(self):
        """Return this connection to the pool"""
        self.pool.release(self)

    def closeSilently(self):
        try:
            self.connection._set_pooled_connection(None)
            self.connection.close()
        except Exception:
            pass


class AsyncPooledConnection(BasePooledConnection):
    """Async pooled connection wrapper"""
    
    async def is_healthy(self) -> bool:
        """
        Check if connection is healthy
        """
        try:
            await self.connection.ping()
            return True
        except Exception:
            return False
    
    def return_to_pool(self):
        """Return this connection to the pool"""
        asyncio.create_task(self.pool.release(self))

    async def closeSilently(self):
        try:
            self.connection._set_pooled_connection(None)
            await self.connection.close()
        except Exception:
            pass
    


class ConnectionPool:
    """
    Advanced connection pool for MariaDB
    
    Provides dynamic pool sizing, health checking, and connection lifecycle management.
    """
    
    def __init__(
        self,
        connection_factory: Callable[[], Any],
        config: Optional[PoolConfig] = None,
        **connection_params
    ):
        """
        Initialize connection pool
        
        Args:
            connection_factory: Callable that creates new connections
            config: Pool configuration
            **connection_params: Parameters to pass to connection factory
        """
        self.connection_factory = connection_factory
        self.connection_params = {}
        self.config = config or PoolConfig()
        
        self._pool: queue.Queue[PooledConnection] = queue.Queue(maxsize=self.config.max_size)
        self._all_connections: list[PooledConnection] = []
        self._lock = threading.RLock()
        self._closed = False
        self._shutdown_event = threading.Event()  # For immediate thread shutdown
        self._maintenance_thread = None

        if (len(connection_params) > 0):
            self._set_config(**connection_params)

    def _set_config(self, **kwargs):
        """
        Set pool configuration
        
        Args:
            **kwargs: Connection parameters to update
        """
        # Update connection parameters
        self.connection_params.update(kwargs)
        
        # Only initialize connections if we have connection parameters
        # Check for essential connection parameters (at least one of: host, user, database)
        has_connection_params = any(key in self.connection_params 
                                   for key in ['host', 'user', 'database', 'unix_socket'])
        
        if has_connection_params:
            self._ensure_min_connections()
            # Start background maintenance thread
            if self.config.enable_health_check and not self._maintenance_thread:
                self._maintenance_thread = threading.Thread(
                    target=self._maintenance_loop,
                    daemon=True
                )
                self._maintenance_thread.start()

    def _create_connection(self) -> PooledConnection:
        """Create a new pooled connection"""
        with self._lock:
            if len(self._all_connections) >= self.config.max_size:
                raise PoolError(f"Pool has reached maximum size of {self.config.max_size}")
                
            try:
                conn = self.connection_factory(**self.connection_params)
                pooled_conn = PooledConnection(conn, self)
                conn._set_pooled_connection(pooled_conn)

                self._all_connections.append(pooled_conn)
                return pooled_conn
            except Exception as e:
                raise PoolError(f"Failed to create connection: {e}") from e
                
    def _ensure_min_connections(self):
        """Ensure minimum number of connections exist"""
        with self._lock:
            current_count = len(self._all_connections)
            for _ in range(self.config.min_size - current_count):
                try:
                    pooled_conn = self._create_connection()
                    pooled_conn.mark_idle()
                    if self._closed:
                        pooled_conn.closeSilently()
                    else:
                        self._pool.put_nowait(pooled_conn)
                except Exception:
                    break
                    
    def _maintenance_loop(self):
        """Background thread for pool maintenance"""
        while not self._closed:
            self._cleanup_expired_connections()
            self._ensure_min_connections()
            # Use event.wait() instead of time.sleep() for immediate shutdown
            if self._shutdown_event.wait(timeout=self.config.validation_interval):
                break  # Event was set, exit immediately
            
    def _cleanup_expired_connections(self):
        """Remove expired connections from pool"""
        with self._lock:
            for pool_conn in list(self._all_connections):
                if not pool_conn.in_use and pool_conn.is_expired(self.config.max_lifetime, self.config.max_idle_time):
                    pool_conn.closeSilently()
                    self._all_connections.remove(pool_conn)

    def acquire(self, timeout: Optional[float] = None) -> PooledConnection:
        """
        Acquire a connection from the pool
        
        Args:
            timeout: Timeout in seconds (uses config default if None)
            
        Returns:
            Database connection object
        """
        if self._closed:
            raise PoolError("Pool is closed")
            
        timeout = timeout if timeout is not None else self.config.acquire_timeout

        # Check if we can create a new connection before blocking
        can_create_new = len(self._all_connections) < self.config.max_size
        
        # Use a short timeout if we can create new connections
        get_timeout = 0.1 if can_create_new else timeout
        
        try:
            # Try to get an existing connection
            pooled_conn = self._pool.get(timeout=get_timeout)
            # Validate connection health
            if not pooled_conn.is_healthy():
                # Connection is unhealthy, remove it and create a new one atomically
                with self._lock:
                    pooled_conn.closeSilently()
                    if pooled_conn in self._all_connections:
                        self._all_connections.remove(pooled_conn)
                    # Create new connection while still holding the lock
                    # to ensure atomic remove+create operation
                    if len(self._all_connections) >= self.config.max_size:
                        raise PoolError(f"Pool has reached maximum size of {self.config.max_size}")
                    try:
                        conn = self.connection_factory(**self.connection_params)
                        pooled_conn = PooledConnection(conn, self)
                        conn._set_pooled_connection(pooled_conn)
                        self._all_connections.append(pooled_conn)
                    except Exception as e:
                        raise PoolError(f"Failed to create connection: {e}") from e
                
        except queue.Empty:
            # No idle connections, try to create a new one
            try:
                pooled_conn = self._create_connection()
            except PoolError:
                # Can't create new connection, wait longer for an existing one
                if timeout and timeout > get_timeout:
                    try:
                        pooled_conn = self._pool.get(timeout=timeout - get_timeout)
                    except queue.Empty:
                        raise PoolError("No connections available and pool is at maximum size")
                else:
                    raise PoolError("No connections available and pool is at maximum size")
                
        pooled_conn.mark_in_use()
        return pooled_conn
        
    def release(self, pool_conn: PooledConnection):
        """
        Release a connection back to the pool
        
        Args:
            connection: Connection to release
        """
        if self._closed:
            return
            
        with self._lock:
                
            pool_conn.mark_idle()
            
            # Reset or rollback connection before returning to pool
            try:
                conn = pool_conn.connection
                
                # Reset connection if reset_connection is enabled
                if self.config.reset_connection:
                    conn.reset()
                # Or rollback if in transaction
                elif (conn.server_status & IN_TRANS) > 0:
                    conn.rollback()

            except Exception:
                # If reset/rollback fails, close the connection
                pool_conn.closeSilently()
                if pool_conn in self._all_connections:
                    self._all_connections.remove(pool_conn)
                return
            
            # Check if connection should be kept
            if pool_conn.is_expired(self.config.max_lifetime, self.config.max_idle_time):
                pool_conn.closeSilently()
                if pool_conn in self._all_connections:
                    self._all_connections.remove(pool_conn)
            else:
                try:
                    self._pool.put_nowait(pool_conn)
                except queue.Full:
                    # Pool is full, close the connection
                    pool_conn.closeSilently()
                    if pool_conn in self._all_connections:
                        self._all_connections.remove(pool_conn)
                        
    @contextmanager
    def connection(self, timeout: Optional[float] = None):
        """
        Context manager for acquiring and releasing connections
        
        Args:
            timeout: Timeout in seconds
            
        Example:
            with pool.connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
        """
        pool_conn = self.acquire(timeout=timeout)
        try:
            yield pool_conn.conn
        finally:
            self.release(pool_conn)
            
    def close(self):
        """Close the pool and all connections"""
        self._closed = True
        # Signal maintenance thread to stop immediately
        self._shutdown_event.set()

        # Wait for maintenance thread to finish
        if self._maintenance_thread and self._maintenance_thread.is_alive():
            self._maintenance_thread.join(timeout=5.0)
            self._maintenance_thread = None
 
        with self._lock:
            for pooled_conn in self._all_connections:
                pooled_conn.closeSilently()
            self._all_connections.clear()
            
            # Clear the queue
            while not self._pool.empty():
                try:
                    self._pool.get_nowait()
                except queue.Empty:
                    break
        
                    
    def __enter__(self):
        """Context manager entry"""
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
        return False


class AsyncConnectionPool:
    """
    Advanced async connection pool for MariaDB
    
    Provides dynamic pool sizing, health checking, and connection lifecycle management.
    
    Usage:
        pool = AsyncConnectionPool(host="localhost", user="root", database="test")
        await pool.open()
        
        # Use the pool
        async with pool.connection() as conn:
            ...
        
        await pool.close()
    """
    
    def __init__(
        self,
        connection_factory: Callable = None,
        config: Optional[PoolConfig] = None,
        **connection_params
    ):
        """
        Initialize async connection pool (call open() to establish connections)
        
        Args:
            connection_factory: Async callable that creates new connections
            config: Pool configuration
            **connection_params: Parameters to pass to connection factory
        """
        self.connection_factory = connection_factory
        self.connection_params = connection_params
        self.config = config or PoolConfig()
        
        self._pool: asyncio.Queue[AsyncPooledConnection] = asyncio.Queue(maxsize=self.config.max_size)
        self._all_connections: list[AsyncPooledConnection] = []
        self._lock = asyncio.Lock()
        self._closed = False
        self._maintenance_task = None
        self._opened = False

    async def open(self):
        """
        Open the pool and establish initial connections.
        
        This method must be called before using the pool.
        """
        if self._opened:
            return
        
        # Only initialize connections if we have connection parameters
        has_connection_params = any(key in self.connection_params 
                                   for key in ['host', 'user', 'database', 'unix_socket'])
        
        if has_connection_params:
            await self._ensure_min_connections()
            # Start background maintenance task
            if self.config.enable_health_check and not self._maintenance_task:
                self._maintenance_task = asyncio.create_task(self._maintenance_loop())
        
        self._opened = True

    async def _create_connection_unlocked(self) -> AsyncPooledConnection:
        """Create a new pooled connection (must be called with lock held)"""
        if len(self._all_connections) >= self.config.max_size:
            raise PoolError(f"Pool has reached maximum size of {self.config.max_size}")
            
        try:
            conn = await self.connection_factory(**self.connection_params)
            pooled_conn = AsyncPooledConnection(conn, self)
            conn._set_pooled_connection(pooled_conn)

            self._all_connections.append(pooled_conn)
            return pooled_conn
        except Exception as e:
            raise PoolError(f"Failed to create connection: {e}") from e

    async def _create_connection(self) -> AsyncPooledConnection:
        """Create a new pooled connection"""
        async with self._lock:
            return await self._create_connection_unlocked()
                
    async def _ensure_min_connections(self):
        """Ensure minimum number of connections exist"""
        async with self._lock:
            current_count = len(self._all_connections)
            for _ in range(self.config.min_size - current_count):
                try:
                    pooled_conn = await self._create_connection_unlocked()
                    pooled_conn.mark_idle()
                    await self._pool.put(pooled_conn)
                except Exception:
                    break
                    
    async def _maintenance_loop(self):
        """Background task for pool maintenance"""
        while not self._closed:
            await asyncio.sleep(self.config.validation_interval)
            await self._cleanup_expired_connections()
            await self._ensure_min_connections()
            
    async def _cleanup_expired_connections(self):
        """Remove expired connections from pool"""
        async with self._lock:
            for pool_conn in list(self._all_connections):
                if not pool_conn.in_use and pool_conn.is_expired(self.config.max_lifetime, self.config.max_idle_time):
                    await pool_conn.closeSilently()
                    self._all_connections.remove(pool_conn)

    async def acquire(self, timeout: Optional[float] = None) -> AsyncPooledConnection:
        """
        Acquire a connection from the pool
        
        Args:
            timeout: Timeout in seconds (uses config default if None)
            
        Returns:
            Database connection object
        """
        if self._closed:
            raise PoolError("Pool is closed")
            
        timeout = timeout if timeout is not None else self.config.acquire_timeout

        # Check if we can create a new connection before blocking
        can_create_new = len(self._all_connections) < self.config.max_size
        
        # Use a short timeout if we can create new connections
        get_timeout = 0.1 if can_create_new else timeout
        
        try:
            # Try to get an existing connection
            pooled_conn = await asyncio.wait_for(self._pool.get(), timeout=get_timeout)
            # Validate connection health
            if not await pooled_conn.is_healthy():
                # Connection is unhealthy, remove it and create a new one atomically
                async with self._lock:
                    await pooled_conn.closeSilently()
                    if pooled_conn in self._all_connections:
                        self._all_connections.remove(pooled_conn)
                    # Create new connection while still holding the lock
                    if len(self._all_connections) >= self.config.max_size:
                        raise PoolError(f"Pool has reached maximum size of {self.config.max_size}")
                    try:
                        conn = await self.connection_factory(**self.connection_params)
                        pooled_conn = AsyncPooledConnection(conn, self)
                        conn._set_pooled_connection(pooled_conn)
                        self._all_connections.append(pooled_conn)
                    except Exception as e:
                        raise PoolError(f"Failed to create connection: {e}") from e
                
        except asyncio.TimeoutError:
            # No idle connections, try to create a new one
            try:
                pooled_conn = await self._create_connection()
            except PoolError:
                # Can't create new connection, wait longer for an existing one
                if timeout and timeout > get_timeout:
                    try:
                        pooled_conn = await asyncio.wait_for(self._pool.get(), timeout=timeout - get_timeout)
                    except asyncio.TimeoutError:
                        raise PoolError("No connections available and pool is at maximum size")
                else:
                    raise PoolError("No connections available and pool is at maximum size")
                
        pooled_conn.mark_in_use()
        return pooled_conn
        
    async def release(self, pool_conn: AsyncPooledConnection):
        """
        Release a connection back to the pool
        
        Args:
            connection: Connection to release
        """
        if self._closed:
            return
            
        async with self._lock:
                
            pool_conn.mark_idle()
            
            # Reset or rollback connection before returning to pool
            try:
                conn = pool_conn.connection
                
                # Reset connection if reset_connection is enabled
                if self.config.reset_connection:
                    await conn.reset()
                # Or rollback if in transaction
                elif (conn.server_status & IN_TRANS) > 0:
                    await conn.rollback()

            except Exception:
                # If reset/rollback fails, close the connection
                await pool_conn.closeSilently()
                if pool_conn in self._all_connections:
                    self._all_connections.remove(pool_conn)
                return
            
            # Check if connection should be kept
            if pool_conn.is_expired(self.config.max_lifetime, self.config.max_idle_time):
                await pool_conn.closeSilently()
                if pool_conn in self._all_connections:
                    self._all_connections.remove(pool_conn)
            else:
                try:
                    self._pool.put_nowait(pool_conn)
                except asyncio.QueueFull:
                    # Pool is full, close the connection
                    await pool_conn.closeSilently()
                    if pool_conn in self._all_connections:
                        self._all_connections.remove(pool_conn)
                        
    @asynccontextmanager
    async def connection(self, timeout: Optional[float] = None):
        """
        Async context manager for acquiring and releasing connections
        
        Args:
            timeout: Timeout in seconds
            
        Example:
            async with pool.connection() as conn:
                cursor = conn.cursor()
                await cursor.execute("SELECT 1")
        """
        pool_conn = await self.acquire(timeout=timeout)
        try:
            yield pool_conn.connection
        finally:
            await self.release(pool_conn)
            
    async def close(self):
        """Close the pool and all connections"""
        self._closed = True
        
        # Cancel maintenance task
        if self._maintenance_task:
            self._maintenance_task.cancel()
            try:
                await self._maintenance_task
            except asyncio.CancelledError:
                pass
        
        async with self._lock:
            for pooled_conn in self._all_connections:
                await pooled_conn.closeSilently()
            self._all_connections.clear()
            
            # Clear the queue
            while not self._pool.empty():
                try:
                    self._pool.get_nowait()
                except asyncio.QueueEmpty:
                    break
                    
    async def __aenter__(self):
        """Async context manager entry"""
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
        return False
