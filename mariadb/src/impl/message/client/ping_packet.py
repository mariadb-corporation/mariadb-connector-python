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
Ping packet for MariaDB connection testing

Equivalent to the Java PingPacket class.
"""

from typing import Any
from ..client_message import ClientMessage


class PingPacket(ClientMessage):
    """
    Ping packet for connection testing
    
    Equivalent to the Java PingPacket class.
    """
    
    COM_PING = 0x0E
    
    def __init__(self):
        """Initialize ping packet"""
        pass
        
    def encode(self, writer: Any, context: Any) -> None:
        """
        Encode ping packet using payload-based approach
        
        Args:
            writer: Packet writer
            context: Connection context
            
        Raises:
            IOError: If encoding fails
        """
        # Start payload mode
        writer.start_payload()
        
        # Command type (only byte in ping packet)
        writer.write_byte(self.COM_PING)
        
        # Send packet with automatic header and chunking
        writer.send_payload("COM_PING")
    
    def description(self) -> str:
        """Get message description"""
        return "PingPacket()"
    
    def can_be_redone(self) -> bool:
        """Ping can always be redone"""
        return True
