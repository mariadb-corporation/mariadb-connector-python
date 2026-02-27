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

    is_mariadb = driver_name in ('mariadb', 'mariadb_c')
    sql = SQL if is_mariadb else SQL_PERCENT
    params = list(range(1, 1001))

    def do_1000_params():
        cursor = connection.cursor()
        cursor.execute(sql, params)
        cursor.close()

    result = benchmark(do_1000_params)
    print(f"\n{driver_name} (text): {result}")


def test_do_1000_params_binary(benchmark, connection, driver_name):
    """Benchmark DO with 1000 parameters using binary (prepared) protocol."""

    if 'pymysql' in driver_name:
        pytest.skip("pymysql does not support binary protocol")

    is_mariadb = driver_name in ('mariadb', 'mariadb_c')
    sql = SQL if is_mariadb else SQL_PERCENT
    cursor_kwargs = {'binary': True} if is_mariadb else {'prepared': True}
    params = list(range(1, 1001))

    def do_1000_params():
        cursor = connection.cursor(**cursor_kwargs)
        cursor.execute(sql, params)
        cursor.close()

    result = benchmark(do_1000_params)
    print(f"\n{driver_name} (binary): {result}")
