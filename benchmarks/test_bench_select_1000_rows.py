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
    
    # Warmup: ensure seq table is in cache
    for _ in range(500):
        cursor = connection.cursor()
        if driver_name == 'mariadb' or driver_name == 'mariadb_c':
            cursor.execute(SQL + " WHERE 1 = ?", (1,))
        else:  # pymysql, mysql_connector
            cursor.execute(SQL + " WHERE 1 = %s", (1,))
        cursor.fetchall()
        cursor.close()
    
    def select_1000_rows():
        cursor = connection.cursor()
        if driver_name == 'mariadb' or driver_name == 'mariadb_c':
            cursor.execute(SQL + " WHERE 1 = ?", (1,))
        else:  # pymysql, mysql_connector
            cursor.execute(SQL + " WHERE 1 = %s", (1,))
        rows = cursor.fetchall()
        cursor.close()
        return len(rows)
    
    result = benchmark(select_1000_rows)
    print(f"\n{driver_name} (text): {result}")


def test_select_1000_rows_binary(benchmark, connection, driver_name):
    """Benchmark SELECT 1000 rows using binary protocol (prepared statement)."""
    
    # Skip for drivers that don't support binary protocol
    if driver_name in ['pymysql', 'mysql_connector']:
        pytest.skip(f"{driver_name} doesn't support binary protocol")
    
    # Warmup: ensure seq table is in cache
    cursor = connection.cursor(binary=True)
    for _ in range(500):
        if driver_name == 'mariadb' or driver_name == 'mariadb_c':
            cursor.execute(SQL + " WHERE 1 = ?", (1,))
        else:  # pymysql, mysql_connector
            cursor.execute(SQL + " WHERE 1 = %s", (1,))
        cursor.fetchall()
    cursor.close()
    
    def select_1000_rows():
        cursor = connection.cursor(binary=True)
        if driver_name == 'mariadb' or driver_name == 'mariadb_c':
            cursor.execute(SQL + " WHERE 1 = ?", (1,))
        else:  # pymysql, mysql_connector
            cursor.execute(SQL + " WHERE 1 = %s", (1,))
        rows = cursor.fetchall()
        cursor.close()
        return len(rows)
    
    result = benchmark(select_1000_rows)
    print(f"\n{driver_name} (binary): {result}")
