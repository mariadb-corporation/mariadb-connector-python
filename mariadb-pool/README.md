# MariaDB Connection Pool

Connection pooling for MariaDB Connector/Python with automatic connection management, health checking, and monitoring.

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

#### Using Connection URI

The simplest way to create a connection pool:

```python
import mariadb

# Create pool with URI
pool = mariadb.ConnectionPool(
    "mariadb://user:password@localhost:3306/mydb?pool_name=mypool&max_size=10"
)

# Use context manager to ensure connection is returned to pool
with pool.connection() as conn:
    with conn.cursor() as 
    cursor.execute("SELECT * FROM users")
    results = cursor.fetchall()
    cursor.close()

# Close pool when done
pool.close()
```

#### Using Connection Parameters

Create a pool with traditional connection parameters:

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
with pool.connection() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")
    results = cursor.fetchall()
    cursor.close()

pool.close()
```

### Asynchronous Connection Pool

#### Using Connection URI

Create an async pool with URI:

```python
import mariadb
import asyncio

async def main():
    # Create async pool with URI
    pool = mariadb.AsyncConnectionPool(
        "mariadb://user:password@localhost:3306/mydb?pool_name=async_pool&max_size=10"
    )
    
    # Must call open() to establish connections
    await pool.open()
    
    # Get connection from pool
    conn = await pool.get_connection()
    cursor = conn.cursor()
    await cursor.execute("SELECT * FROM users")
    results = await cursor.fetchall()
    
    # Close connection and cursor
    await cursor.close()
    await conn.close()
    
    # Close pool when done
    await pool.close()

asyncio.run(main())
```

#### Using Connection Parameters

Create an async pool with traditional parameters:

```python
import mariadb
import asyncio

async def main():
    # Create async pool with connection parameters
    pool = mariadb.AsyncConnectionPool(
        pool_name="async_pool",
        host="localhost",
        port=3306,
        user="root",
        password="password",
        database="mydb",
        max_size=10,
        pool_reset_connection=True
    )
    
    # Must call open() to establish connections
    await pool.open()
    
    conn = await pool.get_connection()
    cursor = conn.cursor()
    await cursor.execute("SELECT * FROM users")
    results = await cursor.fetchall()
    await cursor.close()
    await conn.close()
    
    await pool.close()

asyncio.run(main())
```

**Note:** 
- Async pools require calling `await pool.open()` after creation to establish connections (PostgreSQL asyncpg pattern)
- Pools with `pool_name` are registered in `mariadb._CONNECTION_POOLS` and can be accessed via `mariadb.connect(pool_name="...")` or `mariadb.asyncConnect(pool_name="...")`

## Usage Patterns

### Synchronous Patterns

#### Via mariadb.connect() with pool_name

Create a pool automatically when connecting:

```python
import mariadb

# First connection creates the pool
with mariadb.connect(
    "mariadb://user:password@localhost:3306/mydb",
    pool_name="mypool",
    max_size=10
) as conn1:
    # Use the connection
    cursor = conn1.cursor()
    cursor.execute("SELECT * FROM users")
    results = cursor.fetchall()
    cursor.close()

# Subsequent connections reuse the existing pool
with mariadb.connect(pool_name="mypool") as conn2:
    cursor = conn2.cursor()
    cursor.execute("SELECT 1")
    cursor.close()

# Clean up pool
mariadb._CONNECTION_POOLS["mypool"].close()
```

#### With Context Managers

Use context managers for automatic connection cleanup:

```python
import mariadb

pool = mariadb.ConnectionPool(
    "mariadb://user:password@localhost/mydb?pool_name=mypool&max_size=10"
)

# Context manager automatically closes connection
with pool.connection() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")
    results = cursor.fetchall()
    cursor.close()

pool.close()
```

### Asynchronous Patterns

#### Via mariadb.asyncConnect() with pool_name

Create an async pool automatically when connecting:

```python
import mariadb
import asyncio

