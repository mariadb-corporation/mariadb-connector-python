# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Prepare Response Packet parser for MariaDB protocol

Based on MySQL/MariaDB protocol COM_STMT_PREPARE response structure.
"""

from typing import TYPE_CHECKING, Optional

from .column_definition_packet import ColumnDefinitionPacket
from ...client.socket.payload_parser import PayloadParser
if TYPE_CHECKING:
    from ...client.context import Context


class PrepareStmtPacket:
    """
    COM_STMT_PREPARE Response Packet from MariaDB server
    
    Structure (OK response):
    - 1 byte: OK marker (0x00)
    - 4 bytes: statement_id (little-endian)
    - 2 bytes: column_count (little-endian)
    - 2 bytes: parameter_count (little-endian)
    - 1 byte: reserved (0x00)
    - 2 bytes: warning_count (little-endian)
    
    Note: After this packet, the server sends:
    - parameter_count × Column Definition packets (if parameter_count > 0)
    - EOF packet (if not DEPRECATE_EOF and parameter_count > 0)
    - column_count × Column Definition packets (if column_count > 0)
    - EOF packet (if not DEPRECATE_EOF and column_count > 0)
    """
    
    def __init__(
        self,
        statement_id: int,
        column_count: int,
        parameter_count: int,
        warning_count: int = 0,
        sql: str = None
    ):
        """Initialize prepare statement packet with statement ID, column count, and parameter count"""
        self.statement_id = statement_id
        self.column_count = column_count
        self.parameter_count = parameter_count
        self.warning_count = warning_count
        self.sql = sql
        self.columns: List[ColumnDefinitionPacket] = []
        self.parameters: List[ColumnDefinitionPacket] = []
        self.closed = False
    
    @staticmethod
    def decode(data: bytearray, context: Optional['Context'] = None, sql: str = None) -> 'PrepareStmtPacket':
        """Decode COM_STMT_PREPARE response packet from bytearray with optional context"""
        parser = PayloadParser(data)
        
        parser.read_byte()  # Skip OK marker (0x00)
        statement_id = parser.read_int32()
        column_count = parser.read_int16()
        parameter_count = parser.read_int16()
        parser.read_byte()  # Skip reserved byte (0x00)
        warning_count = parser.read_int16()
        
        # Update context if provided
        if context:
            context.warning_count = warning_count
        
        return PrepareStmtPacket(
            statement_id=statement_id,
            column_count=column_count,
            parameter_count=parameter_count,
            warning_count=warning_count,
            sql=sql
        )
    
    def __repr__(self) -> str:
        return (f"PrepareStmtPacket(statement_id={self.statement_id}, "
                f"column_count={self.column_count}, "
                f"parameter_count={self.parameter_count}, "
                f"warning_count={self.warning_count})")
    
    def __str__(self) -> str:
        return (f"PREPARE OK: stmt_id={self.statement_id}, "
                f"params={self.parameter_count}, "
                f"cols={self.column_count}, "
                f"warnings={self.warning_count}")
    
    def is_closed(self) -> bool:
        return self.closed

    def close(self) -> None:
        self.closed = True   