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
