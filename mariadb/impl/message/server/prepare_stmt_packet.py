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
Prepare Response Packet parser for MariaDB protocol

Based on MySQL/MariaDB protocol COM_STMT_PREPARE response structure.
"""

from typing import TYPE_CHECKING, Optional
from ...client.socket.payload_parser import PayloadParser
if TYPE_CHECKING:
    from ...client.context import Context


class PrepareStmtPacket:
    """
    COM_STMT_PREPARE Response Packet from MariaDB server
    
    Structure (OK response):
    - 1 byte: OK marker (0x00)
    - 4 bytes: statement_id (little-endian)
    - 2 bytes: column_count (little-endian)
    - 2 bytes: parameter_count (little-endian)
    - 1 byte: reserved (0x00)
    - 2 bytes: warning_count (little-endian)
    
    Note: After this packet, the server sends:
    - parameter_count × Column Definition packets (if parameter_count > 0)
    - EOF packet (if not DEPRECATE_EOF and parameter_count > 0)
    - column_count × Column Definition packets (if column_count > 0)
    - EOF packet (if not DEPRECATE_EOF and column_count > 0)
    """
    
    def __init__(
        self,
        statement_id: int,
        column_count: int,
        parameter_count: int,
        warning_count: int = 0
    ):
        """
        Initialize Prepare Response packet
        
        Args:
            statement_id: Server-assigned statement ID
            column_count: Number of columns in result set
            parameter_count: Number of parameters in prepared statement
            warning_count: Number of warnings
        """
        self.statement_id = statement_id
        self.column_count = column_count
        self.parameter_count = parameter_count
        self.warning_count = warning_count
        self.columns = []
        self.parameters = []
        self.closed = False
    
    @staticmethod
    def decode(data: bytearray, context: Optional['Context'] = None) -> 'PrepareStmtPacket':
        """
        Decode COM_STMT_PREPARE response packet from bytearray
        
        Args:
            data: Packet data (including OK marker)
            context: Connection context (optional)
            
        Returns:
            PrepareStmtPacket instance
            
        Raises:
            IOError: If packet parsing fails
        """
        parser = PayloadParser(data)
        
        parser.read_byte()  # Skip OK marker (0x00)
        statement_id = parser.read_int32()
        column_count = parser.read_int16()
        parameter_count = parser.read_int16()
        parser.read_byte()  # Skip reserved byte (0x00)
        warning_count = parser.read_int16()
        
        # Update context if provided
        if context:
            context.warning_count = warning_count
        
        return PrepareStmtPacket(
            statement_id=statement_id,
            column_count=column_count,
            parameter_count=parameter_count,
            warning_count=warning_count
        )
    
    def __repr__(self) -> str:
        return (f"PrepareStmtPacket(statement_id={self.statement_id}, "
                f"column_count={self.column_count}, "
                f"parameter_count={self.parameter_count}, "
                f"warning_count={self.warning_count})")
    
    def __str__(self) -> str:
        return (f"PREPARE OK: stmt_id={self.statement_id}, "
                f"params={self.parameter_count}, "
                f"cols={self.column_count}, "
                f"warnings={self.warning_count}")
    
    def is_closed(self) -> bool:
        return self.closed

    def close(self) -> None:
        self.closed = True   