# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Statement Close packet for closing prepared statements

Sends COM_STMT_CLOSE command to the server to deallocate a prepared statement.
"""

from typing import TYPE_CHECKING
from ...client.context import Context
from ..client_message import ClientMessage
if TYPE_CHECKING:
    from ...client.socket.stream import SyncStream

class StmtClosePacket(ClientMessage):
    """
    Statement Close packet for closing prepared statements
    
    Sends COM_STMT_CLOSE command to deallocate a prepared statement on the server.
    """
    
    COM_STMT_CLOSE = 0x19
    
    def __init__(self, statement_id: int):
        """Initialize COM_STMT_CLOSE packet with statement ID"""
        self.statement_id = statement_id

    def process(self, stream: 'SyncStream', context: Context) -> None:
        """Encode COM_STMT_CLOSE packet with statement ID"""
        stream.write_byte(COM_STMT_CLOSE)
        stream.write_uint32(self.statement_id)
    
    def is_binary(self) -> bool:
        return True
    
    def type(self) -> str:
        return "COM_STMT_CLOSE"
