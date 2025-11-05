#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pytest configuration for MariaDB Connector/Python tests

This file contains shared fixtures and configuration for all tests.
"""

import os
import pytest

import logging

#logging.getLogger('mariadb').setLevel(logging.DEBUG)

def get_test_config():
    """Get test configuration from environment variables"""
    config = {
        "user": os.environ.get('TEST_DB_USER', 'root'),
        "host": os.environ.get('TEST_DB_HOST', 'localhost'),
        "database": os.environ.get('TEST_DB_DATABASE', 'testp'),
        "port": int(os.environ.get('TEST_DB_PORT', '3306'))
    }
    

    # Optional SSL configuration
    if os.environ.get('TEST_REQUIRE_TLS'):
        if os.environ.get('TEST_REQUIRE_TLS') == "1":
            config["ssl"] = True
    
    # Optional pool reset configuration
    if os.environ.get('TEST_RESET_SESSION'):
        reset = int(os.environ.get('TEST_RESET_SESSION', '1'))
        config["pool_reset_connection"] = reset
    
    # Optional password
    if os.environ.get('TEST_DB_PASSWORD'):
        config["password"] = os.environ.get('TEST_DB_PASSWORD')
    
    return config

@pytest.fixture(scope="session")
def test_config():
    """Provide test configuration for all tests"""
    return get_test_config()


@pytest.fixture(scope="session") 
def module_config():
    """Provide module configuration for all tests"""
    return get_module_config()


@pytest.fixture
def connection(test_config):
    """Provide a database connection for tests"""
    try:
        import mariadb
        conn = mariadb.connect(**test_config)
        yield conn
    except Exception as e:
        pytest.skip(f"Cannot connect to database: {e}")
    finally:
        if 'conn' in locals():
            conn.close()


@pytest.fixture
def cursor(connection):
    """Provide a database cursor for tests"""
    cursor = connection.cursor()
    yield cursor
    cursor.close()


@pytest.fixture
def binary_cursor(connection):
    """Provide a binary (server prepared statement) cursor for tests"""
    cursor = connection.cursor(binary=True)
    yield cursor
    cursor.close()


@pytest.fixture
def prepared_cursor(connection):
    """Provide a prepared statement cursor for tests"""
    cursor = connection.cursor(prepared=True)
    yield cursor
    cursor.close()


# Test markers
def pytest_configure(config):
    """Configure pytest markers"""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )
    config.addinivalue_line(
        "markers", "slow: marks tests as slow running"
    )
    config.addinivalue_line(
        "markers", "requires_server: marks tests that require a running MariaDB server"
    )


def pytest_collection_modifyitems(config, items):
    """Automatically mark tests based on their location"""
    for item in items:
        # Mark integration tests
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
            item.add_marker(pytest.mark.requires_server)
        
        # Mark unit tests (tests not in integration folder)
        elif "integration" not in str(item.fspath):
            item.add_marker(pytest.mark.unit)
