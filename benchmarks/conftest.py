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
from types import ModuleType
from typing import Any, Iterator
import pytest


# Connection transport selection.
# Set TEST_DB_UNIX_SOCKET (e.g. /run/mysqld/mysqld.sock) to force every driver
# onto that unix socket; leave it unset to connect over TCP/IP. Either way EVERY
# driver uses the SAME transport (configured per-driver in transport_args) and
# TLS is disabled.
_UNIX_SOCKET : str | None = os.environ.get('TEST_DB_UNIX_SOCKET') or None

# libmariadb only selects the unix socket when host is 'localhost' (an IP host
# forces TCP); pymysql / mysql-connector use the socket whenever unix_socket is
# passed. So use 'localhost' in socket mode, and an IP to force TCP otherwise.
_HOST_ENV: str = os.environ.get('TEST_DB_HOST', '127.0.0.1')
# 'localhost' in socket mode (libmariadb only uses the socket then); an IP otherwise to force TCP.
_HOST: str = 'localhost' if _UNIX_SOCKET else ('127.0.0.1' if _HOST_ENV == 'localhost' else _HOST_ENV)

DB_CONFIG: dict[str, Any] = {
    'host': _HOST,
    'port': int(os.environ.get('TEST_DB_PORT', '3306')),
    'user': os.environ.get('TEST_DB_USER', 'root'),
    'password': os.environ.get('TEST_DB_PASSWORD', ''),
    'database': os.environ.get('TEST_DB_DATABASE', 'testp'),
}


def transport_args(driver_name: str) -> dict[str, Any]:
    """Per-driver kwargs so every driver uses the SAME transport with TLS
    disabled: a unix socket if one is available (see _UNIX_SOCKET), else plain
    TCP/IP. (mariadb and pymysql otherwise negotiate TLS by default.)"""
    args: dict[str, Any]
    if driver_name in ('mariadb', 'mariadb_c'):
        args = {'ssl': False}
    else:  # pymysql, mysql_connector, mysql_connector_pure
        args = {'ssl_disabled': True}
    if _UNIX_SOCKET:
        args['unix_socket'] = _UNIX_SOCKET
    return args

# Global variable to store mysql_connector implementation type
_mysql_connector_impl: str | None = None


def get_driver_module(driver_name: str) -> Any:
    """Import and return the specified driver module."""
    if driver_name in ['mariadb', 'mariadb_c']:
        # Environment variable is already set by run_benchmarks.py
        import mariadb
        print(f"\n{driver_name} using implementation: {mariadb.__impl__}")
        return mariadb
    elif driver_name == 'pymysql':
        import pymysql
        return pymysql
    elif driver_name in ['mysql_connector', 'mysql_connector_pure']:
        global _mysql_connector_impl
        import mysql.connector
        if driver_name == 'mysql_connector_pure':
            print(f"\n{driver_name} using implementation: pure Python (use_pure=True)")
        else:
            # Detect if using C extension or pure Python implementation
            try:
                import _mysql_connector
                from mysql.connector.connection_cext import CMySQLConnection
                _mysql_connector_impl = "C"
                impl_type = "C extension (CMySQLConnection)"
            except ImportError:
                _mysql_connector_impl = "Python"
                impl_type = "pure Python (MySQLConnection)"
            print(f"\n{driver_name} using implementation: {impl_type}")
        return mysql.connector
    else:
        raise ValueError(f"Unknown driver: {driver_name}")


def _get_driver_ids() -> list[str]:
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
    ids.append('mysql_connector_pure')
    
    return ids


@pytest.fixture(scope='session', params=['mariadb', 'mariadb_c', 'pymysql', 'mysql_connector', 'mysql_connector_pure'], ids=_get_driver_ids())
def driver_name(request: pytest.FixtureRequest) -> str:
    """Parametrize tests across all drivers."""
    return str(request.param)


