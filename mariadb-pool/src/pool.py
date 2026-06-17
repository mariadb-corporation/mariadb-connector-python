# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Advanced Connection Pool Implementation
"""

import threading
import asyncio
import time
import queue
import collections
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Dict, Union, TYPE_CHECKING
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

# Type hints for connection types
if TYPE_CHECKING:
    try:
        from mariadb.sync_connection import SyncConnection
        from mariadb.async_connection import AsyncConnection
    except ImportError:
        SyncConnection = Any
        AsyncConnection = Any

    try:
        from mariadb_c import Connection as CConnection
    except ImportError:
        CConnection = Any


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
    ping_threshold: float = 0.25  # Ping if connection idle > 250ms (0 = disabled)


class BasePooledConnection:
    """
    Base wrapper for a pooled connection

    Tracks connection metadata and lifecycle
    """

    connection: Any
    pool: Any
    created_at: float
    last_used: float
    use_count: int
    in_use: bool

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

    if TYPE_CHECKING:
        connection: Union['SyncConnection', 'CConnection']

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

    def __getattr__(self, name):
        """Proxy attribute access to underlying connection"""
        return getattr(self.connection, name)


class AsyncPooledConnection(BasePooledConnection):
    """Async pooled connection wrapper"""

    if TYPE_CHECKING:
        connection: 'AsyncConnection'

    async def is_healthy(self) -> bool:
        """
        Check if connection is healthy
        """
        try:
            await self.connection.ping()
            return True
        except Exception:
            return False

    async def return_to_pool(self):
        """Return this connection to the pool"""
        await self.pool.release(self)

    async def closeSilently(self):
        try:
            self.connection._set_pooled_connection(None)
            await self.connection.close()
        except Exception:
            pass

    def __getattr__(self, name):
        """Proxy attribute access to underlying connection"""
        return getattr(self.connection, name)



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
        self.connection_params = connection_params
        self.config = config or PoolConfig()

        # Use Condition + deque like async pool for consistency
        self._cond: threading.Condition = threading.Condition(threading.RLock())
        self._free: collections.deque[PooledConnection] = collections.deque(maxlen=self.config.max_size or None)
        self._used: set[PooledConnection] = set()
        self._acquiring: int = 0
        self._all_connections: list[PooledConnection] = []
        self._closed: bool = False
        self._shutdown_event: threading.Event = threading.Event()  # For immediate thread shutdown
        self._maintenance_thread: Optional[threading.Thread] = None

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

    def _create_connection_unlocked(self) -> PooledConnection:
        """Create a new pooled connection (must be called with _cond held)"""
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

    def _create_connection(self) -> PooledConnection:
        """Create a new pooled connection (legacy method)"""
        with self._cond:
            return self._create_connection_unlocked()

    def _ensure_min_connections(self):
        """Ensure minimum number of connections exist"""
        with self._cond:
            current_count = len(self._all_connections)
            for _ in range(self.config.min_size - current_count):
                try:
                    pooled_conn = self._create_connection_unlocked()
                    pooled_conn.mark_idle()
                    if self._closed:
                        pooled_conn.closeSilently()
                    else:
                        self._free.append(pooled_conn)
                        self._cond.notify()
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

    def _fill_free_pool(self, override_min: bool = False):
        """Fill free pool with connections (MUST be called with _cond held)

        Args:
            override_min: If True, always try to create connections up to min_size
        """
        # Fill up to min_size if override_min is True
        if override_min:
            while len(self._all_connections) < self.config.min_size:
                if self._acquiring > 0:
                    return
                self._acquiring += 1
                try:
                    conn = self.connection_factory(**self.connection_params)
                    pooled_conn = PooledConnection(conn, self)
                    conn._set_pooled_connection(pooled_conn)
                    self._all_connections.append(pooled_conn)
                    pooled_conn.mark_idle()
                    self._free.append(pooled_conn)
                    self._cond.notify()
                except Exception:
                    break
                finally:
                    self._acquiring -= 1

        # If no free connections and we can create more, create one
        if not self._free and (not self.config.max_size or len(self._all_connections) < self.config.max_size):
            if self._acquiring > 0:
                return
            self._acquiring += 1
            try:
                conn = self.connection_factory(**self.connection_params)
                pooled_conn = PooledConnection(conn, self)
                conn._set_pooled_connection(pooled_conn)
                self._all_connections.append(pooled_conn)
                pooled_conn.mark_idle()
                self._free.append(pooled_conn)
                self._cond.notify()
            except Exception:
                pass
            finally:
                self._acquiring -= 1

    def _cleanup_expired_connections(self):
        """Remove expired connections from pool"""
        with self._cond:
            # Clean up expired connections from free pool
            n = 0
            free_size = len(self._free)
            while n < free_size:
                pool_conn = self._free[-1]
                if pool_conn.is_expired(self.config.max_lifetime, self.config.max_idle_time):
                    self._free.pop()
                    pool_conn.closeSilently()
                    if pool_conn in self._all_connections:
                        self._all_connections.remove(pool_conn)
                else:
                    self._free.rotate()
                n += 1

    def acquire(self, timeout: Optional[float] = None) -> Union['SyncConnection', 'CConnection']:
        return self._acquire(timeout).connection

    def _acquire(self, timeout: Optional[float] = None) -> PooledConnection:
        """
        Acquire a connection from the pool (optimized with threading.Condition)

        Args:
            timeout: Timeout in seconds (uses config default if None)

        Returns:
            Database connection object
        """
        if self._closed:
            raise PoolError("Pool is closed")

        if timeout is None:
            timeout = self.config.acquire_timeout

        deadline = time.time() + timeout if timeout else None

        with self._cond:
            while True:
                # Only fill pool on first call or if we have capacity and no one else is acquiring
                # This avoids holding the lock during I/O on every acquire
                if len(self._all_connections) < self.config.min_size and self._acquiring == 0:
                    self._fill_free_pool(override_min=True)

                if self._free:
                    # Get connection from free pool
                    pooled_conn = self._free.popleft()

                    # Selective health check: only ping if connection has been idle too long
                    if self.config.ping_threshold == 0 or time.time() - pooled_conn.last_used > self.config.ping_threshold:
                        # Connection idle too long, verify it's still alive
                        if not pooled_conn.is_healthy():
                            # Connection dead, close and try again
                            pooled_conn.closeSilently()
                            if pooled_conn in self._all_connections:
                                self._all_connections.remove(pooled_conn)
                            continue

                    # Mark as in use and return
                    self._used.add(pooled_conn)
                    pooled_conn.mark_in_use()
                    return pooled_conn

                # Try to create a new connection if we're under max_size
                if self.config.max_size and len(self._all_connections) < self.config.max_size:
                    self._fill_free_pool()
                    continue

                # No free connections and at max capacity, wait for one to be released
                if deadline:
                    remaining = deadline - time.time()
                    if remaining <= 0:
                        raise PoolError(f"Timeout acquiring connection from pool (timeout={timeout}s)")
                    if not self._cond.wait(timeout=remaining):
                        raise PoolError(f"Timeout acquiring connection from pool (timeout={timeout}s)")
                else:
                    self._cond.wait()

    def release(self, pool_conn: PooledConnection):
        """
        Release a connection back to the pool (optimized with threading.Condition)

        Args:
            connection: Connection to release
        """
        if self._closed:
            return

        # Mark idle and remove from used set under lock to ensure atomicity
        with self._cond:
            if pool_conn in self._used:
                self._used.remove(pool_conn)
            pool_conn.mark_idle()

        # Reset or rollback connection before returning to pool
        try:
            conn = pool_conn.connection

            _client = getattr(conn, "_client", None)
            _active = getattr(_client, "_active_streaming_result", None) if _client is not None else None
            if _active is not None:
                try:
                    _active.fetch_remaining()
                finally:
                    _client._active_streaming_result = None

            # Reset connection if reset_connection is enabled
            if self.config.reset_connection:
                conn.reset()
            # Or rollback if in transaction
            elif (conn.server_status & IN_TRANS) > 0:
                conn.rollback()
        except Exception:
            # If reset/rollback fails, close the connection
            pool_conn.closeSilently()
            with self._cond:
                if pool_conn in self._all_connections:
                    self._all_connections.remove(pool_conn)
            return

        # Check if connection should be kept and return to pool under lock
        with self._cond:
            if pool_conn.is_expired(self.config.max_lifetime, self.config.max_idle_time):
                pool_conn.closeSilently()
                if pool_conn in self._all_connections:
                    self._all_connections.remove(pool_conn)
            else:
                # Return to free pool and notify waiters
                if pool_conn not in self._free:
                    self._free.append(pool_conn)
                    self._cond.notify()

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
        pool_conn = self._acquire(timeout=timeout)
        try:
            yield pool_conn.connection
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

        with self._cond:
            for pooled_conn in self._all_connections:
                pooled_conn.closeSilently()
            self._all_connections.clear()
            self._free.clear()
            self._used.clear()

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
        connection_factory: Optional[Callable] = None,
        config: Optional[PoolConfig] = None,
        **connection_params: Any
    ) -> None:
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

        # Use Condition + deque for better performance
        self._cond: asyncio.Condition = asyncio.Condition()
        self._free: collections.deque[AsyncPooledConnection] = collections.deque(maxlen=self.config.max_size or None)
        self._used: set[AsyncPooledConnection] = set()
        self._acquiring: int = 0
        self._all_connections: list[AsyncPooledConnection] = []
        self._closed: bool = False
        self._maintenance_task: Optional[asyncio.Task] = None
        self._opened: bool = False

    async def open(self) -> None:
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
        """Create a new pooled connection (legacy method, not used with Condition pattern)"""
        async with self._cond:
            return await self._create_connection_unlocked()

    async def _ensure_min_connections(self) -> None:
        """Ensure minimum number of connections exist"""
        async with self._cond:
            current_count = len(self._all_connections)
            for _ in range(self.config.min_size - current_count):
                try:
                    pooled_conn = await self._create_connection_unlocked()
                    pooled_conn.mark_idle()
                    self._free.append(pooled_conn)
                    self._cond.notify()
                except Exception:
                    break

    async def _maintenance_loop(self) -> None:
        """Background task for pool maintenance"""
        while not self._closed:
            await asyncio.sleep(self.config.validation_interval)
            await self._cleanup_expired_connections()
            await self._ensure_min_connections()

    async def _fill_free_pool(self, override_min: bool = False) -> None:
        """Fill free pool with connections (MUST be called with _cond held)

        This checks if we need connections and fills up to min_size.
        For aiomysql compatibility, this does I/O while holding the lock.

        Args:
            override_min: If True, always try to create connections up to min_size
        """
        # Fill up to min_size if override_min is True
        if override_min:
            while len(self._all_connections) < self.config.min_size:
                if self._acquiring > 0:
                    return
                self._acquiring += 1
                try:
                    conn = await self.connection_factory(**self.connection_params)
                    pooled_conn = AsyncPooledConnection(conn, self)
                    conn._set_pooled_connection(pooled_conn)
                    self._all_connections.append(pooled_conn)
                    pooled_conn.mark_idle()
                    self._free.append(pooled_conn)
                    self._cond.notify()
                except Exception:
                    break
                finally:
                    self._acquiring -= 1

        # If no free connections and we can create more, create one
        if not self._free and (not self.config.max_size or len(self._all_connections) < self.config.max_size):
            if self._acquiring > 0:
                return
            self._acquiring += 1
            try:
                conn = await self.connection_factory(**self.connection_params)
                pooled_conn = AsyncPooledConnection(conn, self)
                conn._set_pooled_connection(pooled_conn)
                self._all_connections.append(pooled_conn)
                pooled_conn.mark_idle()
                self._free.append(pooled_conn)
                self._cond.notify()
            except Exception:
                pass
            finally:
                self._acquiring -= 1

    async def _cleanup_expired_connections(self) -> None:
        """Remove expired connections from pool"""
        async with self._cond:
            # Clean up expired connections from free pool
            n = 0
            free_size = len(self._free)
            while n < free_size:
                pool_conn = self._free[-1]
                if pool_conn.is_expired(self.config.max_lifetime, self.config.max_idle_time):
                    self._free.pop()
                    await pool_conn.closeSilently()
                    if pool_conn in self._all_connections:
                        self._all_connections.remove(pool_conn)
                else:
                    self._free.rotate()
                n += 1

    async def acquire(self, timeout: Optional[float] = None) -> 'AsyncConnection':
        pooled_conn = await self._acquire(timeout)
        return pooled_conn.connection

    async def _acquire(self, timeout: Optional[float] = None) -> AsyncPooledConnection:
        """
        Acquire a connection from the pool (optimized with asyncio.Condition)

        Args:
            timeout: Timeout in seconds (uses config default if None)

        Returns:
            Database connection object
        """
        if self._closed:
            raise PoolError("Pool is closed")

        if timeout is None:
            timeout = self.config.acquire_timeout

        deadline = time.time() + timeout if timeout else None

        async with self._cond:
            while True:
                # Only fill pool on first call or if we have capacity and no one else is acquiring
                # This avoids holding the lock during I/O on every acquire
                if len(self._all_connections) < self.config.min_size and self._acquiring == 0:
                    await self._fill_free_pool(override_min=True)

                if self._free:
                    # Get connection from free pool
                    pooled_conn = self._free.popleft()

                    # Selective health check: only ping if connection has been idle too long
                    if self.config.ping_threshold == 0 or time.time() - pooled_conn.last_used > self.config.ping_threshold:
                        # Connection idle too long, verify it's still alive
                        if not await pooled_conn.is_healthy():
                            # Connection dead, close and try again
                            await pooled_conn.closeSilently()
                            if pooled_conn in self._all_connections:
                                self._all_connections.remove(pooled_conn)
                            continue

                    # Mark as in use and return
                    self._used.add(pooled_conn)
                    pooled_conn.mark_in_use()
                    return pooled_conn

                # Try to create a new connection if we're under max_size
                if self.config.max_size and len(self._all_connections) < self.config.max_size:
                    await self._fill_free_pool()
                    continue

                # No free connections and at max capacity, wait for one to be released
                if deadline:
                    remaining = deadline - time.time()
                    if remaining <= 0:
                        raise PoolError(f"Timeout acquiring connection from pool (timeout={timeout}s)")
                    try:
                        await asyncio.wait_for(self._cond.wait(), timeout=remaining)
                    except asyncio.TimeoutError:
                        raise PoolError(f"Timeout acquiring connection from pool (timeout={timeout}s)")
                else:
                    await self._cond.wait()

    async def release(self, pool_conn: AsyncPooledConnection) -> None:
        """
        Release a connection back to the pool (optimized with asyncio.Condition)

        Args:
            connection: Connection to release
        """
        if self._closed:
            return

        # Mark idle and remove from used set under lock to ensure atomicity
        async with self._cond:
            if pool_conn in self._used:
                self._used.remove(pool_conn)
            pool_conn.mark_idle()

        # Reset or rollback connection before returning to pool
        try:
            conn = pool_conn.connection

            # Proactively drain any unconsumed streaming result (pure-Python
            # client) before reset/rollback. A cursor returned without being
            # fully read leaves result data on the wire; execute() would only
            # drain it lazily on the next command, and with reset_connection off
            # nothing would drain it at all — desyncing the next pool user.
            # Draining first also makes reset() far less likely to fail (and so
            # the connection less likely to be dropped from the pool). The C
            # extension has no such attribute and relies on reset() instead.
            _client = getattr(conn, "_client", None)
            _active = getattr(_client, "_active_streaming_result", None) if _client is not None else None
            if _active is not None:
                try:
                    await _active.fetch_remaining()
                finally:
                    _client._active_streaming_result = None

            # Reset connection if reset_connection is enabled
            if self.config.reset_connection:
                await conn.reset()
            # Or rollback if in transaction
            elif (conn.server_status & IN_TRANS) > 0:
                await conn.rollback()
        except Exception:
            # If reset/rollback fails, close the connection
            await pool_conn.closeSilently()
            async with self._cond:
                if pool_conn in self._all_connections:
                    self._all_connections.remove(pool_conn)
            return

        # Check if connection should be kept and return to pool under lock
        async with self._cond:
            if pool_conn.is_expired(self.config.max_lifetime, self.config.max_idle_time):
                await pool_conn.closeSilently()
                if pool_conn in self._all_connections:
                    self._all_connections.remove(pool_conn)
            else:
                # Return to free pool and notify waiters
                if pool_conn not in self._free:
                    self._free.append(pool_conn)
                    self._cond.notify()

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
        pool_conn = await self._acquire(timeout=timeout)
        try:
            yield pool_conn.connection
        finally:
            await self.release(pool_conn)

    async def close(self) -> None:
        """Close the pool and all connections"""
        self._closed = True

        # Cancel maintenance task
        if self._maintenance_task:
            self._maintenance_task.cancel()
            try:
                await self._maintenance_task
            except asyncio.CancelledError:
                pass

        async with self._cond:
            for pooled_conn in self._all_connections:
                await pooled_conn.closeSilently()
            self._all_connections.clear()
            self._free.clear()
            self._used.clear()

    async def __aenter__(self) -> 'AsyncConnectionPool':
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        """Async context manager exit"""
        await self.close()
        return False
