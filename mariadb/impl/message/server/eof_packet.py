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
EOF Packet parser for MariaDB protocol

Based on MySQL/MariaDB protocol EOF packet structure.
"""

from typing import TYPE_CHECKING
from ...completion import Completion
from ...client.socket.payload_parser import PayloadParser
if TYPE_CHECKING:
    from ...client.context import Context

from mariadb_shared import constants

class EofPacket(Completion):
    """
    EOF Packet from MariaDB server
    
    Structure (Traditional EOF packet - when DEPRECATE_EOF is not enabled):
    - 1 byte: EOF marker (0xFE)
    - 2 bytes: warning_count (little-endian)
    - 2 bytes: server_status (little-endian)
    
    Note: When DEPRECATE_EOF capability is enabled, the server sends
    an OK packet with 0xFE header instead of a traditional EOF packet.
    In that case, use OkPacket.decode() instead.
    """
    
    def __init__(
        self,
        warning_count: int = 0,
        server_status: int = 0,
        is_output_parameters: bool = False
    ):
        """
        Initialize EOF packet
        
        Args:
            warning_count: Number of warnings
            server_status: Server status flags
            is_output_parameters: Whether this marks output parameters
        """
        # Initialize parent Completion
        super().__init__(
            affected_rows=0,
            insert_id=0,
            warning_count=warning_count,
            is_output_parameters=is_output_parameters
        )
        
        # EofPacket-specific fields
        self.server_status = server_status
    
    def is_output_parameters(self) -> bool:
        """Check if completion has output parameters"""
        return (self.server_status & constants.STATUS.PS_OUT_PARAMS) != 0

    @staticmethod
    def decode(data: bytearray, context: 'Context') -> 'EofPacket':
        """
        Decode EOF packet from bytearray
        
        Args:
            data: Packet data (including EOF marker)
            context: Connection context
            
        Returns:
            EofPacket instance
            
        Raises:
            IOError: If packet parsing fails
            
        Note:
            This method should only be used for traditional EOF packets
            (when DEPRECATE_EOF is not enabled). When DEPRECATE_EOF is
            enabled, the server sends OK packets with 0xFE header instead.
        """
        parser = PayloadParser(data)
        parser.read_byte() # Skip ERR marker
        warning_count = parser.read_int16()
        server_status = parser.read_int16()
        
        # Update context with server status
        if context:
            context.server_status = server_status
            context.warning_count = warning_count
        
        # Check if this marks output parameters (PS_OUT_PARAMS flag)
        from mariadb_shared.constants import STATUS
        is_output_parameters = (server_status & STATUS.PS_OUT_PARAMS) != 0
        
        return EofPacket(
            warning_count=warning_count,
            server_status=server_status,
            is_output_parameters=is_output_parameters
        )
    
    def __repr__(self) -> str:
        return (f"EofPacket(warning_count={self.warning_count}, "
                f"server_status=0x{self.server_status:04X}, "
                f"is_output_parameters={self.is_output_parameters})")
    
    def __str__(self) -> str:
        return f"EOF: {self.warning_count} warnings, status=0x{self.server_status:04X}"
