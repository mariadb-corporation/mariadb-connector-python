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
Quit packet for graceful connection closure

Sends COM_QUIT command to the server before closing the connection.
"""

from ...client.context import Context

from ..client_message import ClientMessage


class QuitPacket(ClientMessage):
    """
    Quit packet for graceful connection closure
    
    Sends COM_QUIT command to notify the server that the client is closing.
    """
    
    COM_QUIT = 0x01
    
    def __init__(self):
        """Initialize COM_QUIT packet"""
        pass
        
    def encode(self, context: Context) -> bytearray:
        """Encode COM_QUIT packet"""
        return bytearray([self.COM_QUIT])
    
    def is_binary(self) -> bool:
        return False
    
    def type(self) -> str:
        return "COM_QUIT"
