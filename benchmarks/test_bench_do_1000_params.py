#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2012-2014 Monty Program Ab
# Copyright (c) 2015-2025 MariaDB Corporation Ab

"""
Benchmark: DO with 1000 parameters
Benchmark parameter binding with many parameters (text and binary protocol).
"""

import pytest


# Build SQL with 1000 parameters
SQL = "DO " + ",".join(["?" for _ in range(1000)])
SQL_PERCENT = "DO " + ",".join(["%s" for _ in range(1000)])


def test_do_1000_params_text(benchmark, connection, driver_name):
    """Benchmark DO with 1000 parameters using text protocol."""
    
    params = list(range(1, 1001))
    
    if driver_name == 'mariadb':
        # Pure Python driver: int params use text protocol by default
        def do_1000_params():
            cursor = connection.cursor()
            cursor.execute(SQL, params)
            cursor.close()
    elif driver_name == 'mariadb_c':
        # C driver: force text protocol (DO defaults to binary in C parser)
        def do_1000_params():
            cursor = connection.cursor()
            cursor.execute(SQL, params, force_text=True)
            cursor.close()
    else:
        # pymysql / mysql_connector: always text protocol
        def do_1000_params():
            cursor = connection.cursor()
            cursor.execute(SQL_PERCENT, params)
            cursor.close()
    
    result = benchmark(do_1000_params)
    print(f"\n{driver_name} (text): {result}")


def test_do_1000_params_binary(benchmark, connection, driver_name):
    """Benchmark DO with 1000 parameters using binary (prepared) protocol."""
    
    if 'pymysql' in driver_name:
        pytest.skip("pymysql does not support binary protocol")
    
    params = list(range(1, 1001))
    
    if driver_name == 'mariadb':
        # Pure Python driver: use binary=True to force binary protocol
        def do_1000_params():
            cursor = connection.cursor(binary=True)
            cursor.execute(SQL, params)
            cursor.close()
    elif driver_name == 'mariadb_c':
        # C driver: DO with int params uses binary protocol by default
        def do_1000_params():
            cursor = connection.cursor()
            cursor.execute(SQL, params)
            cursor.close()
    else:
        # mysql_connector: use prepared=True for binary protocol
        def do_1000_params():
            cursor = connection.cursor(prepared=True)
            cursor.execute(SQL_PERCENT, params)
            cursor.close()
    
    result = benchmark(do_1000_params)
    print(f"\n{driver_name} (binary): {result}")
