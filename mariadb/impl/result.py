# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Result set classes for MariaDB query results
"""

from typing import List, Optional, Any, TYPE_CHECKING, Callable, Tuple
from abc import ABC, abstractmethod
from .message.server.eof_packet import EofPacket
from .message.server.ok_packet import OkPacket
from .message.server.column_definition_packet import ColumnDefinitionPacket

if TYPE_CHECKING:
    from .client.context import Context
    from .configuration import Configuration


class Result(ABC):
    """
    Abstract base class for result sets
    """
    __slots__ = ('columns', 'column_count', 'config', 'loaded', 'warning_count', 'is_output_parameters', 'row_pointer')
    
    def __init__(
        self,
        columns: List[ColumnDefinitionPacket],
        column_count: int,
        config: 'Configuration'
    ):
        """
        Initialize result
        
        Args:
            columns: Column metadata
            column_count: Number of columns
            config: Configuration for parsing
        """
        self.columns: List[ColumnDefinitionPacket] = columns
        self.column_count: int = column_count
        self.config: 'Configuration' = config
        self.loaded: bool = False  # All rows loaded flag
        self.warning_count: int = 0
        self.is_output_parameters: bool = False
        self.row_pointer: int = -1  # Current row position (-1 = before first)
    
    # =========================================================================
    # Abstract Methods
    # =========================================================================
        
    @abstractmethod
    def streaming(self) -> bool:
        """Check if this is a streaming result"""
        ...
    
    
    @abstractmethod
    def get_row_count(self) -> int:
        """Get total row count (-1 if unknown)"""
        ...

    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    def row_number(self) -> Optional[int]:
        """Get current row number (1-based, DB-API style). Returns row_pointer + 1."""
        return self.row_pointer + 1
    
    def __repr__(self) -> str:
        """String representation for debugging"""
        return f"{self.__class__.__name__}(columns={self.column_count}, row_pointer={self.row_pointer}, loaded={self.loaded})"

class SyncResult(Result):
    """
    Abstract base class for result sets
    """
    __slots__ = ()
    
    def __init__(
        self,
        columns: List[ColumnDefinitionPacket],
        column_count: int,
        config: 'Configuration'
    ):
        super().__init__(columns, column_count, config)
    
    # =========================================================================
    # Abstract Methods
    # =========================================================================
    
    @abstractmethod
    def fetch_one(self) -> Optional[Any]:
        """Fetch next row"""
        ...
        
    @abstractmethod
    def fetch_all(self) -> List[Any]:
        """Fetch all remaining rows"""
        ...
        
    @abstractmethod
    def scroll(self, value: int, mode: str = "relative") -> None:
        ...


class AsyncResult(Result):
    """
    Abstract base class for result sets
    """
    __slots__ = ()
    
    def __init__(
        self,
        columns: List[ColumnDefinitionPacket],
        column_count: int,
        config: 'Configuration'
    ):
        super().__init__(columns, column_count, config)
    
    # =========================================================================
    # Abstract Methods
    # =========================================================================
        
    @abstractmethod
    async def fetch_one(self) -> Optional[Any]:
        """Fetch next row"""
        ...
    
    @abstractmethod
    async def fetch_all(self) -> List[Any]:
        """Fetch all remaining rows"""
        ...
    
    
    @abstractmethod
    async def scroll(self, value: int, mode: str = "relative") -> None:
        ...

class BaseCompleteResult(Result):
    """
    Base class for complete (buffered) result sets
    
    All rows are loaded into memory at once, allowing random access.
    """
    __slots__ = ('rows', 'data_size')
    
    def __repr__(self) -> str:
        """String representation for debugging"""
        return f"{self.__class__.__name__}(columns={self.column_count}, rows={self.rows})"
    
    def __init__(
        self,
        columns: List[ColumnDefinitionPacket],
        column_count: int,
        config: 'Configuration',
        rows: List[tuple]
    ):
        """
        Initialize complete result with all rows
        
        Args:
            columns: Column metadata
            column_count: Number of columns
            config: Configuration for parsing
            rows: All row data (already parsed)
        """
        super().__init__(columns, column_count, config)
        self.rows: List[tuple] = rows
        self.data_size: int = len(rows)
        self.loaded: bool = True
        self.row_pointer: int = -1  # Before first row
    
    def scroll(self, value: int, mode: str = "relative") -> None:
        """Scroll to a new position in the result set. Mode: 'relative' or 'absolute'."""
        if mode == "relative":
            if value == 0:
                return
            new_pos = self.row_pointer + value
        elif mode == "absolute":
            new_pos = value - 1  # absolute mode: value is row index to fetch next, so row_pointer = value - 1
        else:
            raise ValueError("Invalid scroll mode")
        
        if new_pos < -1 or new_pos >= self.data_size:  # Validate: -1 = before first, data_size-1 = at last
            raise ValueError("Position value is out of range")
        
        self.row_pointer = new_pos
        
    def streaming(self) -> bool:
        """Check if this is a streaming result"""
        return False
    
    def get_row_count(self) -> int:
        """Get total row count"""
        return self.data_size


class SyncCompleteResult(BaseCompleteResult, SyncResult):
    """
    Synchronous complete (buffered) result set
    
    All rows are loaded into memory at once, allowing random access.
    Uses synchronous (non-async) methods.
    """
    __slots__ = ()
    
    def fetch_one(self) -> Optional[Any]:
        """Fetch next row. row_pointer: -1 = before first, 0 to data_size-1 = index of last fetched."""
        row_pointer = self.row_pointer
        if row_pointer >= self.data_size - 1:
            return None  # Already at or past last row
        
        row_pointer += 1
        self.row_pointer = row_pointer
        return self.rows[row_pointer]
    
    def fetch_all(self) -> List[Any]:
        """Fetch all remaining rows"""
        row_pointer = self.row_pointer
        data_size = self.data_size
        
        if row_pointer < 0:
            self.row_pointer = data_size  # Before first - return all rows
            return self.rows[:]
        elif row_pointer < data_size:
            remaining = self.rows[row_pointer + 1:]  # In middle - return remaining rows
            self.row_pointer = data_size
            return remaining
        return []  # After last - return empty

class AsyncCompleteResult(BaseCompleteResult, AsyncResult):
    """
    Asynchronous complete (buffered) result set
    
    All rows are loaded into memory at once, allowing random access.
    Uses async methods for consistency with async API.
    """
    __slots__ = ()
    
    async def fetch_one(self) -> Optional[Any]:
        """Fetch next row (async). row_pointer: -1 = before first, 0 to data_size-1 = index of last fetched."""
        row_pointer = self.row_pointer
        if row_pointer >= self.data_size - 1:
            return None  # Already at or past last row
        
        row_pointer += 1
        self.row_pointer = row_pointer
        return self.rows[row_pointer]
    
    async def fetch_all(self) -> List[Any]:
        """Fetch all remaining rows (async)"""
        row_pointer = self.row_pointer
        data_size = self.data_size
        
        if row_pointer < 0:
            self.row_pointer = data_size  # Before first - return all rows
            return self.rows[:]
        elif row_pointer < data_size:
            remaining = self.rows[row_pointer + 1:]  # In middle - return remaining rows
            self.row_pointer = data_size
            return remaining
        return []  # After last - return empty
    
    async def scroll(self, value: int, mode: str = "relative") -> None:
        super().scroll(value, mode)

class BaseStreamingResult(Result):
    """
    Base class for streaming (unbuffered) result sets
    
    Rows are fetched one at a time from the network as needed.
    """
    __slots__ = ('read_payload_func', 'context', 'row_parser', '_row_count')
    
    def __repr__(self) -> str:
        """String representation for debugging"""
        return f"{self.__class__.__name__}(columns={self.column_count}, row_pointer={self.row_pointer}, loaded={self.loaded})"
    
    def __init__(
        self,
        read_payload_func: Callable[[], memoryview],
        context: 'Context',
        columns: List[ColumnDefinitionPacket],
        column_count: int,
        config: 'Configuration',
        row_parser: Callable[['BaseConnection', bytes, List['ColumnDefinitionPacket'], 'Configuration'], Tuple] = None,
    ):
        """
        Initialize streaming result
        
        Args:
            read_payload_func: Function to read next packet from network
            context: Connection context
            columns: Column metadata
            column_count: Number of columns
            config: Configuration for parsing
            row_parser: Function to parse row packets (from Client)
        """
        super().__init__(columns, column_count, config)
        self.read_payload_func: Callable[[], memoryview] = read_payload_func
        self.context: Context = context
        self.row_parser: Callable[['BaseConnection', bytes, List['ColumnDefinitionPacket'], 'Configuration'], Tuple] = row_parser
        self.loaded: bool = False
        self._row_count: int = 0  # Track number of rows fetched
        
    def streaming(self) -> bool:
        """Check if this is a streaming result"""
        return True
   
    
    @abstractmethod
    def _read_next_row_packet(self) -> Optional[bytes]:
        """Read next row packet from network (sync or async)"""
        pass
    
    def get_row_count(self) -> int:
        """Get total row count"""
        return self._row_count
    


class SyncStreamingResult(BaseStreamingResult, SyncResult):
    """
    Synchronous streaming (unbuffered) result set
    
    Uses blocking I/O to fetch rows from the network.
    """
    __slots__ = ()
    
    def fetch_one(self) -> Optional[tuple]:
        """Fetch next row"""
        if self.loaded:
            return None
        
        row_packet = self._read_next_row_packet()
        if row_packet is None:
            return None
        
        # Increment row count
        self._row_count += 1
        return self.row_parser(row_packet, self.columns, self.config)
        
    def fetch_all(self) -> List[tuple]:
        """Fetch all remaining rows"""
        result = []
        while not self.loaded:
            row = self.fetch_one()
            if row is None:
                break
            result.append(row)
        return result
    
    def fetch_remaining(self) -> None:
        """Consume all remaining rows without processing them. Called when a new query needs to be executed."""
        if not self.loaded:
            while not self.loaded:
                row_packet = self._read_next_row_packet()
                if row_packet is not None:
                    self._row_count += 1    
    
    def _read_next_row_packet(self) -> Optional[memoryview]:
        """Read next row packet from network (synchronous). Returns row packet memoryview, or None if no more rows."""
        try:
            row_packet = self.read_payload_func()
            packet_type = row_packet[0]
            
            if packet_type == 0xFE:  # Check for EOF/OK packet
                eof_deprecated = self.context.isEofDeprecated()
                packet_len = len(row_packet)
                
                if (eof_deprecated and packet_len < 16777215) or (not eof_deprecated and packet_len < 8):
                    if not eof_deprecated:
                        EofPacket.decode(row_packet, self.context)  # Traditional EOF packet
                    else:
                        OkPacket.decode(row_packet, self.context)  # OK packet with 0xFE header (DEPRECATE_EOF enabled)
                    
                    self.loaded = True
                    return None

            if packet_type == 0xFF:  # Check for error packet
                self.loaded = True
                raise Exception("Error packet received during streaming")
            
            return row_packet  # Regular row data packet
            
        except Exception:
            self.loaded = True
            raise

    def scroll(self, value: int, mode: str = "relative") -> None:
        """Scroll forward in streaming result (limited support). Only supports forward relative scrolling."""
        if mode != "relative":
            raise ValueError("Streaming results only support relative scroll mode")
        
        if value < 0:
            raise ValueError("Streaming results only support forward scrolling (positive values)")
        
        if value == 0:
            return
        
        for _ in range(value):  # Skip 'value' rows by fetching and discarding them
            if self.loaded:
                raise ValueError("Cannot scroll past end of result set")
            row_packet = self._read_next_row_packet()
            if row_packet is None:
                raise ValueError("Cannot scroll past end of result set")
            self._row_count += 1
            self.row_pointer += 1

class AsyncStreamingResult(BaseStreamingResult, AsyncResult):
    """
    Asynchronous streaming (unbuffered) result set
    
    Uses non-blocking I/O to fetch rows from the network.
    """
    __slots__ = ()
    
    async def _read_next_row_packet(self) -> Optional[memoryview]:
        """Read next row packet from network (asynchronous). Returns row packet memoryview, or None if no more rows."""
        try:
            row_packet = await self.read_payload_func()
            packet_type = row_packet[0]
            
            if packet_type == 0xFE:  # Check for EOF/OK packet
                eof_deprecated = self.context.isEofDeprecated()
                packet_len = len(row_packet)
                
                if (eof_deprecated and packet_len < 16777215) or (not eof_deprecated and packet_len < 8):
                    if not eof_deprecated:
                        EofPacket.decode(row_packet, self.context)  # Traditional EOF packet
                    else:
                        OkPacket.decode(row_packet, self.context)  # OK packet with 0xFE header (DEPRECATE_EOF enabled)
                    self.loaded = True
                    return None
            
            if packet_type == 0xFF:  # Check for error packet
                self.loaded = True
                raise Exception("Error packet received during streaming")
            
            return row_packet  # Regular row data packet
            
        except Exception:
            self.loaded = True
            raise
    
    async def fetch_one(self) -> Optional[tuple]:
        """Fetch next row (async)"""
        if self.loaded:
            return None
        
        row_packet = await self._read_next_row_packet()
        if row_packet is None:
            return None
        
        # Increment row count
        self._row_count += 1
        return self.row_parser(row_packet, self.columns, self.config)
    
    async def fetch_all(self) -> List[tuple]:
        """Fetch all remaining rows (async)"""
        result = []
        while not self.loaded:
            row = await self.fetch_one()
            if row is None:
                break
            result.append(row)
        return result
    
    async def fetch_remaining(self) -> None:
        """Consume all remaining rows without processing them (async). Called when a new query needs to be executed."""
        if not self.loaded:
            while not self.loaded:
                row_packet = await self._read_next_row_packet()
                if row_packet is not None:
                    self._row_count += 1
    
    async def scroll(self, value: int, mode: str = "relative") -> None:
        """Scroll forward in streaming result (limited support, async). Only supports forward relative scrolling."""
        if mode != "relative":
            raise ValueError("Streaming results only support relative scroll mode")
        
        if value < 0:
            raise ValueError("Streaming results only support forward scrolling (positive values)")
        
        if value == 0:
            return
        
        for _ in range(value):  # Skip 'value' rows by fetching and discarding them
            if self.loaded:
                raise ValueError("Cannot scroll past end of result set")
            row_packet = await self._read_next_row_packet()
            if row_packet is None:
                raise ValueError("Cannot scroll past end of result set")
            self._row_count += 1
            self.row_pointer += 1
