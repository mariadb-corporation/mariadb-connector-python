# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from ...client.context import Context
from ...client.socket.payload_writer import PayloadWriter
from ..client_message import ClientMessage


class PreparePacket(ClientMessage):
    """
    Prepare packet for SQL statement preparation (COM_STMT_PREPARE)
    
    See: https://mariadb.com/kb/en/com_stmt_prepare/
    """
    
    COM_STMT_PREPARE = 0x16
    
    def __init__(self, sql: str):
        """Initialize COM_STMT_PREPARE packet with SQL statement"""
        self.sql = sql
        
    def encode(self, context: Context) -> bytearray:
        """Encode COM_STMT_PREPARE packet with SQL statement"""
        writer = PayloadWriter()
        writer.write_byte(self.COM_STMT_PREPARE)
        writer.write_string(self.sql, 'utf-8')
        return writer.get_payload()

    def is_binary(self) -> bool:
        return True

    def type(self) -> str:
        return "COM_STMT_PREPARE"                   