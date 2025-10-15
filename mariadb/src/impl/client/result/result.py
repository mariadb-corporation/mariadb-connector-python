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
Result interface for MariaDB query results

Equivalent to the Java Result interface.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Any, Tuple


class ColumnMetadata:
    """Column metadata information"""
    
    def __init__(self, name: str, type_name: str, type_code: int, 
                 precision: int = 0, scale: int = 0, nullable: bool = True):
        self.name = name
        self.type_name = type_name
        self.type_code = type_code
        self.precision = precision
        self.scale = scale
        self.nullable = nullable
        self.table_name: Optional[str] = None
        self.schema_name: Optional[str] = None
        self.catalog_name: Optional[str] = None
        self.original_name: Optional[str] = None
        self.original_table_name: Optional[str] = None
    
    def __str__(self) -> str:
        return f"Column(name='{self.name}', type='{self.type_name}')"


class Result(ABC):
    """
    Result interface for MariaDB query results
    
    Equivalent to the Java Result interface.
    """
    
    @abstractmethod
    def get_column_count(self) -> int:
        """Get number of columns"""
        pass
    
    @abstractmethod
    def get_column_metadata(self, index: int) -> ColumnMetadata:
        """Get column metadata by index (0-based)"""
        pass
    
    @abstractmethod
    def get_columns_metadata(self) -> List[ColumnMetadata]:
        """Get all column metadata"""
        pass
    
    @abstractmethod
    def next(self) -> bool:
        """Move to next row"""
        pass
    
    @abstractmethod
    def get_value(self, index: int) -> Any:
        """Get value by column index (0-based)"""
        pass
    
    @abstractmethod
    def get_value_by_name(self, name: str) -> Any:
        """Get value by column name"""
        pass
    
    @abstractmethod
    def is_null(self, index: int) -> bool:
        """Check if value is null by index"""
        pass
    
    @abstractmethod
    def close(self) -> None:
        """Close result"""
        pass
    
    @abstractmethod
    def is_closed(self) -> bool:
        """Check if result is closed"""
        pass


class CompleteResult(Result):
    """
    Complete result implementation for small result sets
    
    Equivalent to the Java CompleteResult class.
    """
    
    def __init__(self, columns: List[ColumnMetadata], rows: List[Tuple]):
        """
        Initialize complete result
        
        Args:
            columns: Column metadata
            rows: Row data
        """
        self.columns = columns
        self.rows = rows
        self.current_row_index = -1
        self.closed = False
        
        # Create column name to index mapping
        self.column_name_map = {}
        for i, col in enumerate(columns):
            self.column_name_map[col.name.lower()] = i
    
    def get_column_count(self) -> int:
        """Get number of columns"""
        return len(self.columns)
    
    def get_column_metadata(self, index: int) -> ColumnMetadata:
        """Get column metadata by index"""
        if index < 0 or index >= len(self.columns):
            raise IndexError(f"Column index {index} out of range")
        return self.columns[index]
    
    def get_columns_metadata(self) -> List[ColumnMetadata]:
        """Get all column metadata"""
        return self.columns.copy()
    
    def next(self) -> bool:
        """Move to next row"""
        if self.closed:
            return False
        
        self.current_row_index += 1
        return self.current_row_index < len(self.rows)
    
    def get_value(self, index: int) -> Any:
        """Get value by column index"""
        if self.current_row_index < 0 or self.current_row_index >= len(self.rows):
            raise RuntimeError("No current row")
        
        if index < 0 or index >= len(self.columns):
            raise IndexError(f"Column index {index} out of range")
        
        return self.rows[self.current_row_index][index]
    
    def get_value_by_name(self, name: str) -> Any:
        """Get value by column name"""
        index = self.column_name_map.get(name.lower())
        if index is None:
            raise KeyError(f"Column '{name}' not found")
        
        return self.get_value(index)
    
    def is_null(self, index: int) -> bool:
        """Check if value is null"""
        return self.get_value(index) is None
    
    def close(self) -> None:
        """Close result"""
        self.closed = True
    
    def is_closed(self) -> bool:
        """Check if result is closed"""
        return self.closed
    
    def get_row_count(self) -> int:
        """Get total number of rows"""
        return len(self.rows)
    
    def reset(self) -> None:
        """Reset to before first row"""
        self.current_row_index = -1
    
    def __len__(self) -> int:
        return len(self.rows)
    
    def __iter__(self):
        """Iterator support"""
        self.reset()
        return self
    
    def __next__(self):
        """Iterator next"""
        if self.next():
            return tuple(self.get_value(i) for i in range(self.get_column_count()))
        raise StopIteration
