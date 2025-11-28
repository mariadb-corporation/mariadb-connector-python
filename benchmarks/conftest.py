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

# Global variable to store mysql_connector implementation type
_mysql_connector_impl = None


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
    elif driver_name == 'mysql_connector':
        global _mysql_connector_impl
        import mysql.connector
        # Detect if using C extension or pure Python implementation
        # The C extension module is _mysql_connector
        try:
            import _mysql_connector
            from mysql.connector.connection_cext import CMySQLConnection
            _mysql_connector_impl = "C"
            impl_type = "C extension (CMySQLConnection)"
        except ImportError:
            _mysql_connector_impl = "Python"
            impl_type = "pure Python (MySQLConnection)"
        print(f"\n{driver_name} using implementation: {impl_type}")
        print(f"Note: mysql-connector-python C extension is slower than mariadb-connector-python C implementation")
        return mysql.connector
    else:
        raise ValueError(f"Unknown driver: {driver_name}")


def _get_driver_ids():
    """Generate driver IDs for parametrization, detecting mysql_connector implementation type."""
    global _mysql_connector_impl
    
    # Detect mysql_connector implementation type early
    if _mysql_connector_impl is None:
        try:
            import mysql.connector
            # Create a test connection to see which implementation is actually used
            # Check the default connection class
            test_config = {'host': 'localhost', 'user': 'root'}
            try:
                # Try to determine from connection class without actually connecting
                # Check if CMySQLConnection is available and will be used by default
                from mysql.connector.connection_cext import CMySQLConnection
                _mysql_connector_impl = "C"
            except ImportError:
                _mysql_connector_impl = "Python"
        except Exception:
            # Fallback: check if _mysql_connector module exists
            try:
                import _mysql_connector
                _mysql_connector_impl = "C"
            except ImportError:
                _mysql_connector_impl = "Python"
    
    ids = ['mariadb', 'mariadb_c', 'pymysql']
    if _mysql_connector_impl:
        ids.append(f'mysql_connector ({_mysql_connector_impl})')
    else:
        ids.append('mysql_connector')
    
    return ids


@pytest.fixture(scope='session', params=['mariadb', 'mariadb_c', 'pymysql', 'mysql_connector'], ids=_get_driver_ids())
def driver_name(request):
    """Parametrize tests across all drivers."""
    return request.param


@pytest.fixture(scope='session')
def driver(driver_name):
    """Get the driver module for the current test."""
    # Extract base driver name (remove implementation type suffix if present)
    base_name = driver_name.split(' (')[0] if ' (' in driver_name else driver_name
    return get_driver_module(base_name)


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
        table_sql = f"CREATE TABLE test100 ({cols})"
        try:
            cursor.execute(table_sql + " ENGINE = MEMORY")
        except:
            cursor.execute(table_sql)
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
