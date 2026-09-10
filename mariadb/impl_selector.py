"""
MariaDB implementation selector

This module handles the selection between the pure Python and the native
(C extension / binary wheel) implementations. The selected classes are
exposed typed against the shared interfaces of ``mariadb_shared``, which
every implementation derives from, so callers never deal with ``Any``.
"""

import os
import sys
from typing import cast

from mariadb_shared.async_connection_common import AsyncConnectionCommon
from mariadb_shared.async_cursor_common import AsyncCursorCommon
from mariadb_shared.sync_connection_common import SyncConnectionCommon
from mariadb_shared.sync_cursor_common import SyncCursorCommon


__impl__: str = ""
SyncConnection: type[SyncConnectionCommon]
AsyncConnection: type[AsyncConnectionCommon]
SyncCursor: type[SyncCursorCommon]
AsyncCursor: type[AsyncCursorCommon]
# Version of the underlying MariaDB Connector/C library; None for the pure
# Python implementation, which has no such dependency.
mariadbapi_version: str | None = None


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
    global __impl__, SyncConnection, AsyncConnection, SyncCursor, AsyncCursor, mariadbapi_version

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

    def python_async() -> tuple[type[AsyncConnectionCommon], type[AsyncCursorCommon]]:
        """The pure Python async implementation, also the fallback of the
        native implementations when they have no async support of their own."""
        from .async_connection import AsyncConnection as PythonAsyncConnection
        from .async_cursor import AsyncCursor as PythonAsyncCursor
        return PythonAsyncConnection, PythonAsyncCursor

    # Try C extension (requires compilation, for advanced users)
    if not impl or impl in ("c", "mariadb_c"):
        try:
            import mariadb_c.connections
            import mariadb_c.cursors
            from mariadb_c._mariadb import mariadbapi_version as c_api_version
            SyncConnection = mariadb_c.connections.Connection
            SyncCursor = mariadb_c.cursors.Cursor
            mariadbapi_version = c_api_version
            # Native async implementation first, pure Python async otherwise
            try:
                import mariadb_c.async_connections
                import mariadb_c.async_cursors
                AsyncConnection = mariadb_c.async_connections.AsyncConnection
                AsyncCursor = mariadb_c.async_cursors.AsyncCursor
            except Exception:
                AsyncConnection, AsyncCursor = python_async()
            __impl__ = "c"
            return
        except Exception as e:
            handle_error("c", e)

    # Try binary wheel  (best for end users - precompiled with deps)
    if not impl or impl in ("binary", "mariadb_binary"):
        try:
            import mariadb_binary.connections # pyright: ignore[reportMissingImports]
            import mariadb_binary.cursors # pyright: ignore[reportMissingImports]
            SyncConnection = cast(type[SyncConnectionCommon], mariadb_binary.connections.Connection) # pyright: ignore[reportUnknownMemberType]
            SyncCursor = cast(type[SyncCursorCommon], mariadb_binary.cursors.Cursor) # pyright: ignore[reportUnknownMemberType]
            mariadbapi_version = cast(str | None, getattr(mariadb_binary.connections, "mariadbapi_version", None)) # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
            # Native async implementation first, pure Python async otherwise
            try:
                import mariadb_binary.async_connections # pyright: ignore[reportMissingImports]
                import mariadb_binary.async_cursors # pyright: ignore[reportMissingImports]
                AsyncConnection = cast(type[AsyncConnectionCommon], mariadb_binary.async_connections.AsyncConnection) # pyright: ignore[reportUnknownMemberType]
                AsyncCursor = cast(type[AsyncCursorCommon], mariadb_binary.async_cursors.AsyncCursor) # pyright: ignore[reportUnknownMemberType]
            except Exception:
                AsyncConnection, AsyncCursor = python_async()
            __impl__ = "binary"
            return
        except Exception as e:
            handle_error("binary", e)

    # Fall back to pure Python implementation (slowest, but always works)
    if not impl or impl in ("python", "mariadb"):
        try:
            from .sync_connection import SyncConnection as PythonSyncConnection
            from .sync_cursor import SyncCursor as PythonSyncCursor
            SyncConnection = PythonSyncConnection
            SyncCursor = PythonSyncCursor
            AsyncConnection, AsyncCursor = python_async()
            mariadbapi_version = None
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
