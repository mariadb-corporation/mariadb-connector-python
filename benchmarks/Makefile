# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2012-2014 Monty Program Ab
# Copyright (c) 2015-2025 MariaDB Corporation Ab

.PHONY: help install bench bench-all bench-mariadb bench-mariadb-c bench-pymysql bench-mysql-connector compare clean

help:
	@echo "MariaDB Python Connector Benchmarks"
	@echo ""
	@echo "Available targets:"
	@echo "  install             - Install benchmark dependencies"
	@echo "  bench               - Run all benchmarks for all drivers"
	@echo "  bench-all           - Run all benchmarks and generate report"
	@echo "  bench-mariadb       - Run benchmarks for mariadb (pure Python)"
	@echo "  bench-mariadb-c     - Run benchmarks for mariadb_c (C extension)"
	@echo "  bench-pymysql       - Run benchmarks for pymysql"
	@echo "  bench-mysql-connector - Run benchmarks for mysql-connector-python"
	@echo "  compare             - Generate comparison report from existing results"
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

bench-mariadb:
	python run_benchmarks.py --driver mariadb --json benchmark_mariadb.json

bench-mariadb-c:
	python run_benchmarks.py --driver mariadb_c --json benchmark_mariadb_c.json

bench-pymysql:
	python run_benchmarks.py --driver pymysql --json benchmark_pymysql.json

bench-mysql-connector:
	python run_benchmarks.py --driver mysql_connector --json benchmark_mysql_connector.json

compare:
	python run_benchmarks.py --compare

clean:
	rm -rf results_*
	rm -f benchmark_*.json
	rm -rf .benchmarks
	rm -rf __pycache__
	find . -name "*.pyc" -delete
	find . -name ".pytest_cache" -type d -exec rm -rf {} + 2>/dev/null || true
