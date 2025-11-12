#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2012-2014 Monty Program Ab
# Copyright (c) 2015-2025 MariaDB Corporation Ab

"""
Benchmark: DO 1
Simple command execution benchmark.
"""

import pytest


def test_do_1(benchmark, connection, driver_name):
    """Benchmark DO 1 command execution."""
    
    def do_1():
        cursor = connection.cursor()
        cursor.execute("DO 1")
        cursor.close()
    
    result = benchmark(do_1)
    print(f"\n{driver_name}: {result}")
