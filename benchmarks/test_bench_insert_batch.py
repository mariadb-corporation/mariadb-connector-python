#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2012-2014 Monty Program Ab
# Copyright (c) 2015-2025 MariaDB Corporation Ab

"""
Benchmark: Batch INSERT
Benchmark batch insert operations with 100 rows.
"""

import pytest
import random
import string


def random_string(length=100):
    """Generate a random string with emojis."""
    chars = list(string.ascii_letters + string.digits + "\\Z😎🌶🎤🥂")
    return ''.join(random.choice(chars) for _ in range(length))


@pytest.mark.usefixtures("setup_database")
def test_insert_batch(benchmark, connection, driver_name):
    """Benchmark batch insert of 100 rows."""
    
    def insert_batch():
        cursor = connection.cursor()
        s = random_string(100)
        
        if driver_name == 'mariadb' or driver_name == 'mariadb_c':
            # Use executemany
            data = [(s,) for _ in range(100)]
            cursor.executemany("INSERT INTO perfTestTextBatch(t0) VALUES (?)", data)
        else:  # pymysql
            # Use executemany with %s
            data = [(s,) for _ in range(100)]
            cursor.executemany("INSERT INTO perfTestTextBatch(t0) VALUES (%s)", data)
        
        cursor.close()
        # Clear table for next iteration
        cursor = connection.cursor()
        cursor.execute("DELETE FROM perfTestTextBatch")
        cursor.close()
    
    result = benchmark(insert_batch)
    print(f"\n{driver_name}: {result}")
