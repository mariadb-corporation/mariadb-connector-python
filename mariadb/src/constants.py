"""
MariaDB Constants

This module provides access to all MariaDB constants in a unified way.
It imports from the constants package and exposes them at the module level.
"""

# Import all constants from the constants package
from .constants import (
    CURSOR,
    FIELD_TYPE,
    FIELD_FLAG,
    INDICATOR,
    STATUS,
    ERR,
    CAPABILITY,
    INFO,
    TPC_STATE,
    EXT_FIELD_TYPE
)

# Make constants available at module level for backward compatibility
__all__ = [
    "CURSOR", 
    "FIELD_TYPE",
    "FIELD_FLAG",
    "INDICATOR",
    "STATUS",
    "ERR",
    "CAPABILITY",
    "INFO",
    "TPC_STATE",
    "EXT_FIELD_TYPE"
]
