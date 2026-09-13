# MariaDB Python Connector Benchmarks

Comprehensive benchmark suite for comparing performance between:
- **mariadb** (pure Python implementation)
- **mariadb_c** (C extension)
- **pymysql** (reference implementation)

## Overview

This benchmark suite is modeled after the Java connector benchmarks and provides fair, consistent comparisons across all three Python implementations.

## Benchmark Tests

### 1. **DO 1** (`test_bench_do_1.py`)
- **Purpose**: Measure overhead of simple command execution
- **SQL**: `DO 1`
- **Metrics**: Command execution latency

### 2. **SELECT 1** (`test_bench_select_1.py`)
- **Purpose**: Measure simple query execution and result fetching
- **SQL**: `SELECT 1`
- **Metrics**: Query execution + single row fetch latency

### 3. **SELECT 1000 Rows** (`test_bench_select_1000_rows.py`)
- **Purpose**: Measure bulk data retrieval performance
- **SQL**: `SELECT seq, 'abcdefghijabcdefghijabcdefghijaa' FROM seq_1_to_1000`
- **Variants**:
  - Text protocol (regular execute)
  - Binary protocol (prepared statements) - mariadb/mariadb_c only
- **Metrics**: Throughput for fetching 1000 rows

### 4. **SELECT 100 Columns** (`test_bench_select_100_cols.py`)
- **Purpose**: Measure wide result set parsing performance
- **SQL**: `SELECT * FROM test100` (100 integer columns)
- **Variants**:
  - Text protocol
  - Binary protocol - mariadb/mariadb_c only
- **Metrics**: Wide result set parsing latency

### 5. **DO 1000 Parameters** (`test_bench_do_1000_params.py`)
- **Purpose**: Measure parameter binding overhead
- **SQL**: `DO ?,?,?,...` (1000 parameters)
- **Metrics**: Parameter binding and encoding latency

### 6. **Batch INSERT** (`test_bench_insert_batch.py`)
- **Purpose**: Measure batch insert performance
- **SQL**: `INSERT INTO perfTestTextBatch(t0) VALUES (?)` × 100
- **Metrics**: Batch insert throughput

### 7. **Batch INSERT 10k rows** (`test_bench_insert_batch_10k.py`)
- **Purpose**: `executemany()` of 10,000 eight-column rows into a BLACKHOLE table
- **Metrics**: statement building / bulk protocol cost without storage-engine work

### 8. **Concurrent connections** (`test_bench_concurrent.py`)
- **Purpose**: 50 threads at once, each doing connect + indexed single-row point query + close
- **Metrics**: connection setup cost with many connections opened in parallel

### 9. **Connection pool** (`test_bench_pool.py`)
- **Purpose**: 500 point queries from 20 threads through a 5-20 connection pool (`mariadb.create_pool`, `mysql.connector.pooling.MySQLConnectionPool`; PyMySQL has no pool and is skipped)
- **Metrics**: acquire/release cost and fairness under contention

Scenarios 7-9 are the sync counterparts of the async suite's extra scenarios
(threads stand in for asyncio tasks) and run fewer rounds than the
micro-benchmarks.

## Setup

### Prerequisites

1. **Install dependencies**:
```bash
pip install -r requirements-bench.txt
```

2. **Install drivers**:
```bash
# Pure Python implementation
pip install -e .

# C extension (if available)
pip install -e ./mariadb_c

# PyMySQL
pip install pymysql
```

3. **Configure database**:
Set environment variables for database connection:
```bash
export TEST_DB_HOST=localhost
export TEST_DB_PORT=3306
export TEST_DB_USER=root
export TEST_DB_PASSWORD=yourpassword
export TEST_DB_DATABASE=testp
```

4. **Setup test database**:
```bash
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS testp"
```

## Running Benchmarks

### Quick Start

Run all benchmarks for all drivers:
```bash
cd benchmarks
python run_benchmarks.py
```

### Run Specific Benchmark

```bash
# Run only SELECT 1 benchmark
python run_benchmarks.py --benchmark select_1

# Run only DO 1 benchmark
python run_benchmarks.py --benchmark do_1
```

### Run for Specific Driver

```bash
# Test only mariadb_c
python run_benchmarks.py --driver mariadb_c

# Test only pymysql
python run_benchmarks.py --driver pymysql
```

### Save Results to JSON

```bash
# Save mariadb results
python run_benchmarks.py --driver mariadb --json benchmark_mariadb.json

# Save mariadb_c results
python run_benchmarks.py --driver mariadb_c --json benchmark_mariadb_c.json

# Save pymysql results
python run_benchmarks.py --driver pymysql --json benchmark_pymysql.json
```

### Generate Comparison Report

After saving results for all drivers:
```bash
python run_benchmarks.py --compare --compare-files \
    benchmark_mariadb.json \
    benchmark_mariadb_c.json \
    benchmark_pymysql.json
```

Or automatically compare all `benchmark_*.json` files:
```bash
python run_benchmarks.py --compare
```

## Async Benchmarks

