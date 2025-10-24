"""
MariaDB implementation selector

This module handles the selection between pure Python and C extension
implementations, similar to how psycopg handles implementation selection
in its pq module.
"""

import os
import sys
from typing import Any, Type


# Global variables to store the selected implementation
__impl__: str = ""
Connection: Type[Any] = None
Cursor: Type[Any] = None


def _select_implementation() -> None:
    """
    Select the best MariaDB implementation available.
    
    Uses MARIADB_PYTHON_CONNECTOR environment variable:
    - 'mariadb_c' or 'c': Force C extension
    - 'mariadb' or 'python': Force pure Python  
    - Not set: Try C extension first, fallback to pure Python
    """
    global __impl__, Connection, Cursor
    
    impl = os.environ.get("MARIADB_PYTHON_CONNECTOR", "").lower()
    attempts = []
    
    def handle_error(name: str, e: Exception) -> None:
        if not impl:
            msg = f"couldn't import mariadb '{name}' implementation: {e}"
            attempts.append(msg)
        else:
            msg = f"couldn't import requested mariadb '{name}' implementation: {e}"
            raise ImportError(msg) from e
    
    # Try C extension first (best performance)
    if not impl or impl in ("c", "mariadb_c"):
        try:
            # Try installed package first (mariadb_c maps to src/ via pyproject.toml)
            try:
                import mariadb_c.connections
                import mariadb_c.cursors
                Connection = mariadb_c.connections.Connection
                Cursor = mariadb_c.cursors.Cursor
            except ModuleNotFoundError:
                # Fallback for development mode (not installed)
                import mariadb_c.src.connections
                import mariadb_c.src.cursors
                Connection = mariadb_c.src.connections.Connection
                Cursor = mariadb_c.src.cursors.Cursor
            __impl__ = "c"
            return
        except Exception as e:
            handle_error("c", e)
    
    # Fall back to pure Python implementation
    if not impl or impl in ("python", "mariadb"):
        try:
            from .connection import Connection as PythonConnection
            from .cursor import Cursor as PythonCursor
            Connection = PythonConnection
            Cursor = PythonCursor
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


# Select implementation at import time (like psycopg does)
_select_implementation()
