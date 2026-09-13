# MariaDB Python Connector Benchmarks

Comprehensive benchmark suite comparing **mariadb** (pure Python), **mariadb_c** (C extension), **pymysql**, **mysql_connector** (C extension), and **mysql_connector_pure** (pure Python).

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

# Run all benchmarks except mysql_connector_pure (faster)
make bench-fast

# Or run individually
python run_benchmarks.py --driver mariadb --json benchmark_mariadb.json
python run_benchmarks.py --driver mariadb_c --json benchmark_mariadb_c.json
python run_benchmarks.py --driver pymysql --json benchmark_pymysql.json
python run_benchmarks.py --driver mysql_connector --json benchmark_mysql_connector.json
python run_benchmarks.py --driver mysql_connector_pure --json benchmark_mysql_connector_pure.json

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
- **Batch INSERT 10k** - `executemany()` of 10,000 mixed-type rows into a BLACKHOLE table
- **Concurrent connections** - 50 threads each doing connect + single-row point query + close
- **Connection pool** - 500 point queries from 20 threads through a 5-20 pool (drivers with a pool)

## Async Benchmarks

`async/` compares `mariadb.AsyncConnection` (pure Python and C extension)
with **aiomysql** and **asyncmy**. Besides the six tests above it adds the
scenarios of [asyncmy's own benchmark suite](https://github.com/long2ice/asyncmy/tree/dev/benchmark):
a 10,000-row batch insert, 50 concurrent connections (connect + single-row
point query + close), and 500 concurrent queries through a 5-20 connection pool.

```bash
pip install aiomysql asyncmy
make bench-async            # all async drivers + comparison table
make compare-async          # table from existing benchmark_async_*.json
```

## Documentation

See [BENCHMARKS.md](BENCHMARKS.md) for complete documentation including:
- Detailed benchmark descriptions
- Setup instructions
- Usage examples
- Performance interpretation
- Troubleshooting guide