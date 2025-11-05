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
Statement Close packet for closing prepared statements

Sends COM_STMT_CLOSE command to the server to deallocate a prepared statement.
"""

import struct
from ...client.context import Context
from ..client_message import ClientMessage


class StmtClosePacket(ClientMessage):
    """
    Statement Close packet for closing prepared statements
    
    Sends COM_STMT_CLOSE command to deallocate a prepared statement on the server.
    """
    
    COM_STMT_CLOSE = 0x19
    
    def __init__(self, statement_id: int):
        """Initialize COM_STMT_CLOSE packet with statement ID"""
        self.statement_id = statement_id
        
    def encode(self, context: Context) -> bytearray:
        """Encode COM_STMT_CLOSE packet with statement ID"""
        # COM_STMT_CLOSE (0x19) + statement_id (4 bytes, little-endian)
        return bytearray(struct.pack('<BI', self.COM_STMT_CLOSE, self.statement_id))
    
    def is_binary(self) -> bool:
        return True
    
    def type(self) -> str:
        return "COM_STMT_CLOSE"
