#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2012-2014 Monty Program Ab
# Copyright (c) 2015-2025 MariaDB Corporation Ab

"""
Benchmark: SELECT 100 columns
Benchmark fetching a row with 100 integer columns.
"""

import pytest


@pytest.mark.usefixtures("setup_database")
def test_select_100_cols_text(benchmark, connection, driver_name):
    """Benchmark SELECT 100 columns using text protocol."""
    
    def select_100_cols():
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM test100")
        row = cursor.fetchone()
        cursor.close()
        # Consume all values to ensure fair comparison
        total = sum(row)
        return total
    
    result = benchmark(select_100_cols)
    print(f"\n{driver_name} (text): {result}")


@pytest.mark.usefixtures("setup_database")
def test_select_100_cols_binary(benchmark, connection, driver_name):
    """Benchmark SELECT 100 columns using binary protocol (prepared statement)."""
    
    # Skip for pymysql as it doesn't support binary protocol
    if driver_name == 'pymysql':
        pytest.skip("pymysql doesn't support binary protocol")
    
    def select_100_cols():
        cursor = connection.cursor(binary=True)
        cursor.execute("SELECT * FROM test100")
        row = cursor.fetchone()
        cursor.close()
        # Consume all values to ensure fair comparison
        total = sum(row)
        return total
    
    result = benchmark(select_100_cols)
    print(f"\n{driver_name} (binary): {result}")
