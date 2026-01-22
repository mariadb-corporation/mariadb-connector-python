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

# CLIENT is an alias for CAPABILITY for backward compatibility with C extension
# SQLAlchemy expects CLIENT.FOUND_ROWS
CLIENT = CAPABILITY

# Make constants available at module level for backward compatibility
__all__ = [
    "CURSOR", 
    "FIELD_TYPE",
    "FIELD_FLAG",
    "INDICATOR",
    "STATUS",
    "ERR",
    "CAPABILITY",
    "CLIENT",
    "INFO",
    "TPC_STATE",
    "EXT_FIELD_TYPE"
]
