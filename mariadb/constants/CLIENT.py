"""
CLIENT constants module - alias for CAPABILITY constants

This module provides CLIENT.FOUND_ROWS for SQLAlchemy compatibility.
The C extension exposes these as CLIENT constants, but they're actually
CAPABILITY flags in the protocol.
"""

from mariadb_shared.constants.CAPABILITY import *

# Make all CAPABILITY constants available as CLIENT constants
__all__ = [name for name in dir() if not name.startswith('_')]
