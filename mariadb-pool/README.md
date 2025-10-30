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

### Using Connection URI (Recommended)

The simplest way to create a connection pool:

```python
import mariadb

# Create pool with URI - pool can be used directly without a name
pool = mariadb.ConnectionPool(
    "mariadb://user:password@localhost:3306/mydb"
)

# Get connection from pool
conn = pool.get_connection()
cursor = conn.cursor()
cursor.execute("SELECT * FROM users")
results = cursor.fetchall()

# Always close connections to return them to the pool
cursor.close()
conn.close()

# Close pool when done
pool.close()
```

**Note:** Pools without a `pool_name` can be used directly but won't be registered in `mariadb._CONNECTION_POOLS`. To create a named pool that can be accessed via `mariadb.connect(pool_name="...")`, include `pool_name` in the URI query parameters or as a keyword argument.

### Using Connection Parameters

Create a pool with traditional connection parameters:

```python
import mariadb

# Create pool with connection parameters
pool = mariadb.ConnectionPool(
    host="localhost",
    user="root",
    password="password",
    database="mydb",
    pool_size=10  # Optional: set pool size
)

conn = pool.get_connection()
# Use connection...
conn.close()
pool.close()
```

## Usage Patterns

### Via mariadb.connect() with pool_name

Create a pool automatically when connecting:

```python
import mariadb

# First connection creates the pool
conn1 = mariadb.connect(
    "mariadb://user:password@localhost:3306/mydb",
    pool_name="mypool"
)

# Use the connection
cursor = conn1.cursor()
cursor.execute("SELECT * FROM users")
results = cursor.fetchall()
cursor.close()
conn1.close()

# Subsequent connections reuse the existing pool
conn2 = mariadb.connect(pool_name="mypool")
conn2.close()
```

### With Context Managers

Use context managers for automatic connection cleanup:

```python
import mariadb

pool = mariadb.ConnectionPool(
    "mariadb://user:password@localhost/mydb?pool_name=mypool&pool_size=10"
)

# Context manager automatically closes connection
with pool.connection() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")
    results = cursor.fetchall()
    cursor.close()

pool.close()
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
- `pool_size` - Number of connections in pool (default: 5)
- `autocommit` - Enable autocommit mode (default: false)
- `ssl` - Enable SSL/TLS connection
- `local_infile` - Enable LOAD DATA LOCAL INFILE

**Example with Multiple Options:**
```python
pool = mariadb.ConnectionPool(
    "mariadb://user:pass@localhost/db?pool_name=mypool&pool_size=20&autocommit=true&ssl=true"
)
```

**Note:** Keyword arguments override URI parameters:
```python
# pool_size in URI is 5, but kwarg overrides to 10
pool = mariadb.ConnectionPool(
    "mariadb://user:pass@localhost/db?pool_name=mypool&pool_size=5",
    pool_size=10  # This takes precedence
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
    pool_size=10,                    # Number of connections
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
| `pool_size` | int | - | Convenience parameter that sets both min_size and max_size |
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
    pool_size=10  # Creates pool with min=10, max=10
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
    "mariadb://user:pass@localhost/db?pool_name=mypool&pool_size=15&max_idle_time=600"
)
```


## Best Practices

### 1. Always Close Connections

Return connections to the pool by closing them:

```python
conn = pool.get_connection()
try:
    # Use connection
    pass
finally:
    conn.close()  # Returns to pool
```

### 2. Use Context Managers

Prefer context managers for automatic cleanup:

```python
with pool.connection() as conn:
    cursor = conn.cursor()
    # Use connection
    cursor.close()
# Connection automatically returned to pool
```

### 3. Configure Pool Size Appropriately

Set pool size based on your application's concurrency:

```python
# For web applications with 10-20 concurrent requests
pool = mariadb.ConnectionPool(
    "mariadb://user:pass@host/db?pool_size=15"
)
```

## License

LGPL 2.1+