async def main():
    # First connection creates the pool
    async with await mariadb.asyncConnect(
        "mariadb://user:password@localhost:3306/mydb",
        pool_name="async_pool",
        max_size=10
    ) as conn1:
        # Use the connection
        cursor = conn1.cursor()
        await cursor.execute("SELECT * FROM users")
        results = await cursor.fetchall()
        await cursor.close()
    
    # Subsequent connections reuse the existing pool
    async with await mariadb.asyncConnect(pool_name="async_pool") as conn2:
        cursor = conn2.cursor()
        await cursor.execute("SELECT 1")
        await cursor.close()
    
    # Clean up pool
    await mariadb._CONNECTION_POOLS["async_pool"].close()

asyncio.run(main())
```

#### With Async Context Managers

Use async context managers for automatic connection cleanup:

```python
import mariadb
import asyncio

async def main():
    pool = mariadb.AsyncConnectionPool(
        "mariadb://user:password@localhost/mydb?pool_name=async_pool&max_size=10"
    )
    await pool.open()
    
    # Async context manager automatically closes connection
    async with pool.connection() as conn:
        cursor = conn.cursor()
        await cursor.execute("SELECT * FROM users")
        results = await cursor.fetchall()
        await cursor.close()
    
    await pool.close()

asyncio.run(main())
```

### URI Format and Options

**URI Format:**
```
mariadb://[user[:password]@][host][:port][/database][?option1=value1&option2=value2]
```

**Supported URI Schemes:**
- `mariadb://` - MariaDB connection
- `mysql://` - MySQL connection (alias)

**Common Query Parameters:**
- `pool_name` - Name of the pool (required for ConnectionPool)
- `max_size` - Maximum number of connections in pool (default: 10)
- `autocommit` - Enable autocommit mode (default: false)
- `ssl` - Enable SSL/TLS connection
- `local_infile` - Enable LOAD DATA LOCAL INFILE

**Example with Multiple Options:**
```python
pool = mariadb.ConnectionPool(
    "mariadb://user:pass@localhost/db?pool_name=mypool&max_size=20&autocommit=true&ssl=true"
)
```

**Note:** Keyword arguments override URI parameters:
```python
# max_size in URI is 5, but kwarg overrides to 10
pool = mariadb.ConnectionPool(
    "mariadb://user:pass@localhost/db?pool_name=mypool&max_size=5",
    max_size=10  # This takes precedence
)
```

## Pool Configuration

### Basic Pool Options

Configure pool behavior with connection parameters:

```python
import mariadb

pool = mariadb.ConnectionPool(
    pool_name="mypool",
    host="localhost",
    user="root",
    password="password",
    database="mydb",
    # Pool configuration
    max_size=10,                     # Maximum number of connections
    pool_reset_connection=True,      # Reset connection state on return
)
```


### Manual Connection Management

For advanced use cases, manage connections manually:

```python
import mariadb

pool = mariadb.ConnectionPool(
    "mariadb://user:pass@localhost/mydb?pool_name=mypool"
)

# Get connection from pool
conn = pool.get_connection()

try:
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (name) VALUES (?)", ("John",))
    conn.commit()
    cursor.close()
finally:
    # Always close to return connection to pool
    conn.close()

pool.close()
```

## Pool Configuration Options

The pool accepts the following configuration parameters:

### Pool-Specific Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `min_size` | int | 10 | Minimum number of connections to maintain |
| `max_size` | int | 10 | Maximum number of connections allowed (max: 64) |
| `max_idle_time` | float | 600.0 | Maximum idle time (seconds) before closing connection |
| `max_lifetime` | float | 3600.0 | Maximum lifetime (seconds) of a connection |
| `validation_interval` | float | 30.0 | Interval (seconds) between connection validations |
| `acquire_timeout` | float | 30.0 | Timeout (seconds) when acquiring a connection |
| `enable_health_check` | bool | True | Enable periodic health checks on idle connections |
| `reset_connection` | bool | False | Reset connection state when returned to pool |

**Note:** If you set only `min_size` or only `max_size` (without setting the other), both will be set to the same value to create a fixed-size pool.

### mariadb.ConnectionPool Parameters

Additional parameters supported by `mariadb.ConnectionPool`:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `pool_name` | str | Required | Unique name for the pool |
| `pool_reset_connection` | bool | True | Alias for reset_connection (mapped by wrapper) |
| `pool_validation_interval` | float | - | Alias for validation_interval (mapped by wrapper) |

