#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2012-2014 Monty Program Ab
# Copyright (c) 2015-2025 MariaDB Corporation Ab

"""
Benchmark configuration and fixtures for comparing mariadb, mariadb_c, and pymysql.
"""

import os
import sys
import pytest


# Database configuration from environment variables
DB_CONFIG = {
    'host': os.environ.get('TEST_DB_HOST', 'localhost'),
    'port': int(os.environ.get('TEST_DB_PORT', '3306')),
    'user': os.environ.get('TEST_DB_USER', 'root'),
    'password': os.environ.get('TEST_DB_PASSWORD', ''),
    'database': os.environ.get('TEST_DB_DATABASE', 'testp'),
}


def get_driver_module(driver_name):
    """Import and return the specified driver module."""
    if driver_name in ['mariadb', 'mariadb_c']:
        # Environment variable is already set by run_benchmarks.py
        import mariadb
        print(f"\n{driver_name} using implementation: {mariadb.__impl__}")
        return mariadb
    elif driver_name == 'pymysql':
        import pymysql
        return pymysql
    else:
        raise ValueError(f"Unknown driver: {driver_name}")


@pytest.fixture(scope='session', params=['mariadb', 'mariadb_c', 'pymysql'])
def driver_name(request):
    """Parametrize tests across all three drivers."""
    return request.param


@pytest.fixture(scope='session')
def driver(driver_name):
    """Get the driver module for the current test."""
    return get_driver_module(driver_name)


@pytest.fixture(scope='function')
def connection(driver):
    """Create a database connection for each test."""
    conn = driver.connect(**DB_CONFIG)
    yield conn
    try:
        conn.close()
    except:
        pass


@pytest.fixture(scope='session')
def setup_database():
    """Setup test database tables once per session."""
    # Use mariadb for setup (doesn't matter which driver)
    os.environ['MARIADB_PYTHON_CONNECTOR'] = 'python'
    import mariadb
    
    conn = mariadb.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    try:
        # Install BLACKHOLE engine if available
        try:
            cursor.execute("INSTALL SONAME 'ha_blackhole'")
        except:
            pass
        
        # Create test100 table (100 integer columns)
        cursor.execute("DROP TABLE IF EXISTS test100")
        cols = ",".join([f"i{i} int" for i in range(1, 101)])
        cursor.execute(f"CREATE TABLE test100 ({cols})")
        vals = ",".join([str(i) for i in range(1, 101)])
        cursor.execute(f"INSERT INTO test100 VALUES ({vals})")
        
        # Create perfTestTextBatch table
        cursor.execute("DROP TABLE IF EXISTS perfTestTextBatch")
        create_table = (
            "CREATE TABLE perfTestTextBatch ("
            "id MEDIUMINT NOT NULL AUTO_INCREMENT, "
            "t0 text, "
            "PRIMARY KEY (id)"
            ") COLLATE='utf8mb4_unicode_ci'"
        )
        try:
            cursor.execute(create_table + " ENGINE = BLACKHOLE")
        except:
            cursor.execute(create_table)
        
        conn.commit()
    finally:
        cursor.close()
        conn.close()
    
    yield
    
    # Cleanup after all tests
    conn = mariadb.connect(**DB_CONFIG)
    cursor = conn.cursor()
    try:
        cursor.execute("DROP TABLE IF EXISTS test100")
        cursor.execute("DROP TABLE IF EXISTS perfTestTextBatch")
        conn.commit()
    finally:
        cursor.close()
        conn.close()
