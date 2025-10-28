# MariaDB Advanced Connection Pool

Advanced connection pooling for MariaDB Connector/Python with dynamic sizing, health checking, and monitoring capabilities.

## Features

- **Dynamic Pool Sizing**: Automatically adjusts pool size between min and max limits
- **Connection Health Checking**: Periodic validation of idle connections
- **Connection Lifecycle Management**: Automatic expiration based on age and idle time
- **Pool Statistics**: Detailed metrics on pool usage and performance
- **Thread-Safe**: Fully thread-safe implementation
- **Context Manager Support**: Easy-to-use context managers for connection handling

## Installation

```bash
pip install mariadb-pool
```

## Usage

### Basic Usage

```python
from mariadb_pool import ConnectionPool, PoolConfig
import mariadb

# Define connection factory
def create_connection():
    return mariadb.connect(
        host="localhost",
        user="root",
        password="password",
        database="test"
    )

# Create pool with custom configuration
config = PoolConfig(
    min_size=5,
    max_size=20,
    max_idle_time=600,  # 10 minutes
    max_lifetime=3600,  # 1 hour
)

pool = ConnectionPool(create_connection, config=config)

# Use connection with context manager
with pool.connection() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")
    results = cursor.fetchall()

# Get pool statistics
stats = pool.get_stats()
print(f"Active connections: {stats.active_connections}")
print(f"Idle connections: {stats.idle_connections}")
print(f"Average wait time: {stats.average_wait_time:.3f}s")

# Close pool when done
pool.close()
```

### Advanced Configuration

```python
from mariadb_pool import ConnectionPool, PoolConfig

config = PoolConfig(
    min_size=10,                    # Minimum connections to maintain
    max_size=50,                    # Maximum connections allowed
    max_idle_time=300.0,            # Close idle connections after 5 minutes
    max_lifetime=1800.0,            # Close connections after 30 minutes
    validation_interval=60.0,       # Check health every minute
    acquire_timeout=10.0,           # Wait up to 10 seconds for a connection
    enable_health_check=True        # Enable background health checks
)

pool = ConnectionPool(create_connection, config=config)
```

### Manual Connection Management

```python
# Acquire connection manually
conn = pool.acquire(timeout=5.0)

try:
    # Use connection
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (name) VALUES (?)", ("John",))
    conn.commit()
finally:
    # Always release connection back to pool
    pool.release(conn)
```

### Pool as Context Manager

```python
with ConnectionPool(create_connection, config=config) as pool:
    with pool.connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        print(cursor.fetchone())
# Pool is automatically closed when exiting context
```

## Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `min_size` | int | 5 | Minimum number of connections in pool |
| `max_size` | int | 20 | Maximum number of connections in pool |
| `max_idle_time` | float | 600.0 | Maximum idle time (seconds) before closing |
| `max_lifetime` | float | 3600.0 | Maximum connection lifetime (seconds) |
| `validation_interval` | float | 30.0 | Health check interval (seconds) |
| `acquire_timeout` | float | 30.0 | Timeout when acquiring connection (seconds) |
| `enable_health_check` | bool | True | Enable background health checks |

## Pool Statistics

The pool provides detailed statistics via `get_stats()`:

- `total_connections`: Total connections created since pool start
- `active_connections`: Currently in-use connections
- `idle_connections`: Available connections in pool
- `total_requests`: Total connection requests
- `failed_requests`: Failed connection attempts
- `average_wait_time`: Average time to acquire a connection

## Thread Safety

The connection pool is fully thread-safe and can be used in multi-threaded applications:

```python
import threading

def worker():
    with pool.connection() as conn:
        # Do work with connection
        pass

threads = [threading.Thread(target=worker) for _ in range(10)]
for t in threads:
    t.start()
for t in threads:
    t.join()
```

## Best Practices

1. **Use Context Managers**: Always use `with pool.connection()` to ensure connections are properly released
2. **Configure Pool Size**: Set `min_size` and `max_size` based on your application's concurrency needs
3. **Monitor Statistics**: Regularly check pool statistics to optimize configuration
4. **Handle Exceptions**: Always release connections even when exceptions occur
5. **Close Pool**: Call `pool.close()` when shutting down your application

## License

LGPL 2.1

## Author

Georg Richter
