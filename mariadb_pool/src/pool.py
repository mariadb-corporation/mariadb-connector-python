"""
Advanced Connection Pool Implementation
"""

import threading
import time
import queue
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Dict
from contextlib import contextmanager


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
    min_size: int = 5
    max_size: int = 20
    max_idle_time: float = 600.0  # 10 minutes
    max_lifetime: float = 3600.0  # 1 hour
    validation_interval: float = 30.0  # 30 seconds
    acquire_timeout: float = 30.0  # 30 seconds
    enable_health_check: bool = True


@dataclass
class PoolStats:
    """
    Statistics for connection pool
    
    Attributes:
        total_connections: Total number of connections created
        active_connections: Number of connections currently in use
        idle_connections: Number of idle connections in the pool
        total_requests: Total number of connection requests
        failed_requests: Number of failed connection requests
        average_wait_time: Average wait time for acquiring a connection
    """
    total_connections: int = 0
    active_connections: int = 0
    idle_connections: int = 0
    total_requests: int = 0
    failed_requests: int = 0
    average_wait_time: float = 0.0
    _wait_times: list = field(default_factory=list, repr=False)
    
    def record_wait(self, wait_time: float):
        """Record a wait time for statistics"""
        self._wait_times.append(wait_time)
        if len(self._wait_times) > 1000:
            self._wait_times = self._wait_times[-1000:]
        self.average_wait_time = sum(self._wait_times) / len(self._wait_times)


class PooledConnection:
    """
    Wrapper for a pooled connection
    
    Tracks connection metadata and lifecycle
    """
    
    def __init__(self, connection: Any, pool: 'ConnectionPool'):
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
        
    def is_healthy(self) -> bool:
        """
        Check if connection is healthy
        
        This is a stub - actual implementation should ping the database
        """
        try:
            # Stub: actual implementation would call connection.ping()
            return True
        except Exception:
            return False


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
        self.stats = PoolStats()
        
        self._pool: queue.Queue = queue.Queue(maxsize=self.config.max_size)
        self._all_connections: list[PooledConnection] = []
        self._lock = threading.RLock()
        self._closed = False
        
        # Start background maintenance thread
        if self.config.enable_health_check:
            self._maintenance_thread = threading.Thread(
                target=self._maintenance_loop,
                daemon=True
            )
            self._maintenance_thread.start()
        
        # Create minimum connections
        self._ensure_min_connections()
        
    def _create_connection(self) -> PooledConnection:
        """Create a new pooled connection"""
        with self._lock:
            if len(self._all_connections) >= self.config.max_size:
                raise PoolError(f"Pool has reached maximum size of {self.config.max_size}")
                
            try:
                conn = self.connection_factory(**self.connection_params)
                pooled_conn = PooledConnection(conn, self)
                self._all_connections.append(pooled_conn)
                self.stats.total_connections += 1
                return pooled_conn
            except Exception as e:
                self.stats.failed_requests += 1
                raise PoolError(f"Failed to create connection: {e}") from e
                
    def _ensure_min_connections(self):
        """Ensure minimum number of connections exist"""
        with self._lock:
            current_count = len(self._all_connections)
            for _ in range(self.config.min_size - current_count):
                try:
                    pooled_conn = self._create_connection()
                    pooled_conn.mark_idle()
                    self._pool.put_nowait(pooled_conn)
                except Exception:
                    break
                    
    def _maintenance_loop(self):
        """Background thread for pool maintenance"""
        while not self._closed:
            time.sleep(self.config.validation_interval)
            self._cleanup_expired_connections()
            self._ensure_min_connections()
            
    def _cleanup_expired_connections(self):
        """Remove expired connections from pool"""
        with self._lock:
            expired = [
                conn for conn in self._all_connections
                if not conn.in_use and conn.is_expired(
                    self.config.max_lifetime,
                    self.config.max_idle_time
                )
            ]
            
            for conn in expired:
                try:
                    conn.connection.close()
                    self._all_connections.remove(conn)
                except Exception:
                    pass
                    
    def acquire(self, timeout: Optional[float] = None) -> Any:
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
        start_time = time.time()
        
        self.stats.total_requests += 1
        
        try:
            # Try to get an existing connection
            pooled_conn = self._pool.get(timeout=timeout)
            
            # Validate connection health
            if not pooled_conn.is_healthy():
                # Connection is unhealthy, create a new one
                try:
                    pooled_conn.connection.close()
                except Exception:
                    pass
                self._all_connections.remove(pooled_conn)
                pooled_conn = self._create_connection()
                
        except queue.Empty:
            # No idle connections, try to create a new one
            try:
                pooled_conn = self._create_connection()
            except PoolError:
                self.stats.failed_requests += 1
                raise PoolError("No connections available and pool is at maximum size")
                
        pooled_conn.mark_in_use()
        
        with self._lock:
            self.stats.active_connections += 1
            self.stats.idle_connections = self._pool.qsize()
            
        wait_time = time.time() - start_time
        self.stats.record_wait(wait_time)
        
        return pooled_conn.connection
        
    def release(self, connection: Any):
        """
        Release a connection back to the pool
        
        Args:
            connection: Connection to release
        """
        if self._closed:
            return
            
        with self._lock:
            # Find the pooled connection wrapper
            pooled_conn = None
            for pc in self._all_connections:
                if pc.connection is connection:
                    pooled_conn = pc
                    break
                    
            if pooled_conn is None:
                return
                
            pooled_conn.mark_idle()
            self.stats.active_connections -= 1
            
            # Check if connection should be kept
            if pooled_conn.is_expired(self.config.max_lifetime, self.config.max_idle_time):
                try:
                    connection.close()
                    self._all_connections.remove(pooled_conn)
                except Exception:
                    pass
            else:
                try:
                    self._pool.put_nowait(pooled_conn)
                    self.stats.idle_connections = self._pool.qsize()
                except queue.Full:
                    # Pool is full, close the connection
                    try:
                        connection.close()
                        self._all_connections.remove(pooled_conn)
                    except Exception:
                        pass
                        
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
        conn = self.acquire(timeout=timeout)
        try:
            yield conn
        finally:
            self.release(conn)
            
    def close(self):
        """Close the pool and all connections"""
        self._closed = True
        
        with self._lock:
            for pooled_conn in self._all_connections:
                try:
                    pooled_conn.connection.close()
                except Exception:
                    pass
            self._all_connections.clear()
            
            # Clear the queue
            while not self._pool.empty():
                try:
                    self._pool.get_nowait()
                except queue.Empty:
                    break
                    
    def get_stats(self) -> PoolStats:
        """Get current pool statistics"""
        with self._lock:
            self.stats.idle_connections = self._pool.qsize()
            return self.stats
            
    def __enter__(self):
        """Context manager entry"""
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
        return False
