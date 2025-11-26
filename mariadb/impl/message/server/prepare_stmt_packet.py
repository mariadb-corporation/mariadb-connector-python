# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Prepare Response Packet parser for MariaDB protocol

Based on MySQL/MariaDB protocol COM_STMT_PREPARE response structure.
"""

import struct
from typing import TYPE_CHECKING, List, Optional

from .column_definition_packet import ColumnDefinitionPacket

if TYPE_CHECKING:
    from ...client.context import Context

# Pre-compile struct format for faster unpacking
# Format: skip(B), statement_id(I), column_count(H), parameter_count(H), reserved(B), warning_count(H)
_STRUCT_PREPARE_RESPONSE = struct.Struct('<BIHHBH')


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
    __slots__ = (
        'statement_id',
        'column_count',
        'parameter_count',
        'warning_count',
        'sql',
        'columns',
        'parameters',
        'closed',
    )
    def __init__(
        self,
        statement_id: int,
        column_count: int,
        parameter_count: int,
        warning_count: int,
        sql: Optional[str]
    ):
        """Initialize prepare statement packet"""
        self.statement_id = statement_id
        self.column_count = column_count
        self.parameter_count = parameter_count
        self.warning_count = warning_count
        self.sql = sql
        self.columns: List[ColumnDefinitionPacket] = []
        self.parameters: List[ColumnDefinitionPacket] = []
        self.closed = False
    
    @staticmethod
    def decode(data: memoryview, context: Optional['Context'] = None, sql: Optional[str] = None) -> 'PrepareStmtPacket':
        """Decode COM_STMT_PREPARE response packet (optimized)"""
        # Unpack all fields in one operation using pre-compiled struct
        _, statement_id, column_count, parameter_count, _, warning_count = _STRUCT_PREPARE_RESPONSE.unpack_from(data, 0)
        
        # Update context if provided
        if context:
            context.warning_count = warning_count
        
        return PrepareStmtPacket(
            statement_id,
            column_count,
            parameter_count,
            warning_count,
            sql
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