### Connection Parameters

All standard `mariadb.connect()` parameters are supported:
- `host`, `port`, `user`, `password`, `database`
- `autocommit`, `ssl`, `local_infile`
- And all other connection options

See [MariaDB Connector/Python documentation](https://mariadb-corporation.github.io/mariadb-connector-python/) for complete list.

### Examples

**Simple pool with fixed size:**
```python
pool = mariadb.ConnectionPool(
    pool_name="mypool",
    host="localhost",
    user="root",
    password="password",
    database="mydb",
    max_size=10  # Creates pool with max=10
)
```

**Dynamic pool with min/max:**
```python
pool = mariadb.ConnectionPool(
    pool_name="mypool",
    host="localhost",
    user="root",
    database="mydb",
    min_size=5,      # Keep at least 5 connections
    max_size=20,     # Allow up to 20 connections
    max_idle_time=300.0,    # Close idle connections after 5 minutes
    max_lifetime=1800.0,    # Close connections after 30 minutes
)
```

**URI with pool options:**
```python
pool = mariadb.ConnectionPool(
    "mariadb://user:pass@localhost/db?pool_name=mypool&max_size=15&max_idle_time=600"
)
```


## Sync vs Async Comparison

| Feature | Synchronous Pool | Asynchronous Pool |
|---------|------------------|-------------------|
| **Import** | `mariadb.ConnectionPool` | `mariadb.AsyncConnectionPool` |
| **Initialization** | Immediate | Requires `await pool.open()` |
| **Get Connection** | `pool.get_connection()` | `await pool.get_connection()` |
| **Add Connection** | `pool.add_connection()` | `await pool.add_connection()` |
| **Close Pool** | `pool.close()` | `await pool.close()` |
| **Context Manager** | `with pool.connection()` | `async with pool.connection()` |
| **Via connect()** | `mariadb.connect(pool_name=...)` | `await mariadb.asyncConnect(pool_name=...)` |
| **Connection Close** | `conn.close()` | `await conn.close()` |
| **Cursor Execute** | `cursor.execute(...)` | `await cursor.execute(...)` |
| **Fetch Results** | `cursor.fetchall()` | `await cursor.fetchall()` |

## Complete Examples

### Synchronous Web Application (Flask)

```python
from flask import Flask, jsonify
import mariadb

app = Flask(__name__)

# Initialize pool at startup
db_pool = mariadb.ConnectionPool(
    "mariadb://webapp:secret@localhost/myapp?pool_name=webapp&max_size=20"
)

@app.route('/users')
def get_users():
    with db_pool.connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, email FROM users")
        users = cursor.fetchall()
        cursor.close()
        return jsonify(users)

@app.teardown_appcontext
def close_pool(error):
    if db_pool:
        db_pool.close()

if __name__ == '__main__':
    app.run()
```

### Asynchronous Web Application (aiohttp)

```python
from aiohttp import web
import mariadb

async def init_app():
    app = web.Application()
    
    # Initialize async pool
    app['db_pool'] = mariadb.AsyncConnectionPool(
        "mariadb://webapp:secret@localhost/myapp?pool_name=async_webapp&max_size=20"
    )
    await app['db_pool'].open()
    
    app.router.add_get('/users', get_users)
    app.on_cleanup.append(cleanup)
    return app

async def get_users(request):
    pool = request.app['db_pool']
    async with pool.connection() as conn:
        cursor = conn.cursor()
        await cursor.execute("SELECT id, name, email FROM users")
        users = await cursor.fetchall()
        await cursor.close()
        return web.json_response(users)

async def cleanup(app):
    await app['db_pool'].close()

if __name__ == '__main__':
    app = init_app()
    web.run_app(app)
```

### Connection URL Examples

#### Basic Connection
```python
# Sync
pool = mariadb.ConnectionPool(
    "mariadb://user:password@localhost/mydb?pool_name=basic&max_size=10"
)

# Async
pool = mariadb.AsyncConnectionPool(
    "mariadb://user:password@localhost/mydb?pool_name=async_basic&max_size=10"
)
await pool.open()
```

#### With SSL/TLS
```python
# Sync
pool = mariadb.ConnectionPool(
    "mariadb://user:pass@localhost/db?pool_name=secure&max_size=10&ssl=true&ssl_verify_cert=true"
)

# Async
pool = mariadb.AsyncConnectionPool(
    "mariadb://user:pass@localhost/db?pool_name=async_secure&max_size=10&ssl=true"
)
await pool.open()
```

#### With Custom Port
```python
# Sync
pool = mariadb.ConnectionPool(
    "mariadb://user:pass@localhost:3307/db?pool_name=custom_port&max_size=5"
)

# Async
pool = mariadb.AsyncConnectionPool(
    "mariadb://user:pass@localhost:3307/db?pool_name=async_custom&max_size=5"
)
await pool.open()
```

#### With Multiple Options
```python
# Sync
pool = mariadb.ConnectionPool(
    "mariadb://user:pass@host/db?pool_name=advanced&max_size=20&autocommit=true&charset=utf8mb4&max_idle_time=300"
)

# Async
pool = mariadb.AsyncConnectionPool(
    "mariadb://user:pass@host/db?pool_name=async_advanced&max_size=20&autocommit=true&charset=utf8mb4"
)
await pool.open()
```

### Connection Parameters Examples

#### Basic Configuration
```python
# Sync
pool = mariadb.ConnectionPool(
    pool_name="basic_params",
    host="localhost",
    port=3306,
    user="myuser",
    password="mypassword",
    database="mydb",
    max_size=10
)

# Async
pool = mariadb.AsyncConnectionPool(
    pool_name="async_basic_params",
    host="localhost",
    port=3306,
    user="myuser",
    password="mypassword",
    database="mydb",
    max_size=10
)
await pool.open()
```

#### Advanced Configuration
```python
# Sync
pool = mariadb.ConnectionPool(
    pool_name="advanced_params",
    host="db.example.com",
    port=3306,
    user="webapp",
    password="secret",
    database="production",
    # Pool settings
    max_size=20,
    pool_reset_connection=True,
    pool_validation_interval=30,
    # Connection settings
    autocommit=False,
    ssl=True,
    ssl_verify_cert=True,
    connect_timeout=10,
    charset="utf8mb4"
)

# Async
pool = mariadb.AsyncConnectionPool(
    pool_name="async_advanced_params",
    host="db.example.com",
    port=3306,
    user="webapp",
    password="secret",
    database="production",
    # Pool settings
    max_size=20,
    pool_reset_connection=True,
    pool_validation_interval=30,
    # Connection settings
    autocommit=False,
    ssl=True,
    connect_timeout=10,
    charset="utf8mb4"
)
await pool.open()
```

## Best Practices

### 1. Always Use Context Managers

Use context managers to ensure connections are properly returned to the pool:

**Sync:**
```python
with pool.connection() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")
    results = cursor.fetchall()
    cursor.close()
# Connection automatically returned to pool
```

**Async:**
```python
async with pool.connection() as conn:
    cursor = conn.cursor()
    await cursor.execute("SELECT * FROM users")
    results = await cursor.fetchall()
    await cursor.close()
# Connection automatically returned to pool
```

### 2. Configure Pool Size Appropriately

Set pool size based on your application's concurrency:

**Sync:**
```python
# For web applications with 10-20 concurrent requests
pool = mariadb.ConnectionPool(
    "mariadb://user:pass@host/db?pool_name=webapp&max_size=15"
)
```

**Async:**
```python
# For async applications with 50-100 concurrent requests
pool = mariadb.AsyncConnectionPool(
    "mariadb://user:pass@host/db?pool_name=async_webapp&max_size=50"
)
await pool.open()
```

### 3. Initialize Async Pools Properly

Always call `open()` on async pools:

```python
# ❌ Wrong - pool not opened
pool = mariadb.AsyncConnectionPool(...)
async with pool.connection() as conn:  # Will hang!
    pass

# ✅ Correct - pool opened first
pool = mariadb.AsyncConnectionPool(...)
await pool.open()
async with pool.connection() as conn:
    cursor = conn.cursor()
    await cursor.execute("SELECT 1")
    await cursor.close()
```

## License

LGPL 2.1+