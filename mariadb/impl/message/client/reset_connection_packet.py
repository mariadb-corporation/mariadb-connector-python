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
Reset connection packet for MariaDB connection reset

Resets the connection state without re-authenticating.
"""

from ...client.context import Context

from ..client_message import ClientMessage
from ...client.socket.payload_writer import PayloadWriter


class ResetConnectionPacket(ClientMessage):
    """
    Reset connection packet
    
    Resets the current connection and clears session state and pending results.
    This is more efficient than reconnecting as it doesn't require re-authentication.
    """
    
    COM_RESET_CONNECTION = 0x1F
    
    def __init__(self):
        """Initialize reset connection packet"""
        pass
        
    def encode(self, context: Context) -> bytearray:
        """
        Encode reset connection packet
        
        Args:
            context: Connection context
            
        Raises:
            IOError: If encoding fails
        """
        # Build payload
        return bytearray([self.COM_RESET_CONNECTION])
    

    def is_binary(self) -> bool:
        return False
    
    def type(self) -> str:
        return "COM_RESET_CONNECTION"