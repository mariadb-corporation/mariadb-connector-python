#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pytest configuration for MariaDB Connector/Python tests

This file contains shared fixtures and configuration for all tests.
"""
from __future__ import annotations


import os
from typing import Any, Callable, Dict, Iterator, TYPE_CHECKING, TypedDict, cast
import pytest

from mariadb_shared.connection_params import ConnectionOptions
from mariadb_shared.rows import TupleRow
from mariadb_shared.sync_connection_common import SyncConnectionCommon
from mariadb_shared.sync_cursor_common import SyncCursorCommon

if TYPE_CHECKING:
    from typing_extensions import Unpack

class _TestConfigRequired(TypedDict):
    host: str
    user: str
    database: str
    port: int


class TestConfig(_TestConfigRequired, total=False):
    """The test connection parameters: the base keys are always present, the
    others depend on the environment (TLS, password, pool reset). Every key is
    a connect() keyword, so a TestConfig can be unpacked into connect(),
    asyncConnect() or the pool factories with the row type resolved."""
    ssl: bool | Dict[str, Any]
    ssl_ca: str
    ssl_verify_cert: bool
    tls_fp: str | None
    password: str | None
    pool_reset_connection: bool
    # keys the tests set on a configuration before connecting
    unix_socket: str | None
    connect_timeout: float
    read_timeout: int
    write_timeout: int
    init_command: str | None
    autocommit: bool
    status_callback: Callable[..., Any] | None
    converter: Dict[int, Callable[[Any], Any]] | None


def get_test_config(**overrides: Unpack[ConnectionOptions]) -> TestConfig:
    """Get test configuration from environment variables, with per-test
    overrides, e.g. ``conf(ssl=False)``"""
    config: TestConfig = {
        "user": os.environ.get('TEST_DB_USER', 'root'),
        "host": os.environ.get('TEST_DB_HOST', '127.0.0.1'),
        "database": os.environ.get('TEST_DB_DATABASE', 'testp'),
        "port": int(os.environ.get('TEST_DB_PORT', '3306')),
        "ssl": False
    }
    

    if os.environ.get('TEST_REQUIRE_TLS') == "1":
        config["ssl"] = True

    if TEST_DB_SERVER_CERT := os.environ.get('TEST_DB_SERVER_CERT'):
        if config["ssl"] != False:
            config["ssl_ca"] = TEST_DB_SERVER_CERT

    # Optional pool reset configuration
    if os.environ.get('TEST_RESET_SESSION'):
        reset = int(os.environ.get('TEST_RESET_SESSION', '1'))
        config["pool_reset_connection"] = bool(reset)
    
    # Optional password
    if os.environ.get('TEST_DB_PASSWORD'):
        config["password"] = os.environ.get('TEST_DB_PASSWORD')
    
    # The overrides may carry any connection keyword; the result keeps the
    # TestConfig shape for the callers that read the base keys.
    return cast(TestConfig, {**config, **overrides})

@pytest.fixture(scope="session")
def test_config() -> TestConfig:
    """Provide test configuration for all tests"""
    return get_test_config()



@pytest.fixture
def connection(test_config: TestConfig) -> Iterator[SyncConnectionCommon[TupleRow]]:
    """Provide a database connection for tests"""
    import mariadb
    try:
        conn = mariadb.connect(**test_config)
    except Exception as e:
        pytest.skip(f"Cannot connect to database: {e}")
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def cursor(connection: SyncConnectionCommon[Any]) -> Iterator[SyncCursorCommon[Any]]:
    """Provide a database cursor for tests"""
    cursor = connection.cursor()
    yield cursor
    cursor.close()


@pytest.fixture
def binary_cursor(connection: SyncConnectionCommon[Any]) -> Iterator[SyncCursorCommon[Any]]:
    """Provide a binary (server prepared statement) cursor for tests"""
    cursor = connection.cursor(binary=True)
    yield cursor
    cursor.close()

# Test markers
def pytest_configure(config: pytest.Config) -> None:
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


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Automatically mark tests based on their location"""
    for item in items:
        # Mark integration tests
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
            item.add_marker(pytest.mark.requires_server)
        
        # Mark unit tests (tests not in integration folder)
        elif "integration" not in str(item.fspath):
            item.add_marker(pytest.mark.unit)
