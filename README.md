<p align="center">
  <a href="http://mariadb.com/">
    <img src="https://mariadb.com/kb/static/images/logo-2018-black.png">
  </a>
</p>

# MariaDB Connector/Python

[![License (LGPL version 2.1+)][licence-image]](LICENSE)
[![Python 3.7][python-image]][python-url]
[![Build Status](https://travis-ci.com/mariadb-corporation/mariadb-connector-python.svg?branch=1.1)](https://app.travis-ci.com/mariadb-corporation/mariadb-connector-python)
<a href="https://scan.coverity.com/projects/mariadb-connector-python">
  <img alt="Coverity Scan Build Status"
       src="https://scan.coverity.com/projects/21386/badge.svg"/>
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

## Quick Start

### Basic Connection and Query

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

or usi

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

### Using Connection Pools

Connection pools improve performance by reusing connections:

```python
import mariadb

# Create a connection pool
pool = mariadb.ConnectionPool(
    "mariadb://user:password@localhost:3306/mydb?pool_name=mypool&pool_size=10"
)

# Get connection from pool
with pool.connection() as conn:
    with conn.cursor() as cursor:
        # Insert data
        cursor.execute("INSERT INTO users (name, email) VALUES (?, ?)", 
                       ("John Doe", "john@example.com"))
        conn.commit()
        
        # Fetch data
        cursor.execute("SELECT * FROM users WHERE name = ?", ("John Doe",))
        for row in cursor.fetchall():
            print(f"User: {row}")
# Connection automatically returned to pool

# Close pool when done
pool.close()
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

## Features

- **DB-API 2.0 Compliant**: Full compliance with Python Database API specification
- **High Performance**: C extension for optimal performance
- **Connection Pooling**: Built-in connection pool management
- **URI Support**: Connect using connection URIs for clean configuration
- **Prepared Statements**: Automatic prepared statement support
- **Multiple Result Sets**: Handle multiple result sets from stored procedures
- **SSL/TLS Support**: Secure connections with SSL/TLS
- **Compression**: Optional protocol compression
- **Transaction Support**: Full transaction management with savepoints

## License

MariaDB Connector/Python is licensed under the LGPL 2.1 or later (LGPL-2.1-or-later)

## Source code

MariaDB Connector/Python source code is hosted on [Github](https://github.com/mariadb-corporation/mariadb-connector-python)

## Documentation

MariaDB Connector/Python documentation can be found on [Github Pages](https://mariadb-corporation.github.io/mariadb-connector-python/)

## Bugs

Bugs and feature requests should be filed in the [MariaDB bug ticket system](https://jira.mariadb.org/)


[licence-image]:https://img.shields.io/badge/license-GNU%20LGPL%20version%202.1-green.svg?style=flat-square
[python-image]:https://img.shields.io/badge/python-3.7-blue.svg
[python-url]:https://www.python.org/downloads/release/python-370/
