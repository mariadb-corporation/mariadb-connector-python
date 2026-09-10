#!/usr/bin/env python -O
# -*- coding: utf-8 -*-


from __future__ import annotations

import os
import sys
from pathlib import Path

# Add the mariadb module to the path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from typing import Any, cast

import mariadb
from mariadb_shared.connection_params import ConnectionOptions
from mariadb_shared.rows import TupleRow
from mariadb_shared.sync_connection_common import SyncConnectionCommon

try:
    from .conftest import get_test_config as conf
except ImportError:
    # Fallback for direct import
    from conftest import get_test_config as conf


def is_skysql() -> bool:
    if conf()["host"][-13:] == "db.skysql.net":
        return True
    return False


def is_maxscale(conn: SyncConnectionCommon[Any] | None = None) -> bool:
    """Whether the tests run against MaxScale: asked to the server through
    ``conn`` when one is given (MaxScale 23.08+ banner), else from the
    environment (MAXSCALE_TAG, or the legacy srv variable)."""
    # Detection from server banner (MaxScale 23.08+)
    if conn is not None:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT @@maxscale_version")
            row = cursor.fetchone()
            cursor.close()
            if row and row[0]:
                return True
        except Exception:
            pass

    # Detection from environment: maxscale-tag set by connector-ci-setup action
    maxscale_tag = os.environ.get('MAXSCALE_TAG')
    if maxscale_tag:
        return True

    # Legacy detection via srv env var
    return (os.environ.get('srv') == "maxscale" or
            os.environ.get('srv') == 'skysql-ha')

def is_native() -> bool:
    return mariadb.__impl__ == 'python'

def is_async_native() -> bool:
    """
    Check if pure Python implementation is being used for async operations.
    
    Returns True if using pure Python async (mariadb.async_connection).
    Returns False if using C extension async (mariadb_c.async_connections).
    
    On PyPy 3.11+, the pure Python implementation is used for async operations
    even when mariadb-c is installed, so we need to check the actual implementation.
    """
    # Check if AsyncConnection is from pure Python or C extension
    if hasattr(mariadb, 'AsyncConnection'):
        module = mariadb.AsyncConnection.__module__
        # Pure Python async: mariadb.async_connection
        # C extension async: mariadb_c.async_connections
        return 'mariadb.async_connection' in module
    
    # If no AsyncConnection, fall back to general is_native() check
    return is_native()

def is_mysql() -> bool:
    """Whether the server under test is MySQL rather than MariaDB"""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("select version()")
        row = cursor.fetchone()
        assert row is not None
        return "MARIADB" not in str(row[0]).upper()
    finally:
        conn.close()

def get_host_suffix() -> str:
    return "@'localhost'" if os.getenv("LOCAL_DB", "container") == "local" else "@'%'"

def create_connection(additional_conf: ConnectionOptions | None = None) -> SyncConnectionCommon[TupleRow]:
    if additional_conf is None:
        return mariadb.connect(**conf())
    merged = cast(ConnectionOptions, {**conf(), **additional_conf})
    return mariadb.connect(**merged)


# ---------------------------------------------------------------------------
# Payload generators for long-data / multipart tests.
# ---------------------------------------------------------------------------
def varied_bytes(n: int) -> bytes:
    """Deterministic non-uniform bytes of length n (for BLOB columns)."""
    block = bytes(range(256))
    buf = bytearray((block * (n // 256 + 1))[:n])
    for i in range(0, n, 4096):
        buf[i] = (i // 4096) & 0xFF
    return bytes(buf)


def varied_text(n: int) -> str:
    """Deterministic non-uniform printable-ASCII str of length n (for TEXT)."""
    block = bytes(range(0x21, 0x7f))          # 94 printable ASCII chars
    buf = bytearray((block * (n // len(block) + 1))[:n])
    for i in range(0, n, 4096):
        buf[i] = 0x21 + ((i // 4096) % 94)
    return buf.decode("ascii")
