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
    
    if driver_name == 'mariadb':
        # Pure Python driver: int params use text protocol by default
        def select_100_cols():
            cursor = connection.cursor()
            cursor.execute("SELECT * FROM test100 WHERE 1 = ?", (1,))
            row = cursor.fetchone()
            cursor.close()
            return sum(row)
    elif driver_name == 'mariadb_c':
        # C driver: force text protocol (SELECT defaults to binary in C parser)
        def select_100_cols():
            cursor = connection.cursor()
            cursor.execute("SELECT * FROM test100 WHERE 1 = ?", (1,), force_text=True)
            row = cursor.fetchone()
            cursor.close()
            return sum(row)
    else:
        # pymysql / mysql_connector: always text protocol
        def select_100_cols():
            cursor = connection.cursor()
            cursor.execute("SELECT * FROM test100 WHERE 1 = %s", (1,))
            row = cursor.fetchone()
            cursor.close()
            return sum(row)
    
    result = benchmark(select_100_cols)
    print(f"\n{driver_name} (text): {result}")


@pytest.mark.usefixtures("setup_database")
def test_select_100_cols_binary(benchmark, connection, driver_name):
    """Benchmark SELECT 100 columns using binary protocol (prepared statement)."""
    
    # Skip for drivers that don't support binary protocol
    if 'pymysql' in driver_name:
        pytest.skip("pymysql does not support binary protocol")
    
    if driver_name == 'mariadb':
        # Pure Python driver: use binary=True to force binary protocol
        def select_100_cols():
            cursor = connection.cursor(binary=True)
            cursor.execute("SELECT * FROM test100 WHERE 1 = ?", (1,))
            row = cursor.fetchone()
            cursor.close()
            return sum(row)
    elif driver_name == 'mariadb_c':
        # C driver: SELECT with int params uses binary protocol by default
        def select_100_cols():
            cursor = connection.cursor()
            cursor.execute("SELECT * FROM test100 WHERE 1 = ?", (1,))
            row = cursor.fetchone()
            cursor.close()
            return sum(row)
    else:
        # mysql_connector: use prepared=True for binary protocol
        def select_100_cols():
            cursor = connection.cursor(prepared=True)
            cursor.execute("SELECT * FROM test100 WHERE 1 = %s", (1,))
            row = cursor.fetchone()
            cursor.close()
            return sum(row)
    
    result = benchmark(select_100_cols)
    print(f"\n{driver_name} (binary): {result}")
