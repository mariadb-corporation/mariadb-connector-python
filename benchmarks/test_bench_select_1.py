#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2012-2014 Monty Program Ab
# Copyright (c) 2015-2025 MariaDB Corporation Ab

"""
Benchmark: SELECT 1
Simple SELECT query benchmark.
"""

from typing import Any

import pytest


def test_select_1(benchmark: Any, connection: Any, driver_name: str) -> None:
    """Benchmark SELECT 1 query execution."""

    # Warmup: ensure connection is established and cached
    cursor = connection.cursor()
    for _ in range(10):
        cursor.execute("SELECT 1")
        cursor.fetchone()
    cursor.close()

    def select_1() -> Any:
        cursor = connection.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        cursor.close()
        return result[0]
    
    result = benchmark(select_1)
    print(f"\n{driver_name}: {result}")
