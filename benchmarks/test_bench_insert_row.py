#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2012-2014 Monty Program Ab
# Copyright (c) 2015-2025 MariaDB Corporation Ab

"""
Benchmark: single-row INSERT covering a broad range of types
(int, date, string, boolean, bytes, small string, float, decimal, NULL,
datetime, time) into a BLACKHOLE table. Exercises parameter binding / type
conversion across the common Python -> SQL type mappings on the write path.
"""

import datetime
from decimal import Decimal

import pytest

_COLUMNS = ("i, d, bool_col, bytes_col, small_str, float_col, "
            "decimal_col, null_col, datetime_col, time_col")
_VALUES = (
    42,                                              # int
    datetime.date(2026, 6, 18),                      # date
    True,                                            # boolean
    b"\x00\x01\x02\x03binary-data\xfe\xff",          # bytes
    "small",                                         # small string
    3.14159,                                         # float
    Decimal("12345.67"),                             # decimal
    None,                                            # NULL
    datetime.datetime(2026, 6, 18, 14, 30, 15),      # datetime
    datetime.time(14, 30, 15),                       # time
)


@pytest.mark.usefixtures("setup_database")
def test_insert_row(benchmark, connection, driver_name):
    """Benchmark a single-row INSERT of mixed types into a BLACKHOLE table."""
    cursor = connection.cursor()
    placeholder = "?" if driver_name in ('mariadb', 'mariadb_c') else "%s"
    sql = "INSERT INTO perfTestInsertTypes (%s) VALUES (%s)" % (
        _COLUMNS, ", ".join([placeholder] * len(_VALUES)))

    def insert_row():
        cursor.execute(sql, _VALUES)

    result = benchmark(insert_row)
    print(f"\n{driver_name}: {result}")
