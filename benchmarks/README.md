# MariaDB Python Connector Benchmarks

Comprehensive benchmark suite comparing **mariadb** (pure Python), **mariadb_c** (C extension), and **pymysql**.

## Quick Start

```bash
# Install dependencies
pip install -r requirements-bench.txt

# Set database connection (optional, defaults to localhost)
export TEST_DB_HOST=localhost
export TEST_DB_PORT=3306
export TEST_DB_USER=root
export TEST_DB_PASSWORD=yourpassword
export TEST_DB_DATABASE=testp

# Run all benchmarks
make bench-all

# Or run individually
python run_benchmarks.py --driver mariadb --json benchmark_mariadb.json
python run_benchmarks.py --driver mariadb_c --json benchmark_mariadb_c.json
python run_benchmarks.py --driver pymysql --json benchmark_pymysql.json
python run_benchmarks.py --driver mysql_connector --json benchmark_mysql_connector.json

# Generate comparison report
python run_benchmarks.py --compare
```

## Benchmark Tests

- **DO 1** - Simple command execution overhead
- **SELECT 1** - Simple query execution
- **SELECT 1000 Rows** - Bulk data retrieval (text & binary protocol)
- **SELECT 100 Columns** - Wide result set parsing
- **DO 1000 Parameters** - Parameter binding overhead
- **Batch INSERT** - Batch insert performance (100 rows)

## Documentation

See [BENCHMARKS.md](BENCHMARKS.md) for complete documentation including:
- Detailed benchmark descriptions
- Setup instructions
- Usage examples
- Performance interpretation
- Troubleshooting guide