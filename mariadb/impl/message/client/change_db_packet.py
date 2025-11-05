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
Change Database Packet (COM_INIT_DB)

Equivalent to the Java ChangeDbPacket class.
See https://mariadb.com/kb/en/com_init_db/ protocol
"""

from ...client.context import Context

from ..client_message import ClientMessage
from ...client.socket.payload_writer import PayloadWriter


class ChangeDbPacket(ClientMessage):
    """
    Change database packet implementation
    
    Sends COM_INIT_DB command to change the current database.
    Equivalent to the Java ChangeDbPacket class.
    """

    COM_INIT_DB = 0x02
    
    def __init__(self, database: str):
        """Initialize COM_INIT_DB packet with database name"""
        self.database = database
    
    def encode(self, context: Context) -> bytearray:
        """Encode COM_INIT_DB packet with database name"""
        writer = PayloadWriter()
        writer.write_byte(self.COM_INIT_DB)
        writer.write_string(self.database)
        return writer.get_payload()
    
    def is_binary(self) -> bool:
        return False

    def type(self) -> str:
        return "COM_INIT_DB"