"""
MariaDB Constants

This module provides access to all MariaDB constants in a unified way.
It imports from the constants package and exposes them at the module level.
"""

# Import all constants from the constants package and expose them directly
from .constants.CURSOR import *
from .constants.FIELD_TYPE import *
from .constants.FIELD_FLAG import *
from .constants.INDICATOR import *
from .constants.STATUS import *
from .constants.ERR import *
from .constants.CAPABILITY import *
from .constants.INFO import *
from .constants.TPC_STATE import *
from .constants.EXT_FIELD_TYPE import *

# Also import the modules themselves for compatibility
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
