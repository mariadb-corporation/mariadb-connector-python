#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2012-2014 Monty Program Ab
# Copyright (c) 2015-2025 MariaDB Corporation Ab

"""
Benchmark: DO with 1000 parameters
Benchmark parameter binding with many parameters.
"""

import pytest


# Build SQL with 1000 parameters
SQL = "DO " + ",".join(["?" if i == 0 else "?" for i in range(1000)])
SQL_PERCENT = "DO " + ",".join(["%s" for _ in range(1000)])


def test_do_1000_params_text(benchmark, connection, driver_name):
    """Benchmark DO with 1000 parameters using text protocol."""
    
    params = list(range(1, 1001))
    
    def do_1000_params():
        cursor = connection.cursor()
        if driver_name == 'mariadb' or driver_name == 'mariadb_c':
            cursor.execute(SQL, params)
        else:  # pymysql
            cursor.execute(SQL_PERCENT, params)
        cursor.close()
    
    result = benchmark(do_1000_params)
    print(f"\n{driver_name} (text): {result}")
