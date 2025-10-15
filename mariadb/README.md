# MariaDB Connector/Python (Pure Python)

This is the pure Python implementation of the MariaDB Connector for Python.

## Overview

This package provides a Python DB API 2.0 (PEP-249) compliant interface to MariaDB and MySQL databases.

**Note:** This is a pure Python implementation with stub methods. The actual database connectivity logic needs to be implemented.

## Installation

### Basic Installation (Pure Python)

```bash
pip install mariadb-python
```

### Optional Dependencies

For better performance, install with the C extension:

```bash
pip install mariadb-python[c-extension]
```

For advanced connection pooling:

```bash
pip install mariadb-python[pool]
```

For everything (C extension + advanced pooling):

```bash
pip install mariadb-python[full]
```

## Usage

```python
import mariadb

# Connect to MariaDB
conn = mariadb.connect(
    host="localhost",
    user="root",
    password="your_password",
    database="test"
)

# Create a cursor
cursor = conn.cursor()

# Execute queries
cursor.execute("SELECT * FROM users")

# Fetch results
for row in cursor:
    print(row)

# Close connection
conn.close()
```

## Features

- DB API 2.0 compliant
- Connection pooling support
- Context manager support
- Pure Python implementation (no C dependencies required)
- Optional C extension for performance

## Development Status

This is a work in progress. The following components have been created as stubs:

- Connection management
- Cursor operations
- Connection pooling
- Exception hierarchy
- DB API 2.0 type constructors
- Field information utilities

## License

LGPL 2.1

## Author

Georg Richter
