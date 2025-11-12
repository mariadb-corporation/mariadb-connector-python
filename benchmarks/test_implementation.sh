#!/bin/bash
# Test script to verify driver implementations are correctly selected

echo "Testing mariadb (pure Python)..."
MARIADB_PYTHON_CONNECTOR=python python -c "import mariadb; print(f'Implementation: {mariadb.__impl__}')"

echo ""
echo "Testing mariadb_c (C extension)..."
MARIADB_PYTHON_CONNECTOR=c python -c "import mariadb; print(f'Implementation: {mariadb.__impl__}')"

echo ""
echo "Testing via run_benchmarks.py..."
python run_benchmarks.py --driver mariadb --benchmark do_1 2>&1 | grep -E "(MARIADB_PYTHON_CONNECTOR|implementation)"
echo ""
python run_benchmarks.py --driver mariadb_c --benchmark do_1 2>&1 | grep -E "(MARIADB_PYTHON_CONNECTOR|implementation)"
