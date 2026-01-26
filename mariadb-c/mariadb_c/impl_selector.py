# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
MariaDB-C implementation selector

This module handles the selection between sync and async implementations
for the C extension, similar to the mariadb package's impl_selector.
"""

import os
import sys
from typing import Any, Type


# Global variables to store the selected implementation
__impl__: str = "c"  # Always C for mariadb-c
sync_connection: Any = None
async_connection: Any = None
Cursor: Type[Any] = None
SyncCursor: Type[Any] = None
AsyncCursor: Type[Any] = None


def _select_implementation() -> None:
    """
    Select the best MariaDB-C implementation available.
    
    For mariadb-c, we always use the C extension for sync operations.
    For async operations, we check if the async C implementation is available.
    
    Uses MARIADB_PYTHON_CONNECTOR environment variable:
    - 'c' or 'mariadb_c': Use C extension (default)
    - Other values: Ignored (mariadb-c only provides C implementation)
    
    Async implementation:
    - If async_connections module is available, use it
    - Otherwise, async_connection will be None
    
    Note: PyPy 3.11+ has cpyext stack overflow issues with C extension async.
    On PyPy, async_connection will be None (use pure Python mariadb package instead).
    """
    global __impl__, sync_connection, async_connection, Cursor, SyncCursor, AsyncCursor
    
    impl = os.environ.get("MARIADB_PYTHON_CONNECTOR", "").lower()
    
    # mariadb-c always uses C extension for sync
    __impl__ = "c"
    
    # Import sync implementation (always available)
    try:
        from . import connections
        from . import cursors
        sync_connection = connections
        Cursor = cursors.Cursor
        SyncCursor = cursors.Cursor
    except Exception as e:
        raise ImportError(f"couldn't import mariadb_c sync implementation: {e}") from e
    
    # Check if running on PyPy
    is_pypy = hasattr(sys, 'pypy_version_info')
    
    # Try to import async implementation (skip on PyPy due to cpyext issues)
    if is_pypy:
        # PyPy has cpyext stack overflow issues with C extension async
        # Set to None - users should use pure Python mariadb package for async on PyPy
        async_connection = None
        AsyncCursor = None
    else:
        try:
            from . import async_connections
            from . import async_cursors
            async_connection = async_connections
            AsyncCursor = async_cursors.AsyncCursor
        except Exception as e:
            # Async not available - this is okay, just set to None
            async_connection = None
            AsyncCursor = None
            # Only warn if explicitly requested
            if impl in ("c", "mariadb_c"):
                import warnings
                warnings.warn(
                    f"mariadb_c async implementation not available: {e}. "
                    "Only sync operations will work.",
                    ImportWarning
                )


# Select implementation on module import
_select_implementation()