The `async/` folder holds the asyncio counterpart of the suite. It compares
`mariadb.AsyncConnection` (pure Python and C extension) with
[aiomysql](https://pypi.org/project/aiomysql/) and
[asyncmy](https://pypi.org/project/asyncmy/) (Cython). Every driver connects
over the same transport with TLS disabled (`mariadb` would otherwise negotiate
TLS by default while aiomysql/asyncmy never do), so results compare
protocol/parsing cost only. Driver differences (`?` vs `%s` placeholders,
cursor/close/pool APIs, binary protocol selection) are abstracted in
`async/asyncbench.py`.


### Running

```bash
pip install aiomysql asyncmy          # also in requirements-bench.txt

make bench-async                      # every async driver, then a comparison table
make bench-async-asyncmy              # one driver -> benchmark_async_asyncmy.json
make compare-async                    # table from existing benchmark_async_*.json

# or directly
python run_async_benchmarks.py --driver mariadb_c_async --json benchmark_async_mariadb_c_async.json
python run_async_benchmarks.py --compare
```

The comparison table prints the median per-call time of each driver and its
ratio to the fastest driver on that row (`1.00x`).

## Row parser micro-benchmark (pure Python)

`parser_field_bench.py` times the pure-Python row parsers alone, per column
type and per protocol, on captured row packets (no network or cursor cost).
Use it to measure a change to one branch of `_parse_text_row_data` /
`_parse_binary_row_data` in `mariadb/impl/client/base_client.py`:

```bash
python parser_field_bench.py --save before.json
# edit the parser
python parser_field_bench.py --save after.json --compare before.json
```

## Using pytest-benchmark Directly

You can also use pytest-benchmark commands directly:

```bash
# Run with detailed output
pytest test_bench_select_1.py -v --benchmark-only

# Compare specific driver
pytest -k mariadb_c --benchmark-only

# Save histogram
pytest --benchmark-only --benchmark-histogram=histogram

# Compare against saved baseline
pytest --benchmark-only --benchmark-compare=0001
```

## Complete Workflow Example

```bash
# 1. Install dependencies
pip install -r requirements-bench.txt

# 2. Set database configuration
export TEST_DB_HOST=localhost
export TEST_DB_PORT=3306
export TEST_DB_USER=root
export TEST_DB_PASSWORD=mypassword
export TEST_DB_DATABASE=testp

# 3. Run benchmarks for each driver and save results
python run_benchmarks.py --driver mariadb --json benchmark_mariadb.json
python run_benchmarks.py --driver mariadb_c --json benchmark_mariadb_c.json
python run_benchmarks.py --driver pymysql --json benchmark_pymysql.json

# 4. Generate comparison report
python run_benchmarks.py --compare

# 5. View detailed pytest-benchmark output
pytest --benchmark-only --benchmark-compare --benchmark-histogram=comparison
```

## Expected Results

Typical performance characteristics:

### mariadb_c (C Extension)
- **Fastest** overall performance
- Best for production workloads
- Lowest latency for all operations
- Efficient binary protocol support

### mariadb (Pure Python)
- **Good** performance with pure Python
- No compilation required
- Portable across platforms
- Suitable for most applications

### pymysql
- **Reference** implementation
- Widely used and tested
- Text protocol only
- Baseline for comparison

## Interpreting Results

pytest-benchmark provides several metrics:

- **Min**: Fastest execution time observed
- **Max**: Slowest execution time observed
- **Mean**: Average execution time
- **StdDev**: Standard deviation (consistency)
- **Median**: 50th percentile
- **IQR**: Interquartile range (middle 50% of results)
- **Outliers**: Number of outlier measurements
- **Rounds**: Number of benchmark iterations

Lower values are better for all time-based metrics.

## Troubleshooting

### Connection Issues
```bash
# Verify database connection
mysql -h $TEST_DB_HOST -P $TEST_DB_PORT -u $TEST_DB_USER -p$TEST_DB_PASSWORD $TEST_DB_DATABASE -e "SELECT 1"
```

### Missing seq_1_to_1000 Table
Some benchmarks require MariaDB's sequence engine:
```sql
-- Check if available
SELECT * FROM seq_1_to_10;

-- If not available, benchmarks will skip automatically
```

### Driver Import Errors
```bash
# Verify driver installation
python -c "import mariadb; print(mariadb.__version__)"
python -c "import pymysql; print(pymysql.__version__)"
```

## Contributing

To add new benchmarks:

1. Create a new test file: `test_bench_<name>.py`
2. Use the `connection` and `driver_name` fixtures
3. Follow the existing benchmark patterns
4. Add the file to `BENCHMARKS` list in `run_benchmarks.py`
5. Update this documentation

## References

- Java Connector Benchmarks: `/mariadb-connector-j/src/benchmark/java/org/mariadb/jdbc/`
- pytest-benchmark docs: https://pytest-benchmark.readthedocs.io/
- MariaDB Connector/Python: https://github.com/mariadb-corporation/mariadb-connector-python
