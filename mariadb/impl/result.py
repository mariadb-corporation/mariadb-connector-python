#
# Copyright (C) 2020-2021 Georg Richter and MariaDB Corporation AB

# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Library General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.

# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Library General Public License for more details.

# You should have received a copy of the GNU Library General Public
# License along with this library; if not see <http://www.gnu.org/licenses>
# or write to the Free Software Foundation, Inc.,
# 51 Franklin St., Fifth Floor, Boston, MA 02110, USA
#

"""
Result set classes for MariaDB query results

Based on Java Result.java, CompleteResult.java, and StreamingResult.java
"""

import struct
from typing import List, Optional, Any, TYPE_CHECKING
from abc import ABC, abstractmethod
from mariadb_shared.constants import STATUS

if TYPE_CHECKING:
    from .client.socket.packet_reader import PacketReader
    from .client.context import Context
    from .configuration import Configuration


class Result(ABC):
    """
    Abstract base class for result sets
    
    Based on Java Result.java
    """
    
    def __init__(
        self,
        columns: List[dict],
        column_count: int,
        config: 'Configuration',
        is_binary: bool = False
    ):
        """
        Initialize result
        
        Args:
            columns: Column metadata
            column_count: Number of columns
            config: Configuration for parsing
            is_binary: Whether result uses binary protocol
        """
        self.columns = columns
        self.column_count = column_count
        self.config = config
        self.is_binary = is_binary
        self.loaded = False  # All rows loaded flag
        self.warning_count = 0
        self.is_output_parameters = False
        self.row_pointer = -1  # Current row position (-1 = before first)
        
    @abstractmethod
    def streaming(self) -> bool:
        """Check if this is a streaming result"""
        pass
    
    @abstractmethod
    def fetch_one(self) -> Optional[Any]:
        """Fetch next row"""
        pass
    
    @abstractmethod
    def fetch_many(self, size: int) -> List[Any]:
        """Fetch multiple rows"""
        pass
    
    @abstractmethod
    def fetch_all(self) -> List[Any]:
        """Fetch all remaining rows"""
        pass
    
    @abstractmethod
    def fetch_remaining(self) -> None:
        """Consume all remaining rows without processing"""
        pass
    
    @abstractmethod
    def get_row_count(self) -> int:
        """Get total row count (-1 if unknown)"""
        pass
    
    def row_number(self) -> Optional[int]:
        """
        Get current row number (1-based, DB-API style)
        
        Returns row_pointer + 1:
        - row_pointer = -1 (before first) → rownumber = 0
        - row_pointer = 0 (at first) → rownumber = 1
        - etc.
        """
        return self.row_pointer + 1


class CompleteResult(Result):
    """
    Complete (buffered) result set - all rows read immediately
    
    Based on Java CompleteResult.java
    """
    
    def __init__(
        self,
        columns: List[dict],
        column_count: int,
        config: 'Configuration',
        rows: List[Any],
        is_binary: bool = False
    ):
        """
        Initialize complete result with all rows
        
        Args:
            columns: Column metadata
            column_count: Number of columns
            config: Configuration for parsing
            rows: All row data (already parsed)
            is_binary: Whether result uses binary protocol
        """
        super().__init__(columns, column_count, config, is_binary)
        self.rows = rows
        self.data_size = len(rows)
        self.loaded = True
        self.row_pointer = -1  # Before first row
    
    def scroll(self, value: int, mode: str = "relative") -> None:
        """
        Scroll to a new position in the result set
        
        Args:
            value: Position value (row index for absolute mode)
            mode: "relative" or "absolute"
            
        Semantics:
        - scroll(N, absolute) positions cursor so next fetch returns row N
        - row_pointer tracks the last fetched row index (-1 = none fetched yet)
        """
        # Calculate new position
        if mode == "relative":
            if value == 0:
                return  # No movement needed
            new_pos = self.row_pointer + value
        elif mode == "absolute":
            # For absolute mode, value is the row index to fetch next
            # So we need to set row_pointer to value - 1
            new_pos = value - 1
        else:
            raise ValueError("Invalid scroll mode")
        
        # Validate new position (-1 = before first, data_size-1 = at last)
        if new_pos < -1 or new_pos >= self.data_size:
            raise ValueError("Position value is out of range")
        
        # Set new position
        self.row_pointer = new_pos
        
    def streaming(self) -> bool:
        """Check if this is a streaming result"""
        return False
    
    def fetch_one(self) -> Optional[Any]:
        """
        Fetch next row
        
        row_pointer semantics:
        -1 = before first row
        0 to data_size-1 = index of last fetched row
        
        rownumber = row_pointer + 1 (1-based, 0 = before first)
        """
        # Check if we can fetch more rows
        if self.row_pointer >= self.data_size - 1:
            # Already at or past last row
            return None
        
        # Move to next row position and return it
        self.row_pointer += 1
        return self.rows[self.row_pointer]
    
    def fetch_many(self, size: int) -> List[Any]:
        """Fetch multiple rows"""
        result = []
        for _ in range(size):
            row = self.fetch_one()
            if row is None:
                break
            result.append(row)
        return result
    
    def fetch_all(self) -> List[Any]:
        """Fetch all remaining rows"""
        if self.row_pointer < 0:
            # Before first - return all rows
            self.row_pointer = self.data_size
            return self.rows[:]
        elif self.row_pointer < self.data_size:
            # In middle - return remaining rows
            remaining = self.rows[self.row_pointer + 1:]
            self.row_pointer = self.data_size
            return remaining
        else:
            # After last - return empty
            return []
    
    def fetch_remaining(self) -> None:
        """Consume all remaining rows without processing"""
        self.row_pointer = self.data_size
    
    def get_row_count(self) -> int:
        """Get total row count"""
        return self.data_size


