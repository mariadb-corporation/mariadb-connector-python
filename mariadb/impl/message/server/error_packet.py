# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Error Packet parser for MariaDB protocol

Based on MySQL/MariaDB protocol error packet structure.
"""

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ...client.context import Context
    from ...client.exception_factory import ExceptionFactory
from ..payload_reader import PayloadReader

# Pre-compute constants
_HASH_MARKER = 0x23  # '#'
_DEFAULT_SQL_STATE = "HY000"


class ErrorPacket:
    """
    Error Packet from MariaDB server
    
    Structure:
    - 1 byte: Error marker (0xFF)
    - 2 bytes: error_code (little-endian)
    - [optional] 1 byte: '#' marker (0x23) for SQL state
    - [optional] 5 bytes: sql_state (if '#' marker present)
    - remaining bytes: error_message (UTF-8 string)
    
    Note: Pre-4.1 format doesn't include SQL state marker and state.
    """
    __slots__ = (
        'error_code',
        'sql_state',
        'error_message',
    )
    
    def __init__(
        self,
        error_code: int,
        sql_state: str,
        error_message: str,
    ):
        """Initialize error packet with error code, SQL state, and message"""
        self.error_code = error_code
        self.sql_state = sql_state
        self.error_message = error_message
    
    def is_output_parameters(self) -> bool:
        """Check if completion has output parameters"""
        return False

    @staticmethod
    def decode(data: memoryview, context: Optional['Context'] = None) -> 'ErrorPacket':
        """Decode error packet from bytearray with optional context"""
        parser = PayloadReader(data)
        parser.skip(1)  # Skip error marker (0xFF) - skip is faster than read_byte if we don't use value
        error_code = parser.read_uint16()
        
        # Fast path: check for SQL state marker
        if parser.has_remaining() and parser.get_byte() == _HASH_MARKER:
            parser.skip(1)  # Skip '#' marker
            
            # SQL state (5 bytes)
            if parser.remaining_bytes() >= 5:
                sql_state = parser.read_bytes(5).decode('ascii')
            else:
                raise IOError("Invalid error packet: SQL state truncated")
        else:
            sql_state = _DEFAULT_SQL_STATE
        
        # Decode error message - remove unnecessary bytes() wrapper if read_remaining returns bytes
        error_message = parser.read_remaining().decode('utf-8', errors='replace')
        
        return ErrorPacket(error_code, sql_state, error_message)

    def toError(self, exception_factory: 'ExceptionFactory', sql: Optional[str] = None):
        """Convert to exception"""
        return exception_factory.create_exception(
            self.error_message, 
            self.sql_state, 
            self.error_code, 
            sql
        )
    
    def __repr__(self) -> str:
        """String representation for debugging"""
        return (f"ErrorPacket(error_code={self.error_code}, "
                f"sql_state='{self.sql_state}', "
                f"error_message='{self.error_message}')")
    
    def __str__(self) -> str:
        """Human-readable string representation"""
        return f"[{self.error_code}] ({self.sql_state}): {self.error_message}"