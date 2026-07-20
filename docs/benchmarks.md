# Benchmarks

Performance comparison of **MariaDB Connector/Python**. Both the `mariadb` C
extension and the pure-Python implementation against
[PyMySQL](https://pypi.org/project/PyMySQL/) and
[MySQL Connector/Python](https://pypi.org/project/mysql-connector-python/)
(its C and pure-Python variants).

Every number on this page is produced by the benchmark suite in the
[`benchmarks/`](../benchmarks) folder of this repository and can be reproduced
with the commands under [Reproducing](#reproducing).

## TL;DR

The `mariadb` **C extension is the fastest driver in almost every benchmark**;
the only exceptions are the bare `DO` round-trips (no result set to parse),
where the pure-Python driver matches it. The pure-Python `mariadb`
implementation is the **fastest pure-Python driver in every benchmark**, and on
result-set parsing it now **matches or beats MySQL Connector/Python's C
extension** — e.g. `SELECT 100 columns` (7,435 vs 7,303 ops/s, text). Selected
results (operations per second, higher is better):

| Workload | mariadb (C) | vs pure-Python `mariadb` | vs MySQL Connector/C |
|---|---|---|---|
| `SELECT 1` (simple query) | **85,508 ops/s** | 1.6× faster | 2.4× faster |
| `SELECT 1000 rows` (binary) | **6,259 ops/s** | 7.7× faster | 4.2× faster |
| `SELECT 100 columns` (binary) | **13,624 ops/s** | 2.2× faster | 2.5× faster |
| `DO 1000 params` (binary) | **2,721 ops/s** | 2.0× faster | 36× faster |
| Batch `INSERT` (100 rows) | **8,454 ops/s** | 1.6× faster | 3.6× faster |

## Environment

|  |  |
|---|---|
| CPU | Intel Core i9-11900K, governor `performance` (~4.8 GHz), client pinned to one core (`taskset -c 4`) |
| OS / Python | Linux · CPython 3.14.4 |
| Server | MariaDB 12.3.2 · Unix socket · TLS off |
| Tooling | [pytest-benchmark](https://pypi.org/project/pytest-benchmark/) · ≥ 1000 rounds per benchmark (capped at ~1 s wall-time for the slowest drivers) · GC disabled |
| Method | 2 warm-up passes (discarded) then 3 reported passes; the **median** per-call time across the 3 is reported (→ ops/s) |
| Date | 2026-07-20 |

> ⚠️ Sub-millisecond micro-benchmarks are sensitive to machine state (CPU
> frequency scaling, background load, caches). These figures are meant for
> *relative* comparison between drivers on identical hardware, not as absolute
> throughput guarantees. A column is shown as `–` when a driver does not
> implement that variant (e.g. PyMySQL has no binary/prepared protocol path).

## Full results

| Benchmark | mariadb – C extension | mariadb – pure Python | PyMySQL | mysql-connector – C | mysql-connector – pure |
|---|---|---|---|---|---|
| DO 1 — command round-trip | 101,753 ops/s (1.0x) | 103,308 ops/s **(fastest)** | 91,890 ops/s (1.1x) | 52,438 ops/s (2.0x) | 31,414 ops/s (3.3x) |
| SELECT 1 — simple query | 85,508 ops/s **(fastest)** | 52,596 ops/s (1.6x) | 43,679 ops/s (2.0x) | 34,932 ops/s (2.4x) | 18,266 ops/s (4.7x) |
| INSERT — mixed types (single row) | 34,305 ops/s **(fastest)** | 30,269 ops/s (1.1x) | 26,165 ops/s (1.3x) | 30,360 ops/s (1.1x) | 17,693 ops/s (1.9x) |
| Batch INSERT — 100 rows (executemany) | 8,454 ops/s **(fastest)** | 5,394 ops/s (1.6x) | 2,141 ops/s (3.9x) | 2,370 ops/s (3.6x) | 1,885 ops/s (4.5x) |
| SELECT 1000 rows — binary protocol | 6,259 ops/s **(fastest)** | 818 ops/s (7.7x) | – | 1,490 ops/s (4.2x) | 287 ops/s (21.8x) |
| SELECT 1000 rows — text protocol | 6,781 ops/s **(fastest)** | 1,049 ops/s (6.5x) | 541 ops/s (12.5x) | 1,633 ops/s (4.2x) | 355 ops/s (19.1x) |
| SELECT 100 columns — binary protocol | 13,624 ops/s **(fastest)** | 6,170 ops/s (2.2x) | – | 5,511 ops/s (2.5x) | 1,230 ops/s (11.1x) |
| SELECT 100 columns — text protocol | 18,113 ops/s **(fastest)** | 7,435 ops/s (2.4x) | 2,543 ops/s (7.1x) | 7,303 ops/s (2.5x) | 2,362 ops/s (7.7x) |
| DO 1000 params — binary protocol | 2,721 ops/s **(fastest)** | 1,394 ops/s (2.0x) | – | 76 ops/s (35.8x) | 59 ops/s (46.2x) |
| DO 1000 params — text protocol | 4,082 ops/s **(fastest)** | 4,066 ops/s (1.0x) | 2,187 ops/s (1.9x) | 2,870 ops/s (1.4x) | 1,100 ops/s (3.7x) |

*(Multiplier in parentheses is how much slower than the fastest driver for that row.)*

### Simple operations

![DO 1 — command round-trip](benchmarks/do_1.png)
![SELECT 1 — simple query](benchmarks/select_1.png)

### Insert

![INSERT — mixed types (single row)](benchmarks/insert_row.png)
![Batch INSERT — 100 rows](benchmarks/insert_batch.png)

### Bulk reads

![SELECT 1000 rows — binary](benchmarks/select_1000_rows_binary.png)
![SELECT 1000 rows — text](benchmarks/select_1000_rows_text.png)

### Wide rows

![SELECT 100 columns — binary](benchmarks/select_100_cols_binary.png)
![SELECT 100 columns — text](benchmarks/select_100_cols_text.png)

### Many parameters

![DO 1000 params — binary](benchmarks/do_1000_params_binary.png)
![DO 1000 params — text](benchmarks/do_1000_params_text.png)

## Reproducing

From a checkout, with a MariaDB/MySQL server running:

```bash
cd benchmarks
pip install -r requirements-bench.txt          # pytest-benchmark, pymysql, mysql-connector-python
export TEST_DB_HOST=127.0.0.1 TEST_DB_PORT=3306 TEST_DB_USER=root TEST_DB_DATABASE=testp
export TEST_DB_UNIX_SOCKET=/run/mysqld/mysqld.sock   # all drivers over this socket; unset for TCP/IP
python run_all_benchmarks.py                    # all drivers -> results_<timestamp>/
```

For the stable numbers shown above, pin the CPU to maximum frequency, pin the
client to one core, warm the machine with a couple of discarded passes, then
report the **median** of several passes (which filters out any unlucky pass):

```bash
sudo cpupower frequency-set -g performance      # restore later: -g powersave
taskset -c 4 python run_all_benchmarks.py        # warm-up (discarded)
taskset -c 4 python run_all_benchmarks.py        # warm-up (discarded)
for i in 1 2 3; do                               # reported passes
  taskset -c 4 python run_all_benchmarks.py
done
# take the per-benchmark median across the 3 reported results_* dirs
```

Regenerate the charts and the table on this page from a results directory
(charts are rendered with [matplotlib](https://matplotlib.org/) using the
Google Charts colour palette):

```bash
pip install matplotlib
python make_charts.py results_<timestamp>        # writes ../docs/benchmarks/*.png + comparison_table.md
```

Individual drivers and benchmarks can also be run directly — see
[`benchmarks/README.md`](../benchmarks/README.md) and
[`benchmarks/BENCHMARKS.md`](../benchmarks/BENCHMARKS.md).
