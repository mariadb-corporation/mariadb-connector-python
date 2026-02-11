#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2012-2014 Monty Program Ab
# Copyright (c) 2015-2025 MariaDB Corporation Ab

"""
Benchmark: SELECT 1000 rows
Benchmark fetching 1000 rows with text and binary protocol.
"""

import pytest


SQL = "SELECT seq, 'abcdefghijabcdefghijabcdefghijaa' FROM seq_1_to_1000"


def test_select_1000_rows_text(benchmark, connection, driver_name):
    """Benchmark SELECT 1000 rows using text protocol (regular execute)."""
    
    SQL_WHERE = SQL + " WHERE 1 = ?"
    SQL_WHERE_PERCENT = SQL + " WHERE 1 = %s"
    
    # Warmup: ensure seq table is in cache
    for _ in range(500):
        cursor = connection.cursor()
        if driver_name == 'mariadb':
            cursor.execute(SQL_WHERE, (1,))
        elif driver_name == 'mariadb_c':
            cursor.execute(SQL_WHERE, (1,), force_text=True)
        else:
            cursor.execute(SQL_WHERE_PERCENT, (1,))
        cursor.fetchall()
        cursor.close()
    
    if driver_name == 'mariadb':
        def select_1000_rows():
            cursor = connection.cursor()
            cursor.execute(SQL_WHERE, (1,))
            rows = cursor.fetchall()
            cursor.close()
            return len(rows)
    elif driver_name == 'mariadb_c':
        def select_1000_rows():
            cursor = connection.cursor()
            cursor.execute(SQL_WHERE, (1,), force_text=True)
            rows = cursor.fetchall()
            cursor.close()
            return len(rows)
    else:
        def select_1000_rows():
            cursor = connection.cursor()
            cursor.execute(SQL_WHERE_PERCENT, (1,))
            rows = cursor.fetchall()
            cursor.close()
            return len(rows)
    
    result = benchmark(select_1000_rows)
    print(f"\n{driver_name} (text): {result}")


def test_select_1000_rows_binary(benchmark, connection, driver_name):
    """Benchmark SELECT 1000 rows using binary protocol (prepared statement)."""
    
    # Skip for drivers that don't support binary protocol
    if 'pymysql' in driver_name:
        pytest.skip("pymysql does not support binary protocol")
    
    SQL_WHERE = SQL + " WHERE 1 = ?"
    SQL_WHERE_PERCENT = SQL + " WHERE 1 = %s"
    
    if driver_name == 'mariadb':
        # Warmup
        cursor = connection.cursor(binary=True)
        for _ in range(500):
            cursor.execute(SQL_WHERE, (1,))
            cursor.fetchall()
        cursor.close()
        
        def select_1000_rows():
            cursor = connection.cursor(binary=True)
            cursor.execute(SQL_WHERE, (1,))
            rows = cursor.fetchall()
            cursor.close()
            return len(rows)
    elif driver_name == 'mariadb_c':
        # C driver: SELECT with int params uses binary protocol by default
        cursor = connection.cursor()
        for _ in range(500):
            cursor.execute(SQL_WHERE, (1,))
            cursor.fetchall()
        cursor.close()
        
        def select_1000_rows():
            cursor = connection.cursor()
            cursor.execute(SQL_WHERE, (1,))
            rows = cursor.fetchall()
            cursor.close()
            return len(rows)
    else:
        # mysql_connector: use prepared=True for binary protocol
        cursor = connection.cursor(prepared=True)
        for _ in range(500):
            cursor.execute(SQL_WHERE_PERCENT, (1,))
            cursor.fetchall()
        cursor.close()
        
        def select_1000_rows():
            cursor = connection.cursor(prepared=True)
            cursor.execute(SQL_WHERE_PERCENT, (1,))
            rows = cursor.fetchall()
            cursor.close()
            return len(rows)
    
    result = benchmark(select_1000_rows)
    print(f"\n{driver_name} (binary): {result}")
