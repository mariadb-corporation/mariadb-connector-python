"""
MariaDB exception classes

This module re-exports exceptions from mariadb_shared to ensure
all code uses the same exception instances.
"""

# Re-export all exceptions from shared package
from mariadb_shared.exceptions import (
    Error,
    Warning,
    InterfaceError,
    DatabaseError,
    InternalError,
    OperationalError,
    ProgrammingError,
    IntegrityError,
    DataError,
    NotSupportedError,
    PoolError
)

__all__ = [
    'Error',
    'Warning',
    'InterfaceError',
    'DatabaseError',
    'InternalError',
    'OperationalError',
    'ProgrammingError',
    'IntegrityError',
    'DataError',
    'NotSupportedError',
    'PoolError'
]
