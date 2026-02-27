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

    is_mariadb = driver_name in ('mariadb', 'mariadb_c')
    SQL_WHERE = SQL + (" WHERE 1 = ?" if is_mariadb else " WHERE 1 = %s")

    # Warmup: ensure seq table is in cache
    for _ in range(500):
        cursor = connection.cursor()
        cursor.execute(SQL_WHERE, (1,))
        cursor.fetchall()
        cursor.close()

    def select_1000_rows():
        cursor = connection.cursor()
        cursor.execute(SQL_WHERE, (1,))
        rows = cursor.fetchall()
        cursor.close()
        return len(rows)

    result = benchmark(select_1000_rows)
    print(f"\n{driver_name} (text): {result}")


def test_select_1000_rows_binary(benchmark, connection, driver_name):
    """Benchmark SELECT 1000 rows using binary protocol (prepared statement)."""

    if 'pymysql' in driver_name:
        pytest.skip("pymysql does not support binary protocol")

    is_mariadb = driver_name in ('mariadb', 'mariadb_c')
    SQL_WHERE = SQL + (" WHERE 1 = ?" if is_mariadb else " WHERE 1 = %s")
    cursor_kwargs = {'binary': True} if is_mariadb else {'prepared': True}

    # Warmup
    cursor = connection.cursor(**cursor_kwargs)
    for _ in range(500):
        cursor.execute(SQL_WHERE, (1,))
        cursor.fetchall()
    cursor.close()

    def select_1000_rows():
        cursor = connection.cursor(**cursor_kwargs)
        cursor.execute(SQL_WHERE, (1,))
        rows = cursor.fetchall()
        cursor.close()
        return len(rows)

    result = benchmark(select_1000_rows)
    print(f"\n{driver_name} (binary): {result}")
