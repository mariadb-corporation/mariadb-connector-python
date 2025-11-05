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
Prepare packet for MariaDB prepared statement preparation

Equivalent to the Java PreparePacket class.
"""


from ...client.context import Context
from ...client.socket.payload_writer import PayloadWriter
from ..client_message import ClientMessage


class PreparePacket(ClientMessage):
    """
    Prepare packet for SQL statement preparation (COM_STMT_PREPARE)
    
    See: https://mariadb.com/kb/en/com_stmt_prepare/
    """
    
    COM_STMT_PREPARE = 0x16
    
    def __init__(self, sql: str):
        """Initialize COM_STMT_PREPARE packet with SQL statement"""
        self.sql = sql
        
    def encode(self, context: Context) -> bytearray:
        """Encode COM_STMT_PREPARE packet with SQL statement"""
        writer = PayloadWriter()
        writer.write_byte(self.COM_STMT_PREPARE)
        writer.write_string(self.sql, 'utf-8')
        return writer.get_payload()

    def is_binary(self) -> bool:
        return True

    def type(self) -> str:
        return "COM_STMT_PREPARE"                   