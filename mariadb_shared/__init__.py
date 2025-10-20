"""
Shared constants and utilities for MariaDB Connector/Python

This package contains constants, exceptions, and utilities that are shared
between the pure Python implementation and the C extension to avoid
circular import dependencies.
"""

# Import constants modules to make them available
from . import constants
from .exceptions import *  # noqa: F401,F403

__all__ = [
    # Constants module
    'constants',
    
    # Exceptions  
    'Error', 'Warning', 'InterfaceError', 'DatabaseError',
    'InternalError', 'OperationalError', 'ProgrammingError', 
    'IntegrityError', 'DataError', 'NotSupportedError', 'PoolError'
]
