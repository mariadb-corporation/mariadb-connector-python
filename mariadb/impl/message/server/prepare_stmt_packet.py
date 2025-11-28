# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Prepare Response Packet parser for MariaDB protocol

Based on MySQL/MariaDB protocol COM_STMT_PREPARE response structure.
"""

import struct
import threading
import asyncio
from typing import TYPE_CHECKING, List, Optional, Callable

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
        'database',
        'columns',
        'parameters',
        'closed',
        'close_callback',
    )
    def __init__(
        self,
        statement_id: int,
        column_count: int,
        parameter_count: int,
        warning_count: int,
        sql: Optional[str],
        database: str,
        close_callback: Callable[['PrepareStmtPacket'], None]
    ):
        """Initialize prepare statement packet"""
        self.statement_id = statement_id
        self.column_count = column_count
        self.parameter_count = parameter_count
        self.warning_count = warning_count
        self.sql = sql
        self.database = database
        self.columns: List[ColumnDefinitionPacket] = []
        self.parameters: List[ColumnDefinitionPacket] = []
        self.closed = False
        self.close_callback = close_callback
    
    @staticmethod
    def decode(data: memoryview, context: 'Context', sql: Optional[str], close_callback: Callable[['PrepareStmtPacket'], None]) -> 'PrepareStmtPacket':
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
            sql,
            context.database,
            close_callback
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
        """Close the prepared statement and call close callback"""
        if not self.closed:
            self.closed = True
            self.close_callback(self)


class CachedPrepareStmtPacket(PrepareStmtPacket):
    """
    PrepareStmtPacket with cache reference management.
    
    This class extends PrepareStmtPacket to add context manager support
    for automatic cache reference management when used with a cache.
    Handles its own reference counting.
    """
    __slots__ = ('ref_count', 'lock', 'in_cache')
    
    def __init__(
        self,
        statement_id: int,
        column_count: int,
        parameter_count: int,
        warning_count: int,
        sql: Optional[str],
        database: str,
        close_callback: Callable[['CachedPrepareStmtPacket'], None]
    ):
        """Initialize cached prepare statement packet"""
        super().__init__(statement_id, column_count, parameter_count, warning_count, sql, database, close_callback)
        self.ref_count = 1
        self.lock = threading.Lock()
        self.in_cache = True
    
    def acquire(self) -> bool:
        """
        Acquire a reference to this statement.
        Returns True if acquired, False if statement is in use.
        """
        with self.lock:
            if not self.closed:
                self.ref_count += 1
                return True
            return False
    
    def close(self) -> None:
        """Release a reference to this statement"""
        with self.lock:
            if self.ref_count > 0:
                self.ref_count -= 1
                if self.ref_count == 0 and not self.in_cache:
                    # Only close on server if not in cache and no refs
                    super().close()
    
    def evicted_from_cache(self) -> None:
        """Called when this statement is evicted from the cache"""
        with self.lock:
            self.in_cache = False
            # If no one is using it, close it now
            if self.ref_count == 0 and not self.closed:
                super().close()
    
    def is_in_use(self) -> bool:
        """Check if statement is currently in use"""
        with self.lock:
            return self.ref_count > 0
    
    def __enter__(self) -> 'CachedPrepareStmtPacket':
        """Enter context manager"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager and release cache reference"""
        self.close()
        return False
    
    @staticmethod
    def decode(data: memoryview, context: 'Context', sql: Optional[str], close_callback: Callable[['CachedPrepareStmtPacket'], None]) -> 'CachedPrepareStmtPacket':
        """Decode COM_STMT_PREPARE response packet (optimized)"""
        # Unpack all fields in one operation using pre-compiled struct
        _, statement_id, column_count, parameter_count, _, warning_count = _STRUCT_PREPARE_RESPONSE.unpack_from(data, 0)
        
        # Update context if provided
        if context:
            context.warning_count = warning_count
        
        return CachedPrepareStmtPacket(
            statement_id,
            column_count,
            parameter_count,
            warning_count,
            sql,
            context.database,
            close_callback
        )
