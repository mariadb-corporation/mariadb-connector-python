# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from ...client.context import Context
from ..client_message import ClientMessage

class PreparePacket(ClientMessage):
    """
    Prepare packet for SQL statement preparation (COM_STMT_PREPARE)
    
    See: https://mariadb.com/kb/en/com_stmt_prepare/
    """
    __slots__ = ('sql',)
    
    COM_STMT_PREPARE = 0x16
    
    def __init__(self, sql: str):
        """Initialize COM_STMT_PREPARE packet with SQL statement"""
        self.sql = sql
        
    def payload(self, context: Context) -> bytearray:
        result = bytearray(b'\0\0\0\0\x16')
        result.extend(self.sql.encode('utf-8'))
        return result

    def is_binary(self) -> bool:
        return True

    def type(self) -> str:
        return "COM_STMT_PREPARE"                   