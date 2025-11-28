#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2012-2014 Monty Program Ab
# Copyright (c) 2015-2025 MariaDB Corporation Ab

"""
Benchmark: SELECT 1
Simple SELECT query benchmark.
"""

import pytest


def test_select_1(benchmark, connection, driver_name):
    """Benchmark SELECT 1 query execution."""
    
    # Warmup: ensure connection is established and cached
    cursor = connection.cursor()
    for _ in range(10):
        cursor.execute("SELECT 1")
        cursor.fetchone()
    
    def select_1():
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        return result[0]
    
    result = benchmark(select_1)
    cursor.close()
    print(f"\n{driver_name}: {result}")
