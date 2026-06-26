# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from __future__ import annotations

"""
Query packet for SQL execution with parameter substitution.

This module provides proper parsing of SQL statements to identify placeholders
while correctly handling:
- String literals (single and double quotes)
- Comments (/* */, --, #, //)
- Backtick identifiers
- Escape sequences
"""

from typing import TYPE_CHECKING, Any

from ...client.context import Context
from ..client_message import ClientMessage

if TYPE_CHECKING:
    from ..payload_writer import PayloadWriter
from mariadb_shared.text_protocol import (
    substitute_params,
    normalize_to_qmark as normalize_to_qmark,  # re-exported: cursors import it from here
)



class QueryPacket(ClientMessage):
    """
    Query packet for SQL execution
    Use static factory methods to create instances:
    - QueryPacket.from_sql(sql_string) for plain SQL
    - QueryPacket.from_payload(payload_bytes) for pre-formatted payload with parameters
    """
    __slots__ = ('_payload_bytes', '_sql')

    def __init__(self, payload_bytes: bytearray, sql: str | None = None):
        """
        Initialize COM_QUERY packet with pre-formatted payload
        
        Args:
            payload_bytes: Complete packet payload including header + COM_QUERY + SQL
            sql: Original SQL string (for LOAD LOCAL INFILE validation)
        """
        self._payload_bytes = payload_bytes
        self._sql = sql
    
    @staticmethod
    def from_sql(sql: str) -> 'QueryPacket':
        """
        Create QueryPacket from SQL string
        
        Args:
            sql: SQL statement as string
            
        Returns:
            QueryPacket instance
        """
        payload = bytearray(b'\x00\x00\x00\x00\x03' + sql.encode('utf-8'))
        return QueryPacket(payload, sql)

    @staticmethod
    def from_substitute(sql: str, parameters: Any, no_backslash_escapes: bool = False) -> 'QueryPacket':
        result_list = substitute_params(sql, parameters, no_backslash_escapes)
        result_list.insert(0, b'\x00\x00\x00\x00\x03')
        return QueryPacket(bytearray(b"".join(result_list)), sql)

    def payload(self, context: Context, writer: 'PayloadWriter') -> bytearray:
        return self._payload_bytes

    def is_binary(self) -> bool:
        return False

    def type(self) -> str:
        return "COM_QUERY"
    
    def get_sql(self) -> str | None:
        """Get SQL string for LOAD LOCAL INFILE validation"""
        return self._sql
