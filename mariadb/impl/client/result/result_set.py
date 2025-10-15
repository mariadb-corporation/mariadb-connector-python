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
ResultSet implementation for MariaDB connector

Equivalent to the Java ResultSet interface.
"""

from typing import Any, Optional, List, Union
from .result import Result, ColumnMetadata
from ....exceptions import ProgrammingError


class ResultSet:
    """
    ResultSet implementation for MariaDB
    
    Equivalent to the Java ResultSet interface.
    """
    
    # Fetch directions
    FETCH_FORWARD = 1000
    FETCH_REVERSE = 1001
    FETCH_UNKNOWN = 1002
    
    # Result set types
    TYPE_FORWARD_ONLY = 1003
    TYPE_SCROLL_INSENSITIVE = 1004
    TYPE_SCROLL_SENSITIVE = 1005
    
    # Concurrency types
    CONCUR_READ_ONLY = 1007
    CONCUR_UPDATABLE = 1008
    
    def __init__(self, result: Result, statement: Any):
        """
        Initialize ResultSet
        
        Args:
            result: Underlying Result object
            statement: Statement that created this ResultSet
        """
        self.result = result
        self.statement = statement
        self.closed = False
        self.fetch_direction = self.FETCH_FORWARD
        self.fetch_size = 0
        self.row_number = 0
        self.was_null = False
    
    def _check_closed(self) -> None:
        """Check if ResultSet is closed"""
        if self.closed:
            raise ProgrammingError("ResultSet is closed")
    
    def next(self) -> bool:
        """
        Move cursor to next row
        
        Returns:
            True if there is a next row, False otherwise
        """
        self._check_closed()
        
        if self.result.next():
            self.row_number += 1
            return True
        
        return False
    
    def close(self) -> None:
        """Close the ResultSet"""
        if not self.closed:
            self.closed = True
            if self.result:
                self.result.close()
    
    def was_null(self) -> bool:
        """
        Check if last retrieved value was null
        
        Returns:
            True if last value was null
        """
        return self.was_null
    
    def get_string(self, column: Union[int, str]) -> Optional[str]:
        """
        Get string value from column
        
        Args:
            column: Column index (1-based) or name
            
        Returns:
            String value or None
        """
        self._check_closed()
        
        value = self._get_value(column)
        self.was_null = value is None
        
        if value is None:
            return None
        
        return str(value)
    
    def get_boolean(self, column: Union[int, str]) -> Optional[bool]:
        """Get boolean value from column"""
        self._check_closed()
        
        value = self._get_value(column)
        self.was_null = value is None
        
        if value is None:
            return None
        
        if isinstance(value, bool):
            return value
        elif isinstance(value, (int, float)):
            return value != 0
        elif isinstance(value, str):
            return value.lower() in ('true', '1', 'yes', 'on')
        
        return bool(value)
    
    def get_byte(self, column: Union[int, str]) -> Optional[int]:
        """Get byte value from column"""
        return self.get_int(column)
    
    def get_short(self, column: Union[int, str]) -> Optional[int]:
        """Get short value from column"""
        return self.get_int(column)
    
    def get_int(self, column: Union[int, str]) -> Optional[int]:
        """Get int value from column"""
        self._check_closed()
        
        value = self._get_value(column)
        self.was_null = value is None
        
        if value is None:
            return None
        
        try:
            return int(value)
        except (ValueError, TypeError):
            raise ProgrammingError(f"Cannot convert '{value}' to int")
    
    def get_long(self, column: Union[int, str]) -> Optional[int]:
        """Get long value from column"""
        return self.get_int(column)
    
    def get_float(self, column: Union[int, str]) -> Optional[float]:
        """Get float value from column"""
        self._check_closed()
        
        value = self._get_value(column)
        self.was_null = value is None
        
        if value is None:
            return None
        
        try:
            return float(value)
        except (ValueError, TypeError):
            raise ProgrammingError(f"Cannot convert '{value}' to float")
    
    def get_double(self, column: Union[int, str]) -> Optional[float]:
        """Get double value from column"""
        return self.get_float(column)
    
    def get_bytes(self, column: Union[int, str]) -> Optional[bytes]:
        """Get bytes value from column"""
        self._check_closed()
        
        value = self._get_value(column)
        self.was_null = value is None
        
        if value is None:
            return None
        
        if isinstance(value, bytes):
            return value
        elif isinstance(value, str):
            return value.encode('utf-8')
        
        return bytes(str(value), 'utf-8')
    
    def get_object(self, column: Union[int, str]) -> Any:
        """Get object value from column"""
        self._check_closed()
        
        value = self._get_value(column)
        self.was_null = value is None
        
        return value
    
    def find_column(self, column_name: str) -> int:
        """
        Find column index by name
        
        Args:
            column_name: Column name
            
        Returns:
            Column index (1-based)
        """
        self._check_closed()
        
        columns = self.result.get_columns_metadata()
        for i, col in enumerate(columns):
            if col.name.lower() == column_name.lower():
                return i + 1  # Return 1-based index
        
        raise ProgrammingError(f"Column '{column_name}' not found")
    
    def get_meta_data(self) -> 'ResultSetMetaData':
        """
        Get ResultSet metadata
        
        Returns:
            ResultSetMetaData object
        """
        self._check_closed()
        return ResultSetMetaData(self.result.get_columns_metadata())
    
    def is_closed(self) -> bool:
        """Check if ResultSet is closed"""
        return self.closed
    
    def get_type(self) -> int:
        """Get ResultSet type"""
        return self.TYPE_FORWARD_ONLY
    
    def get_concurrency(self) -> int:
        """Get ResultSet concurrency"""
        return self.CONCUR_READ_ONLY
    
    def get_fetch_direction(self) -> int:
        """Get fetch direction"""
        return self.fetch_direction
    
    def set_fetch_direction(self, direction: int) -> None:
        """Set fetch direction"""
        self._check_closed()
        self.fetch_direction = direction
    
    def get_fetch_size(self) -> int:
        """Get fetch size"""
        return self.fetch_size
    
    def set_fetch_size(self, rows: int) -> None:
        """Set fetch size"""
        self._check_closed()
        self.fetch_size = rows
    
    def get_row(self) -> int:
        """Get current row number"""
        return self.row_number
    
    def get_statement(self) -> Any:
        """Get statement that created this ResultSet"""
        return self.statement
    
    def _get_value(self, column: Union[int, str]) -> Any:
        """
        Get value from column (internal method)
        
        Args:
            column: Column index (1-based) or name
            
        Returns:
            Column value
        """
        if isinstance(column, str):
            return self.result.get_value_by_name(column)
        else:
            # Convert 1-based to 0-based index
            return self.result.get_value(column - 1)
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
        return False
    
    def __iter__(self):
        """Iterator support"""
        return self
    
    def __next__(self):
        """Iterator next"""
        if self.next():
            columns = self.result.get_columns_metadata()
            return tuple(self.get_object(i + 1) for i in range(len(columns)))
        raise StopIteration


class ResultSetMetaData:
    """
    ResultSet metadata
    
    Equivalent to the Java ResultSetMetaData interface.
    """
    
    def __init__(self, columns: List[ColumnMetadata]):
        """
        Initialize metadata
        
        Args:
            columns: Column metadata list
        """
        self.columns = columns
    
    def get_column_count(self) -> int:
        """Get number of columns"""
        return len(self.columns)
    
    def get_column_name(self, column: int) -> str:
        """Get column name (1-based index)"""
        return self.columns[column - 1].name
    
    def get_column_label(self, column: int) -> str:
        """Get column label (1-based index)"""
        return self.get_column_name(column)
    
    def get_column_type(self, column: int) -> int:
        """Get column type code (1-based index)"""
        return self.columns[column - 1].type_code
    
    def get_column_type_name(self, column: int) -> str:
        """Get column type name (1-based index)"""
        return self.columns[column - 1].type_name
    
    def get_precision(self, column: int) -> int:
        """Get column precision (1-based index)"""
        return self.columns[column - 1].precision
    
    def get_scale(self, column: int) -> int:
        """Get column scale (1-based index)"""
        return self.columns[column - 1].scale
    
    def is_nullable(self, column: int) -> bool:
        """Check if column is nullable (1-based index)"""
        return self.columns[column - 1].nullable
    
    def get_table_name(self, column: int) -> Optional[str]:
        """Get table name (1-based index)"""
        return self.columns[column - 1].table_name
    
    def get_schema_name(self, column: int) -> Optional[str]:
        """Get schema name (1-based index)"""
        return self.columns[column - 1].schema_name
    
    def get_catalog_name(self, column: int) -> Optional[str]:
        """Get catalog name (1-based index)"""
        return self.columns[column - 1].catalog_name
