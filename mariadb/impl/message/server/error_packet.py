#
# Copyright (C) 2020-2021 Georg Richter and MariaDB Corporation AB

# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Library General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.

# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Library General Public License for more details.

# You should have received a copy of the GNU Library General Public
# License along with this library; if not see <http://www.gnu.org/licenses>
# or write to the Free Software Foundation, Inc.,
# 51 Franklin St., Fifth Floor, Boston, MA 02110, USA
#

"""
Error Packet parser for MariaDB protocol

Based on MySQL/MariaDB protocol error packet structure.
"""

import struct
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ...client.context import Context
    from ...exception_factory import ExceptionFactory
from ...client.socket.payload_parser import PayloadParser


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
    
    def __init__(
        self,
        error_code: int,
        sql_state: str = "HY000",
        error_message: str = "",
    ):
        """Initialize error packet with error code, SQL state, and message"""
        self.error_code = error_code
        self.sql_state = sql_state
        self.error_message = error_message
    
    def is_output_parameters(self) -> bool:
        """Check if completion has output parameters"""
        return False

    @staticmethod
    def decode(data: bytearray, context: Optional['Context'] = None) -> 'ErrorPacket':
        """Decode error packet from bytearray with optional context"""
        parser = PayloadParser(data)
        parser.read_byte()
        error_code = parser.read_int16()
        sql_state = "HY000"  # Default SQL state
        
        # Check for SQL state marker '#' (0x23)
        if parser.has_remaining() and parser.get_byte() == 0x23:  # '#' symbol
            parser.read_byte()  # Skip '#' marker
            # SQL state (5 bytes)
            if parser.remaining_bytes() >= 5:
                sql_state = parser.read_bytes(5).decode('ascii')
            else:
                raise IOError("Invalid error packet: SQL state truncated")
        
        error_message = parser.read_remaining().decode('utf-8', errors='replace')
        
        return ErrorPacket(
            error_code=error_code,
            sql_state=sql_state,
            error_message=error_message
        )


    def toError(self, exception_factory: 'ExceptionFactory', sql: Optional[str] = None):
        return exception_factory.create_exception(self.error_message, self.sql_state, self.error_code, sql)
    
    def __repr__(self) -> str:
        return (f"ErrorPacket(error_code={self.error_code}, "
                f"sql_state='{self.sql_state}', "
                f"error_message='{self.error_message}')")
    
    def __str__(self) -> str:
        return f"[{self.error_code}] ({self.sql_state}): {self.error_message}"