class StreamingResult(Result):
    """
    Streaming (unbuffered) result set - rows read on demand
    
    Based on Java StreamingResult.java
    """
    
    def __init__(
        self,
        reader: 'PacketReader',
        context: 'Context',
        columns: List[dict],
        column_count: int,
        config: 'Configuration',
        is_binary: bool = False,
        row_parser: Any = None
    ):
        """
        Initialize streaming result
        
        Args:
            reader: Packet reader
            context: Connection context
            columns: Column metadata
            column_count: Number of columns
            config: Configuration for parsing
            is_binary: Whether result uses binary protocol
            row_parser: Function to parse row packets (from Client)
        """
        super().__init__(columns, column_count, config, is_binary)
        self.reader = reader
        self.context = context
        self.row_parser = row_parser
        self.loaded = False
        self._row_count = 0  # Track number of rows fetched
        
    def streaming(self) -> bool:
        """Check if this is a streaming result"""
        return True
    
    def _read_next_row_packet(self) -> Optional[bytes]:
        """
        Read next row packet from network
        
        Returns:
            Row packet bytes, or None if no more rows
        """
        if self.loaded:
            return None
            
        try:
            row_packet = self.reader.read_packet()
            
            if len(row_packet) == 0:
                self.loaded = True
                return None
            
            # Check for EOF/OK packet
            if (row_packet[0] == 0xFE and 
                ((self.context.isEofDeprecated() and len(row_packet) < 16777215) or 
                 (not self.context.isEofDeprecated() and len(row_packet) < 8))):
                
                # This is an EOF or OK packet - end of result set
                pos = 1  # Skip packet type byte
                
                if not self.context.isEofDeprecated():
                    # Traditional EOF packet
                    self.warning_count = struct.unpack('<H', row_packet[pos:pos + 2])[0]
                    server_status = struct.unpack('<H', row_packet[pos + 2:pos + 4])[0]
                    self.context.server_status = server_status
                    self.is_output_parameters = (server_status & STATUS.PS_OUT_PARAMS) != 0
                else:
                    # OK packet with 0xFE header (DEPRECATE_EOF enabled)
                    # Parse OK packet structure
                    affected_rows, pos = self.reader.read_length_encoded_int(row_packet, pos)
                    insert_id, pos = self.reader.read_length_encoded_int(row_packet, pos)
                    server_status = struct.unpack('<H', row_packet[pos:pos + 2])[0]
                    self.warning_count = struct.unpack('<H', row_packet[pos + 2:pos + 4])[0]
                    self.context.server_status = server_status
                    self.is_output_parameters = (self.context.server_status & STATUS.PS_OUT_PARAMS) != 0
                
                self.loaded = True
                return None
            
            # Check for error packet
            if row_packet[0] == 0xFF:
                self.loaded = True
                # Error packet - will be handled by caller
                raise Exception("Error packet received during streaming")
            
            # Regular row data packet
            return row_packet
            
        except Exception as e:
            self.loaded = True
            raise
    
    def fetch_one(self) -> Optional[Any]:
        """Fetch next row"""
        if self.loaded:
            return None
        
        row_packet = self._read_next_row_packet()
        if row_packet is None:
            return None
        
        # Increment row count
        self._row_count += 1
        
        # Parse row using the provided parser
        if self.row_parser:
            return self.row_parser(row_packet, self.columns, self.config, self.is_binary)
        else:
            # Fallback - return raw packet (should not happen)
            return row_packet
    
    def fetch_many(self, size: int) -> List[Any]:
        """Fetch multiple rows"""
        result = []
        for _ in range(size):
            row = self.fetch_one()
            if row is None:
                break
            result.append(row)
        return result
    
    def fetch_all(self) -> List[Any]:
        """Fetch all remaining rows"""
        result = []
        while not self.loaded:
            row = self.fetch_one()
            if row is None:
                break
            result.append(row)
        return result
    
    def fetch_remaining(self) -> None:
        """
        Consume all remaining rows without processing them.
        Called when a new query needs to be executed.
        """
        if not self.loaded:
            while not self.loaded:
                row_packet = self._read_next_row_packet()
                if row_packet is not None:
                    self._row_count += 1
    
    def get_row_count(self) -> int:
        """Get total row count"""
        return self._row_count
