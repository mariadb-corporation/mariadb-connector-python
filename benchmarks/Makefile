# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2012-2014 Monty Program Ab
# Copyright (c) 2015-2025 MariaDB Corporation Ab

.PHONY: help install bench bench-all bench-fast bench-mariadb bench-mariadb-c bench-pymysql bench-mysql-connector bench-mysql-connector-pure compare bench-async bench-async-mariadb bench-async-mariadb-c bench-async-aiomysql bench-async-asyncmy compare-async clean

help:
	@echo "MariaDB Python Connector Benchmarks"
	@echo ""
	@echo "Available targets:"
	@echo "  install             - Install benchmark dependencies"
	@echo "  bench               - Run all benchmarks for all drivers"
	@echo "  bench-all           - Run all benchmarks and generate report"
	@echo "  bench-fast          - Run all benchmarks except mysql_connector_pure"
	@echo "  bench-mariadb       - Run benchmarks for mariadb (pure Python)"
	@echo "  bench-mariadb-c     - Run benchmarks for mariadb_c (C extension)"
	@echo "  bench-pymysql       - Run benchmarks for pymysql"
	@echo "  bench-mysql-connector - Run benchmarks for mysql-connector-python (C)"
	@echo "  bench-mysql-connector-pure - Run benchmarks for mysql-connector-python (pure Python)"
	@echo "  compare             - Generate comparison report from existing results"
	@echo "  bench-async         - Run async benchmarks for every async driver and compare"
	@echo "  bench-async-mariadb - Async benchmarks for mariadb (pure Python)"
	@echo "  bench-async-mariadb-c - Async benchmarks for mariadb_c (C extension)"
	@echo "  bench-async-aiomysql - Async benchmarks for aiomysql"
	@echo "  bench-async-asyncmy - Async benchmarks for asyncmy"
	@echo "  compare-async       - Comparison report from existing async results"
	@echo "  clean               - Remove benchmark results"
	@echo ""
	@echo "Environment variables:"
	@echo "  TEST_DB_HOST     - Database host (default: localhost)"
	@echo "  TEST_DB_PORT     - Database port (default: 3306)"
	@echo "  TEST_DB_USER     - Database user (default: root)"
	@echo "  TEST_DB_PASSWORD - Database password (default: empty)"
	@echo "  TEST_DB_DATABASE - Database name (default: testp)"

install:
	pip install -r requirements-bench.txt

bench:
	python run_benchmarks.py

bench-all:
	python run_all_benchmarks.py

bench-fast:
	python run_all_benchmarks.py --skip mysql_connector_pure

bench-mariadb:
	python run_benchmarks.py --driver mariadb --json benchmark_mariadb.json

bench-mariadb-c:
	python run_benchmarks.py --driver mariadb_c --json benchmark_mariadb_c.json

bench-pymysql:
	python run_benchmarks.py --driver pymysql --json benchmark_pymysql.json

bench-mysql-connector:
	python run_benchmarks.py --driver mysql_connector --json benchmark_mysql_connector.json

bench-mysql-connector-pure:
	python run_benchmarks.py --driver mysql_connector_pure --json benchmark_mysql_connector_pure.json

compare:
	python run_benchmarks.py --compare

bench-async:
	python run_async_benchmarks.py --all

bench-async-mariadb:
	python run_async_benchmarks.py --driver mariadb_async --json benchmark_async_mariadb_async.json

bench-async-mariadb-c:
	python run_async_benchmarks.py --driver mariadb_c_async --json benchmark_async_mariadb_c_async.json

bench-async-aiomysql:
	python run_async_benchmarks.py --driver aiomysql --json benchmark_async_aiomysql.json

bench-async-asyncmy:
	python run_async_benchmarks.py --driver asyncmy --json benchmark_async_asyncmy.json

compare-async:
	python run_async_benchmarks.py --compare

clean:
	rm -rf results_*
	rm -f benchmark_*.json
	rm -rf async/__pycache__
	rm -rf .benchmarks
	rm -rf __pycache__
	find . -name "*.pyc" -delete
	find . -name ".pytest_cache" -type d -exec rm -rf {} + 2>/dev/null || true
