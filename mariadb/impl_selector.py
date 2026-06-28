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
# These hold the selected implementation *module* (e.g. mariadb_c.connections),
# not a connection instance — the class lives at e.g. sync_connection.SyncConnection.
sync_connection: Any = None
async_connection: Any = None
Cursor: Type[Any] | None = None
SyncCursor: Type[Any] | None = None
AsyncCursor: Type[Any] | None = None


def _select_implementation() -> None:
    """
    Select the best MariaDB implementation available.
    
    Uses MARIADB_PYTHON_CONNECTOR environment variable:
    - 'c' or 'mariadb_c': Force C extension (tries C async, falls back to Python async)
    - 'binary' or 'mariadb_binary': Force binary wheel (tries binary async, falls back to Python async)
    - 'python' or 'mariadb': Force pure Python for both sync and async
    - Not set: Try binary first, then C extension, fallback to pure Python
    
    Both C extension and binary wheel will try their native async implementations first,
    with graceful fallback to pure Python async if not available.
    
    Note: PyPy automatically uses pure Python implementation due to cpyext stack overflow
    issues with C extensions in PyPy 3.11+.
    """
    global __impl__, sync_connection, async_connection, Cursor, SyncCursor, AsyncCursor
    
    impl = os.environ.get("MARIADB_PYTHON_CONNECTOR", "").strip().lower()
    attempts: list[str] = []
    
    # PyPy 3.11+ has cpyext stack overflow issues with C extension async operations
    # Automatically use pure Python implementation on PyPy unless explicitly overridden
    is_pypy = hasattr(sys, 'pypy_version_info')
    if is_pypy and not impl:
        impl = "python"
    
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
            # C extension for sync
            sync_connection = mariadb_c.connections # pyright: ignore[reportAssignmentType]
            Cursor = mariadb_c.cursors.Cursor
            SyncCursor = mariadb_c.cursors.Cursor
            __impl__ = "c"
            
            # Try to import C extension async implementation first
            try:
                import mariadb_c.async_connections
                import mariadb_c.async_cursors
                async_connection = mariadb_c.async_connections
                AsyncCursor = mariadb_c.async_cursors.AsyncCursor
            except Exception:
                # Fall back to pure Python async implementation
                try:
                    from . import async_connection as async_conn_module
                    from .async_cursor import AsyncCursor as PythonAsyncCursor
                    async_connection = async_conn_module
                    AsyncCursor = PythonAsyncCursor
                except Exception:
                    # If both fail, set to None
                    async_connection = None
                    AsyncCursor = None
            return
        except Exception as e:
            handle_error("c", e)

    # Try binary wheel  (best for end users - precompiled with deps)
    if not impl or impl in ("binary", "mariadb_binary"):
        try:
            import mariadb_binary.connections # pyright: ignore[reportMissingImports]
            import mariadb_binary.cursors # pyright: ignore[reportMissingImports]
            # Binary wheel for sync
            sync_connection = mariadb_binary.connections # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
            Cursor = mariadb_binary.cursors.Cursor # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
            SyncCursor = mariadb_binary.cursors.Cursor # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
            __impl__ = "binary"
            
            # Try to import binary async implementation first
            try:
                import mariadb_binary.async_connections # pyright: ignore[reportMissingImports]
                import mariadb_binary.async_cursors # pyright: ignore[reportMissingImports]
                async_connection = mariadb_binary.async_connections # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
                AsyncCursor = mariadb_binary.async_cursors.AsyncCursor # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
            except Exception:
                # Fall back to pure Python async implementation
                try:
                    from . import async_connection as async_conn_module
                    from .async_cursor import AsyncCursor as PythonAsyncCursor
                    async_connection = async_conn_module
                    AsyncCursor = PythonAsyncCursor
                except Exception:
                    # If both fail, set to None
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