@pytest.fixture(scope='session')
def driver(driver_name: str) -> Any:
    """Get the driver module for the current test."""
    # Extract base driver name (remove implementation type suffix if present)
    base_name = driver_name.split(' (')[0] if ' (' in driver_name else driver_name
    return get_driver_module(base_name)


_driver_warmed_up: dict[str, bool] = {}

@pytest.fixture(scope='session')
def warmup_session(driver: ModuleType, driver_name: str) -> None:
    """Warm up the database and driver once per session, automatically before any tests run."""
    driver_key = driver_name
    if driver_key not in _driver_warmed_up:
        # Create a temporary connection just for warmup
        if driver_name == 'mysql_connector_pure':
            warmup_conn = driver.connect(**DB_CONFIG, use_pure=True, **transport_args(driver_name))
        else:
            warmup_conn = driver.connect(**DB_CONFIG, **transport_args(driver_name))
        warmup_cursor = warmup_conn.cursor()
        
        # Warm up with simple queries (simulates running test_do_1 first)
        for _ in range(1000):
            warmup_cursor.execute("DO 1")
        
        # Also warm up cursor creation/destruction pattern
        warmup_cursor.close()
        for _ in range(1000):
            warmup_cursor = warmup_conn.cursor()
            warmup_cursor.execute("SELECT seq, 'abcdefghijabcdefghijabcdefghijaa' FROM seq_1_to_1000")
            warmup_cursor.fetchall()
            warmup_cursor.close()
        
        warmup_conn.close()
        _driver_warmed_up[driver_key] = True


@pytest.fixture(scope='function')
def connection(driver: ModuleType, driver_name: str, warmup_session: None) -> Iterator[Any]:
    """Create a database connection for each test."""
    # Now create the actual test connection
    if driver_name == 'mysql_connector_pure':
        conn = driver.connect(**DB_CONFIG, use_pure=True, **transport_args(driver_name))
    else:
        conn = driver.connect(**DB_CONFIG, **transport_args(driver_name))
    yield conn
    try:
        conn.close()
    except:
        pass


@pytest.fixture(scope='session')
def setup_database() -> Iterator[None]:
    """Setup test database tables once per session."""
    # Use mariadb for setup (doesn't matter which driver)
    os.environ['MARIADB_PYTHON_CONNECTOR'] = 'python'
    import mariadb
    
    conn = mariadb.connect(**DB_CONFIG, **transport_args('mariadb'))
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
        
        # Warm up the test100 table by accessing it multiple times
        for _ in range(100):
            cursor.execute("SELECT * FROM test100")
            cursor.fetchone()
        
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

        # Create perfTestInsertTypes table (int, date, string) for the mixed-type INSERT benchmark
        cursor.execute("DROP TABLE IF EXISTS perfTestInsertTypes")
        create_mixed = (
            "CREATE TABLE perfTestInsertTypes ("
            "i INT, d DATE, "
            "bool_col BOOLEAN, bytes_col VARBINARY(255), small_str VARCHAR(32), "
            "float_col FLOAT, decimal_col DECIMAL(10,2), null_col INT, "
            "datetime_col DATETIME, time_col TIME"
            ") COLLATE='utf8mb4_unicode_ci'"
        )
        try:
            cursor.execute(create_mixed + " ENGINE = BLACKHOLE")
        except:
            cursor.execute(create_mixed)

        conn.commit()
    finally:
        cursor.close()
        conn.close()
    
    yield
    
    # Cleanup after all tests
    conn = mariadb.connect(**DB_CONFIG, **transport_args('mariadb'))
    cursor = conn.cursor()
    try:
        cursor.execute("DROP TABLE IF EXISTS test100")
        cursor.execute("DROP TABLE IF EXISTS perfTestTextBatch")
        cursor.execute("DROP TABLE IF EXISTS perfTestInsertTypes")
        conn.commit()
    finally:
        cursor.close()
        conn.close()
