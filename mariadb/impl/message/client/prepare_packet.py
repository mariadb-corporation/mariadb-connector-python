# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from typing import TYPE_CHECKING
from ...client.context import Context
from ..client_message import ClientMessage
if TYPE_CHECKING:
    from ...client.socket.stream import SyncStream

class PreparePacket(ClientMessage):
    """
    Prepare packet for SQL statement preparation (COM_STMT_PREPARE)
    
    See: https://mariadb.com/kb/en/com_stmt_prepare/
    """
    
    COM_STMT_PREPARE = 0x16
    
    def __init__(self, sql: str):
        """Initialize COM_STMT_PREPARE packet with SQL statement"""
        self.sql = sql
        
    def process(self, stream: 'SyncStream', context: Context) -> None:
        stream.write_byte(self.COM_STMT_PREPARE)
        stream.write_string(self.sql, 'utf-8')

    def is_binary(self) -> bool:
        return True

    def type(self) -> str:
        return "COM_STMT_PREPARE"                   