#!/bin/bash
# SPDX-License-Identifier: LGPL-2.1-or-later
# Example usage of the benchmark suite

echo "=== MariaDB Python Connector Benchmark Examples ==="
echo ""

# Example 1: Run a single benchmark
echo "Example 1: Run SELECT 1 benchmark for all drivers"
echo "Command: python run_benchmarks.py --benchmark select_1"
echo ""

# Example 2: Run benchmarks for specific driver
echo "Example 2: Run all benchmarks for mariadb_c only"
echo "Command: python run_benchmarks.py --driver mariadb_c"
echo ""

# Example 3: Save results and compare
echo "Example 3: Complete workflow with comparison"
echo "Commands:"
echo "  python run_benchmarks.py --driver mariadb --json benchmark_mariadb.json"
echo "  python run_benchmarks.py --driver mariadb_c --json benchmark_mariadb_c.json"
echo "  python run_benchmarks.py --driver pymysql --json benchmark_pymysql.json"
echo "  python run_benchmarks.py --compare"
echo ""

# Example 4: Using Make
echo "Example 4: Using Makefile shortcuts"
echo "Commands:"
echo "  make install          # Install dependencies"
echo "  make bench-mariadb-c  # Benchmark C extension"
echo "  make bench-all        # Run everything and generate report"
echo ""

# Example 5: Direct pytest usage
echo "Example 5: Using pytest-benchmark directly"
echo "Commands:"
echo "  pytest test_bench_select_1.py -v --benchmark-only"
echo "  pytest -k mariadb_c --benchmark-only --benchmark-histogram=results"
echo ""

echo "For full documentation, see BENCHMARKS.md"
