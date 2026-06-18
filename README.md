<p style="text-align: center;">
  <a href="https://mariadb.com/">
    <img src="https://mariadb.com/wp-content/uploads/2019/11/mariadb-horizontal-blue.svg"/>
  </a>
</p>

# MariaDB Connector/Python

[![License (LGPL version 2.1+)][licence-image]](LICENSE)
[![Python 3.10][python-image]][python-url]
[![Run CI Tests](https://github.com/mariadb-corporation/mariadb-connector-python/actions/workflows/ci.yml/badge.svg?branch=2.0)](https://github.com/mariadb-corporation/mariadb-connector-python/actions/workflows/ci.yml)
<a href="https://scan.coverity.com/projects/mariadb-connector-python">
  <img alt="Coverity Scan Build Status" src="https://scan.coverity.com/projects/21386/badge.svg"/>
</a>

MariaDB Connector/Python enables python programs to access MariaDB and MySQL databases, using an API which is compliant with the Python DB API 2.0 (PEP-249).

## Installation

### Basic Installation

```bash
pip install mariadb
```

### Optional Dependencies

MariaDB Connector/Python supports optional dependencies for enhanced functionality:

| Package | Description | Installation |
|---------|-------------|--------------|
| `mariadb` | Pure Python implementation (default fallback) | `pip install mariadb` |
| `mariadb[c]` | C extension for better performance | `pip install mariadb[c]` |
| `mariadb[binary]` | Pre-compiled binary wheels (recommended) | `pip install mariadb[binary]` |
| `mariadb[pool]` | Connection pooling support | `pip install mariadb[pool]` |

**Install multiple extras:**
```bash
pip install mariadb[binary,pool]
```

## Synchronous and Asynchronous APIs

MariaDB Connector/Python provides **two complete implementations** for different use cases:

### Synchronous API
The traditional blocking API using `mariadb.connect()` for standard Python applications:
- Simple and straightforward to use
- Compatible with existing synchronous code
- Ideal for scripts, CLI tools, and traditional web frameworks

### Asynchronous API
Native async/await support using `mariadb.asyncConnect()` for modern async Python applications:
- Non-blocking I/O operations
- Efficient handling of concurrent database operations

Both APIs provide:
- Full DB-API 2.0 compliance
- Connection pooling support
- Prepared statement caching
- SSL/TLS support
- Transaction management


## Benchmarks

We want MariaDB Connector/Python to be a **very fast** connector for MariaDB and
MySQL, either with C or pure python implementation. We don't guess, we benchmark. A simple, reproducible benchmark suite
lives in the [`benchmarks/`](benchmarks) folder. It measures various operations
(simple queries, bulk reads, wide rows, batch inserts, many-parameter statements)
and compares the `mariadb` C extension and pure-Python implementations against
PyMySQL and MySQL Connector/Python.

**Command round-trip — `DO 1`** (operations/second, higher is better):

![DO 1 benchmark](docs/benchmarks/do_1.png)

**Bulk read — `SELECT 1000 rows`** :

![SELECT 1000 rows benchmark](docs/benchmarks/select_1000_rows_text.png)

more on [docs/benchmarks.md](docs/benchmarks.md).

## Quick Start

### Basic Connection and Query (Synchronous)

```python
import mariadb

# Connect to MariaDB using URI
with mariadb.connect("mariadb://root:password@localhost:3306/mydb") as conn:

    with conn.cursor() as cursor:
        # Execute query
        cursor.execute("SELECT * FROM users WHERE id = ?", (1,))

        # Fetch results
        for row in cursor.fetchall():
            print(row)

```

### Connection with Parameters

You can also use keyword arguments if preferred:

```python
import mariadb

# Connect using parameters
with mariadb.connect(
    host="localhost",
    port=3306,
    user="root",
    password="password",
    database="mydb"
) as conn:
    with conn.cursor() as cursor:
        cursor.execute("SELECT version()")
        version = cursor.fetchone()
        print(f"MariaDB version: {version[0]}")
```

### Basic Connection and Query (Asynchronous)

```python
import mariadb
import asyncio

async def main():
    # Connect to MariaDB using async API
    async with await mariadb.asyncConnect(
        host="localhost",
        port=3306,
        user="root",
        password="password",
        database="mydb"
    ) as conn:
        async with conn.cursor() as cursor:
            # Execute query
            await cursor.execute("SELECT * FROM users WHERE id = ?", (1,))

            # Fetch results
            async for row in cursor:
                print(row)

# Run async function
asyncio.run(main())
```

### Using Connection Pools (Synchronous)

Connection pools improve performance by reusing connections:

```python
import mariadb

# Create a connection pool with clean parameter separation
pool = mariadb.create_pool(
    host="localhost",
    port=3306,
    user="user",
    password="password",
    database="mydb",
    min_size=5,
    max_size=10,
    ping_threshold=0.25  # only check health of idle connections after 0.25 seconds of inactivity
)

# Get connection from pool
with pool.acquire() as conn:
    with conn.cursor() as cursor:
        # Insert data
        cursor.execute("INSERT INTO users (name, email) VALUES (?, ?)",
                       ("John Doe", "john@example.com"))
        conn.commit()

        # Fetch data
        cursor.execute("SELECT * FROM users WHERE name = ?", ("John Doe",))
        for row in cursor.fetchall():
            print(f"User: {row}")

```

### Named Pools with mariadb.connect()

```python
import mariadb

# First connection creates the pool
with mariadb.connect(
    "mariadb://user:password@localhost:3306/mydb",
    pool_name="mypool"
) as conn:
    with conn.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]
        print(f"Total users: {count}")

# Subsequent connections reuse the pool
with mariadb.connect(pool_name="mypool") as conn:
    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM users LIMIT 5")
        for row in cursor.fetchall():
            print(row)
```

### Dictionary and Named Tuple Cursors

```python
import mariadb

with mariadb.connect("mariadb://user:password@localhost/mydb") as conn:
    # Dictionary cursor - access columns by name
    with conn.cursor(dictionary=True) as cursor:
        cursor.execute("SELECT id, name, email FROM users LIMIT 1")
        row = cursor.fetchone()
        print(f"User: {row['name']}, Email: {row['email']}")

    # Named tuple cursor - access columns as attributes
    with conn.cursor(named_tuple=True) as cursor:
        cursor.execute("SELECT id, name, email FROM users LIMIT 1")
        row = cursor.fetchone()
        print(f"User: {row.name}, Email: {row.email}")
```

### Using Connection Pools (Asynchronous)

Async connection pools for high-performance async applications:

```python
import asyncio
import mariadb

async def main():
    # Create async connection pool
    pool = await mariadb.create_async_pool(
        host="localhost",
        user="user",
        password="password",
        database="mydb",
        min_size=5,
        max_size=10
    )

    # Get connection from pool
    async with await pool.acquire() as conn:
        async with conn.cursor() as cursor:
            # Fetch results
            await cursor.execute("SELECT * FROM users WHERE id = ?", (1,))
            row = await cursor.fetchone()
            print(f"User: {row}")

            # Fetch multiple rows
            await cursor.execute("SELECT * FROM users LIMIT 5")
            async for row in cursor:
                print(f"User: {row}")

            # Insert data with transaction
            await cursor.execute(
                "INSERT INTO users (name, email) VALUES (?, ?)",
                ("Jane Doe", "jane@example.com")
            )
            await conn.commit()

    await pool.close()

# Run the async function
asyncio.run(main())
```

**Using keyword arguments:**

```python
import asyncio
import mariadb

async def main():
    # Connect using keyword arguments
    async with await mariadb.asyncConnect(
        host="localhost",
        user="root",
        password="password",
        database="mydb"
    ) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT COUNT(*) FROM users")
            count = (await cursor.fetchone())[0]
            print(f"Total users: {count}")

asyncio.run(main())
```

## Features

- **DB-API 2.0 Compliant**: Full compliance with Python Database API specification
- **Async/Await Support**: Full asyncio support with `asyncConnect()` and async cursors
- **High Performance**: C extension for optimal performance
- **Connection Pooling**: Built-in connection pool management
- **URI Support**: Connect using connection URIs for clean configuration
- **Prepared Statements**: Automatic prepared statement support
- **Multiple Result Sets**: Handle multiple result sets from stored procedures
- **SSL/TLS Support**: Secure connections with SSL/TLS
- **Compression**: Optional protocol compression
- **Transaction Support**: Full transaction management with savepoints
- **LOAD DATA LOCAL INFILE**: Secure local file loading with `local_infile=True` option

## License

MariaDB Connector/Python is licensed under the LGPL 2.1 or later (LGPL-2.1-or-later)

## Source code

MariaDB Connector/Python source code is hosted on [Github](https://github.com/mariadb-corporation/mariadb-connector-python)

## Documentation

MariaDB Connector/Python documentation can be found on [Github Pages](https://mariadb-corporation.github.io/mariadb-connector-python/)

## Bugs

Bugs and feature requests should be filed in the [MariaDB bug ticket system](https://jira.mariadb.org/)


[licence-image]:https://img.shields.io/badge/license-GNU%20LGPL%20version%202.1-green.svg?style=flat-square
[python-image]:https://img.shields.io/badge/python-3.10-blue.svg
[python-url]:https://www.python.org/downloads/release/python-3100/
