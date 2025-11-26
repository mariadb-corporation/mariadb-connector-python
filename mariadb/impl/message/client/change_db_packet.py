# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from ...client.context import Context
from ..client_message import ClientMessage

class ChangeDbPacket(ClientMessage):
    """
    Change database packet implementation
    
    Sends COM_INIT_DB command to change the current database.
    See https://mariadb.com/kb/en/com_init_db/ protocol
    """
    
    def __init__(self, database: str):
        """Initialize COM_INIT_DB packet with database name"""
        self.database = database
        
    def payload(self, context: Context) -> bytes:
        return b'\0\0\0\0\2' + self.database.encode('utf-8')

    def is_binary(self) -> bool:
        return False

    def type(self) -> str:
        return "COM_INIT_DB"