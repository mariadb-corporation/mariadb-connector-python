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

from typing import Any
from ..client_message import ClientMessage


class ChangeDbPacket(ClientMessage):
    """
    Change database packet implementation
    
    Sends COM_INIT_DB command to change the current database.
    Equivalent to the Java ChangeDbPacket class.
    """
    
    def __init__(self, database: str):
        """
        Constructor to encode COM_INIT_DB packet
        
        Args:
            database: Database name to change to
        """
        self.database = database
    
    def encode(self, writer: Any, context: Any) -> None:
        """
        Encode COM_INIT_DB packet using new payload-based approach
        
        Args:
            writer: Packet writer
            context: Connection context
        """
        # Start payload mode
        writer.start_payload()
        
        # COM_INIT_DB command byte is 0x02
        writer.write_byte(0x02)
        
        # Write database name as string (null-terminated)
        writer.write_string(self.database)
        
        # Send packet with automatic header and chunking
        writer.send_payload("COM_INIT_DB")
    