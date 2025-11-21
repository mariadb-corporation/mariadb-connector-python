# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from ...client.context import Context

from ..client_message import ClientMessage
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ...client.socket.write_stream import BaseWriteStream

class ChangeDbPacket(ClientMessage):
    """
    Change database packet implementation
    
    Sends COM_INIT_DB command to change the current database.
    See https://mariadb.com/kb/en/com_init_db/ protocol
    """

    COM_INIT_DB = 0x02
    
    def __init__(self, database: str):
        """Initialize COM_INIT_DB packet with database name"""
        self.database = database
        
    def process(self, stream: 'BaseWriteStream', context: Context) -> None:
        stream.write_byte(self.COM_INIT_DB)
        stream.write_string(self.database)

    def is_binary(self) -> bool:
        return False

    def type(self) -> str:
        return "COM_INIT_DB"