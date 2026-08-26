# mariadb-pool

`mariadb-pool` is the **connection pooling add-on** for the [mariadb](https://pypi.org/project/mariadb/) connector.
It provides synchronous and asynchronous connection pools with automatic connection management, health checking, and monitoring.

## Installation

Install MariaDB Connector/Python with pool support:

```bash
pip install mariadb[pool]
```

Or install the pool package separately:

```bash
pip install mariadb-pool
```

## Features

- **Easy Connection Management**: Automatic connection pooling via `mariadb.ConnectionPool`
- **URI Support**: Create pools with connection URIs for clean configuration
- **Dynamic Pool Sizing**: Automatically adjusts between min and max connections
- **Connection Health Checking**: Periodic validation of idle connections
- **Thread-Safe**: Fully thread-safe for multi-threaded applications
- **Pool Statistics**: Monitor pool usage and performance
- **Context Manager Support**: Clean connection handling with `with` statements

## Quick Start

### Synchronous Connection Pool

#### Using create_pool() (Recommended)

The cleanest way to create a connection pool with separated pool and connection parameters:

```python
import mariadb

# Create pool with clean parameter separation
pool = mariadb.create_pool(
    host="localhost",
    port=3306,
    user="root",
    password="password",
    database="mydb",
    min_size=5,
    max_size=10,
    ping_threshold=500,  # Only ping connections idle > 500ms on borrow
    max_idle_time=600.0,
    reset_connection=True
)

# Get connection from pool
with pool.acquire() as conn:
    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM users")
        results = cursor.fetchall()

# Close pool when done
pool.close()
```

#### Using ConnectionPool Constructor

Alternatively, use the traditional constructor:

```python
import mariadb

# Create pool with connection parameters
pool = mariadb.ConnectionPool(
    pool_name="mypool",
    host="localhost",
    port=3306,
    user="root",
    password="password",
    database="mydb",
    max_size=10,
    pool_reset_connection=True
)

# Use context manager to ensure connection is returned to pool
with pool.get_connection() as conn:
    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM users")
        results = cursor.fetchall()

pool.close()
```

### Asynchronous Connection Pool

#### Using create_async_pool() (Recommended)

The cleanest way to create an async pool - automatically pre-filled and ready to use:

```python
import mariadb
import asyncio

async def main():
    # Create async pool with clean parameter separation
    # Pool is automatically opened and pre-filled with connections
    pool = await mariadb.create_async_pool(
        host="localhost",
        port=3306,
        user="root",
        password="password",
        database="mydb",
        min_size=5,
        max_size=20,
        ping_threshold=500,  # Only ping connections idle > 500ms
        max_idle_time=600.0,
        reset_connection=True
    )
    
    # Acquire connection from pool
    async with await pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT * FROM users")
            results = await cursor.fetchall()
    
    # Close pool if unneeded anymore
    await pool.close()

asyncio.run(main())
```


## Pool Configuration Options

The pool accepts the following configuration parameters:

### Pool-Specific Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `min_size` | int | 10 | Minimum number of connections to maintain |
| `max_size` | int | 10 | Maximum number of connections allowed (0 = unlimited) |
| `max_idle_time` | float | 600.0 | Maximum idle time (seconds) before closing connection |
| `max_lifetime` | float | 3600.0 | Maximum lifetime (seconds) of a connection |
| `ping_threshold` | float | 500 | On borrow, ping only if the connection was idle longer than this (milliseconds, 0 = always ping). 1.1's `pool_validation_interval` |
| `acquire_timeout` | float | 30.0 | Timeout (seconds) when acquiring a connection |
| `enable_health_check` | bool | True | Enable periodic health checks on idle connections |
| `reset_connection` | bool | False | Reset connection state when returned to pool |

**Performance Tip:** The `ping_threshold` option significantly improves performance by avoiding unnecessary database pings. Connections that have been idle for less than the threshold (default: 500 ms, as in 1.1) are assumed healthy and returned immediately. Only connections idle longer than the threshold are verified with a ping. Set to `0` to ping every time.

**Note:** If you set only `min_size` or only `max_size` (without setting the other), both will be set to the same value to create a fixed-size pool. Pool sizes are not capped.

**Note:** the period of the background sweep that reaps idle and expired connections is not an option — it is fixed at 30 seconds. It is only the resolution at which `max_idle_time` and `max_lifetime` are noticed for connections nobody is using; a connection returned to the pool is checked against both immediately.

**Note:** every option below is accepted identically by `create_pool()`, `create_async_pool()`, `mariadb.ConnectionPool` and a URI query string: naming, typing and size reconciliation all happen in one place (`PoolConfig.from_options()`).

### mariadb.ConnectionPool Parameters

Additional parameters supported by `mariadb.ConnectionPool`:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `pool_name` | str | Required | Unique name for the pool |
| `pool_size` | int | - | Fixed-size pool: sets `min_size` and `max_size` together |
| `pool_validation_interval` | float | 500 | 1.1 name for `ping_threshold` (milliseconds) |
| `pool_reset_connection` | bool | False | Alias for `reset_connection` (1.1 defaulted this to True) |

