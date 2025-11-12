#!/bin/bash
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2012-2014 Monty Program Ab
# Copyright (c) 2015-2025 MariaDB Corporation Ab

# Run all benchmarks and generate comparison report

set -e

echo "=========================================="
echo "MariaDB Python Connector Benchmark Suite"
echo "=========================================="
echo ""

# Check if database is accessible
echo "Checking database connection..."
if ! mysql -h ${TEST_DB_HOST:-localhost} -P ${TEST_DB_PORT:-3306} -u ${TEST_DB_USER:-root} ${TEST_DB_PASSWORD:+-p$TEST_DB_PASSWORD} ${TEST_DB_DATABASE:-testp} -e "SELECT 1" > /dev/null 2>&1; then
    echo "Error: Cannot connect to database"
    echo "Please set TEST_DB_* environment variables"
    exit 1
fi
echo "✓ Database connection OK"
echo ""

# Create results directory
RESULTS_DIR="results_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RESULTS_DIR"
echo "Results will be saved to: $RESULTS_DIR"
echo ""

# Run benchmarks for each driver
for driver in mariadb mariadb_c pymysql; do
    echo "=========================================="
    echo "Running benchmarks for: $driver"
    echo "=========================================="
    
    output_file="$RESULTS_DIR/benchmark_${driver}.json"
    
    if python run_benchmarks.py --driver "$driver" --json "$output_file"; then
        echo "✓ $driver benchmarks completed"
    else
        echo "✗ $driver benchmarks failed"
    fi
    echo ""
done

# Generate comparison report
echo "=========================================="
echo "Generating Comparison Report"
echo "=========================================="
python run_benchmarks.py --compare --compare-files \
    "$RESULTS_DIR"/benchmark_*.json | tee "$RESULTS_DIR/comparison_report.txt"

echo ""
echo "=========================================="
echo "Benchmark Complete!"
echo "=========================================="
echo "Results saved to: $RESULTS_DIR"
echo ""
echo "View detailed results:"
echo "  - JSON files: $RESULTS_DIR/benchmark_*.json"
echo "  - Comparison: $RESULTS_DIR/comparison_report.txt"
echo ""
