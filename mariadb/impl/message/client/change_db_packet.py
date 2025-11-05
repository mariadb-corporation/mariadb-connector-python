# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

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