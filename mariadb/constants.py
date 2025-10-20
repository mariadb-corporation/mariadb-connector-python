"""
MariaDB Constants

This module re-exports constants from mariadb_shared for backward compatibility.
"""

# Re-export constants from shared package
from mariadb_shared.constants import (
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
