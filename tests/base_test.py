#!/usr/bin/env python -O
# -*- coding: utf-8 -*-
import os
import sys
from pathlib import Path

# Add the mariadb module to the path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import mariadb

try:
    from .conftest import get_test_config as conf
except ImportError:
    # Fallback for direct import
    from conftest import get_test_config as conf


def is_skysql():
    if conf()["host"][-13:] == "db.skysql.net":
        return True
    return False


def is_maxscale(conn=None):
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

def is_native():
    return mariadb.__impl__ == 'python'

def is_async_native():
    """
    Check if pure Python implementation is being used for async operations.
    
    Returns True if using pure Python async (mariadb.async_connection).
    Returns False if using C extension async (mariadb_c.async_connections).
    
    On PyPy 3.11+, the pure Python implementation is used for async operations
    even when mariadb-c is installed, so we need to check the actual implementation.
    """
    # Check if AsyncConnection is from pure Python or C extension
    if hasattr(mariadb, 'AsyncConnection') and mariadb.AsyncConnection is not None:
        module = mariadb.AsyncConnection.__module__
        # Pure Python async: mariadb.async_connection
        # C extension async: mariadb_c.async_connections
        return 'mariadb.async_connection' in module
    
    # If no AsyncConnection, fall back to general is_native() check
    return is_native()

def is_mysql():
    mysql_server = 1
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute("select version()")
    row = cursor.fetchone()
    if "MARIADB" in row[0].upper():
        mysql_server = 0
    conn.close()
    del cursor, conn
    return mysql_server

def get_host_suffix():
    return "@'localhost'" if os.getenv("LOCAL_DB", "container") == "local" else "@'%'"

def create_connection(additional_conf=None):
    default_conf = conf()
    if additional_conf is None:
        c = {key: value for (key, value) in (default_conf.items())}
    else:
        c = {key: value for (key, value) in (list(default_conf.items()) + list(
            additional_conf.items()))}
    return mariadb.connect(**c)
