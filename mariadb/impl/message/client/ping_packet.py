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

from ...client.context import Context

from ..client_message import ClientMessage
from ...client.socket.payload_writer import PayloadWriter


class PingPacket(ClientMessage):
    """
    Ping packet for connection testing
    
    Equivalent to the Java PingPacket class.
    """
    
    COM_PING = 0x0E
    
    def __init__(self):
        """Initialize ping packet"""
        pass
        
    def encode(self, context: Context) -> bytearray:
        """
        Encode ping packet using payload-based approach
        
        Args:
            stream: Stream to send payload through
            context: Connection context
            
        Raises:
            IOError: If encoding fails
        """
        return bytearray([PingPacket.COM_PING])
    
    def is_binary(self) -> bool:
        return False

    def type(self) -> str:
        return "COM_PING"                   