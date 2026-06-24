#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2012-2014 Monty Program Ab
# Copyright (c) 2015-2025 MariaDB Corporation Ab

"""
Benchmark: SELECT 100 columns
Benchmark fetching a row with 100 integer columns.
"""

from typing import Any

import pytest


@pytest.mark.usefixtures("setup_database")
def test_select_100_cols_text(benchmark: Any, connection: Any, driver_name: str) -> None:
    """Benchmark SELECT 100 columns using text protocol."""

    is_mariadb = driver_name in ('mariadb', 'mariadb_c')

    def select_100_cols() -> int:
        cursor = connection.cursor()
        if is_mariadb:
            cursor.execute("SELECT * FROM test100 WHERE 1 = ?", (1,))
        else:
            cursor.execute("SELECT * FROM test100 WHERE 1 = %s", (1,))
        row = cursor.fetchone()
        cursor.close()
        return sum(row)

    result = benchmark(select_100_cols)
    print(f"\n{driver_name} (text): {result}")


@pytest.mark.usefixtures("setup_database")
def test_select_100_cols_binary(benchmark: Any, connection: Any, driver_name: str) -> None:
    """Benchmark SELECT 100 columns using binary protocol (prepared statement)."""

    if 'pymysql' in driver_name:
        pytest.skip("pymysql does not support binary protocol")

    is_mariadb = driver_name in ('mariadb', 'mariadb_c')

    def select_100_cols() -> int:
        if is_mariadb:
            cursor = connection.cursor(binary=True)
            cursor.execute("SELECT * FROM test100 WHERE 1 = ?", (1,))
        else:
            cursor = connection.cursor(prepared=True)
            cursor.execute("SELECT * FROM test100 WHERE 1 = %s", (1,))
        row = cursor.fetchone()
        cursor.close()
        return sum(row)

    result = benchmark(select_100_cols)
    print(f"\n{driver_name} (binary): {result}")
