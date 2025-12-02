# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

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
    __slots__ = ('statement_id',)
    
    COM_STMT_CLOSE = 0x19
    
    def __init__(self, statement_id: int):
        """Initialize COM_STMT_CLOSE packet with statement ID"""
        self.statement_id = statement_id

    def payload(self, context: Context) -> bytearray:
        result = bytearray(b'\0\0\0\0\x19')
        result.extend(struct.pack('<I', self.statement_id))
        return result
    
    def is_binary(self) -> bool:
        return True
    
    def type(self) -> str:
        return "COM_STMT_CLOSE"
