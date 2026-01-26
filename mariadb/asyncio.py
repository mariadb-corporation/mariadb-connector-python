# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Async DBAPI interface for mariadb-connector-python

This module provides a DBAPI-compatible async interface that SQLAlchemy
can use with create_async_engine().

Usage with SQLAlchemy:
    from sqlalchemy.ext.asyncio import create_async_engine
    
    engine = create_async_engine(
        "mariadb+mariadbconnector_async://user:pass@host/db"
    )
"""

# Import exception classes from main module
from mariadb_shared.exceptions import (
    Error,
    Warning,
    InterfaceError,
    DatabaseError,
    InternalError,
    NotSupportedError,
    OperationalError,
    ProgrammingError,
    IntegrityError,
    DataError
)

# DBAPI 2.0 attributes
apilevel = "2.0"
threadsafety = 1  # Threads may share the module, but not connections
paramstyle = "qmark"


async def connect(*args, **kwargs):
    """
    Create an async database connection.
    
    This is the async equivalent of mariadb.connect() that SQLAlchemy expects.
    Uses the same implementation selection logic as mariadb.asyncConnect(),
    respecting the MARIADB_PYTHON_CONNECTOR environment variable.
    
    Args:
        *args, **kwargs: Connection parameters (host, user, password, database, etc.)
        
    Returns:
        AsyncConnection instance
    """
    # Import mariadb module to use its asyncConnect function
    # This ensures we use the same implementation selection logic
    import mariadb
    
    # Use the standard asyncConnect function which handles:
    # - MARIADB_PYTHON_CONNECTOR environment variable
    # - Implementation selection (C extension vs pure Python)
    # - Proper connection and initialization
    return await mariadb.asyncConnect(*args, **kwargs)


# For compatibility with some tools that check __all__
__all__ = [
    'connect',
    'Error',
    'Warning',
    'InterfaceError',
    'DatabaseError',
    'InternalError',
    'NotSupportedError',
    'OperationalError',
    'ProgrammingError',
    'IntegrityError',
    'DataError',
    'apilevel',
    'threadsafety',
    'paramstyle',
]
