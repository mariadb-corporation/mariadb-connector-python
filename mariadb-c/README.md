# mariadb-c

`mariadb-c` is the **C extension backend** for the [mariadb](https://pypi.org/project/mariadb/) connector.
It provides a compiled native module (`mariadb_c`) that the `mariadb` package selects automatically when
installed alongside it, replacing the pure-Python implementation with a significantly faster alternative.

## Relationship to `mariadb`

| Package | Description |
|---|---|
| [`mariadb`](https://pypi.org/project/mariadb/) | Main connector — pure Python, works out of the box |
| `mariadb-c` | C extension backend — install alongside `mariadb` for better performance |
| `mariadb-binary` | Pre-compiled binary wheels with bundled dependencies (recommended for most users) |
| `mariadb-pool` | Connection pool add-on |

When `mariadb-c` is installed, the `mariadb` package detects and uses it automatically — no code changes required.

## Requirements

- Python ≥ 3.10
- [MariaDB Connector/C](https://mariadb.com/docs/server/connect/programming-languages/c/) ≥ 3.3 (headers and library must be available at build time)

On Debian/Ubuntu:

```bash
sudo apt-get install libmariadb-dev
```

On RHEL/Fedora:

```bash
sudo dnf install mariadb-connector-c-devel
```

On macOS:

```bash
brew install mariadb-connector-c
```

## Installation

Install `mariadb` together with `mariadb-c` to get the C-accelerated connector:

```bash
pip install mariadb[c]
```

Or, if you prefer pre-built binary wheels that bundle all native dependencies (no compiler needed):

```bash
pip install mariadb mariadb-binary
```

## Usage

No API changes — import `mariadb` as usual:

```python
import mariadb

conn = mariadb.connect(
    user="alice",
    password="secret",
    host="localhost",
    database="mydb",
)
cursor = conn.cursor()
cursor.execute("SELECT @@version")
print(cursor.fetchone())
conn.close()
```

To verify which backend is active:

```python
import mariadb

print(mariadb.__version__)       # e.g. "2.0.0rc1-c"
print(mariadb.__version_type__)  # "c"
```

## Links

- **mariadb on PyPI**: https://pypi.org/project/mariadb/
- **Documentation**: https://mariadb-corporation.github.io/mariadb-connector-python/
- **Source code**: https://github.com/mariadb-corporation/mariadb-connector-python
- **Bug tracker**: https://jira.mariadb.org/

