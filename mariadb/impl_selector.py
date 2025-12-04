"""
MariaDB implementation selector

This module handles the selection between pure Python and C extension
implementations
"""

import os
import sys
from typing import Any, Type


# Global variables to store the selected implementation
__impl__: str = ""
sync_connection: Any = None
async_connection: Any = None
Cursor: Type[Any] = None
SyncCursor: Type[Any] = None
AsyncCursor: Type[Any] = None


def _select_implementation() -> None:
    """
    Select the best MariaDB implementation available.
    
    Uses MARIADB_PYTHON_CONNECTOR environment variable:
    - 'c' or 'mariadb_c': Force C extension for sync (uses pure Python for async)
    - 'binary' or 'mariadb_binary': Force binary wheel for sync (uses pure Python for async)
    - 'python' or 'mariadb': Force pure Python for both sync and async
    - Not set: Try binary first, then C extension, fallback to pure Python
    
    Note: C extension and binary wheel use pure Python async implementation
    since async is not yet implemented in C/binary.
    """
    global __impl__, sync_connection, async_connection, Cursor, SyncCursor, AsyncCursor
    
    impl = os.environ.get("MARIADB_PYTHON_CONNECTOR", "").lower()
    attempts = []
    
    def handle_error(name: str, e: Exception) -> None:
        if not impl:
            msg = f"couldn't import mariadb '{name}' implementation: {e}"
            attempts.append(msg)
        else:
            msg = f"couldn't import requested mariadb '{name}' implementation: {e}"
            raise ImportError(msg) from e
    
    
    # Try C extension (requires compilation, for advanced users)
    if not impl or impl in ("c", "mariadb_c"):
        try:
            import mariadb_c.connections
            import mariadb_c.cursors
            # C extension for sync, but use pure Python for async (not yet implemented in C)
            sync_connection = mariadb_c.connections
            Cursor = mariadb_c.cursors.Cursor
            SyncCursor = mariadb_c.cursors.Cursor
            __impl__ = "c"
            
            # Try to import pure Python async implementation
            try:
                from . import async_connection as async_conn_module
                from .async_cursor import AsyncCursor as PythonAsyncCursor
                async_connection = async_conn_module
                AsyncCursor = PythonAsyncCursor
            except Exception:
                # If async import fails, set to None
                async_connection = None
                AsyncCursor = None
            return
        except Exception as e:
            handle_error("c", e)

    # Try binary wheel  (best for end users - precompiled with deps)
    if not impl or impl in ("binary", "mariadb_binary"):
        try:
            import mariadb_binary.connections
            import mariadb_binary.cursors
            # Binary wheel for sync, but use pure Python for async (not yet implemented in binary)
            sync_connection = mariadb_binary.connections
            Cursor = mariadb_binary.cursors.Cursor
            SyncCursor = mariadb_binary.cursors.Cursor
            __impl__ = "binary"
            
            # Try to import pure Python async implementation
            try:
                from . import async_connection as async_conn_module
                from .async_cursor import AsyncCursor as PythonAsyncCursor
                async_connection = async_conn_module
                AsyncCursor = PythonAsyncCursor
            except Exception:
                # If async import fails, set to None
                async_connection = None
                AsyncCursor = None
            return
        except Exception as e:
            handle_error("binary", e)

    # Fall back to pure Python implementation (slowest, but always works)
    if not impl or impl in ("python", "mariadb"):
        try:
            from . import sync_connection as sync_conn_module
            from . import async_connection as async_conn_module
            from .sync_cursor import SyncCursor as PythonSyncCursor
            from .async_cursor import AsyncCursor as PythonAsyncCursor
            sync_connection = sync_conn_module
            async_connection = async_conn_module
            SyncCursor = PythonSyncCursor
            AsyncCursor = PythonAsyncCursor
            __impl__ = "python"
            return
        except Exception as e:
            handle_error("python", e)
    
    # If we get here, nothing worked
    if impl:
        raise ImportError(f"requested mariadb implementation '{impl}' unknown")
    else:
        sattempts = "\n".join(f"- {attempt}" for attempt in attempts)
        raise ImportError(f"couldn't import any mariadb implementation:\n{sattempts}")


# Select implementation at import time
_select_implementation()
