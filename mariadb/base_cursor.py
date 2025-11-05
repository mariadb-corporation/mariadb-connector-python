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
Base cursor implementation with common functionality for sync and async cursors
"""

import datetime
import decimal
from abc import ABC, abstractmethod
from collections import namedtuple
from typing import Sequence, Optional, List, Any, Union, Dict, TYPE_CHECKING

from .impl.completion import Completion
from .impl.message.server.column_definition_packet import ColumnDefinitionPacket

from .exceptions import ProgrammingError
from .impl.client.exception_factory import ExceptionFactory
from .impl.result import CompleteResult, Result
from .impl.string_utils import StringEscaper
from mariadb_shared.constants.STATUS import NO_BACKSLASH_ESCAPES
from mariadb_shared.constants import EXT_FIELD_TYPE
from mariadb_shared.constants.FIELD_TYPE import (
    INT24, TIMESTAMP, YEAR, NEWDECIMAL, DECIMAL, JSON
)
from mariadb_shared.constants.FIELD_FLAG import NUMERIC as NUM_FLAG

if TYPE_CHECKING:
    from .base_connection import BaseConnection

# Constants
ROWS_ALL = -1
RESULT_TUPLE = 0
RESULT_NAMEDTUPLE = 1
RESULT_DICTIONARY = 2


class BaseCursor(ABC):
    """
    Base class for MariaDB Cursor Objects
    
    Provides common functionality for both synchronous and asynchronous cursors.
    Subclasses must implement abstract methods for sync or async behavior.
    """

    def __init__(self, connection: 'BaseConnection', **kwargs):
        """
        Initialize cursor with a connection
        
        Args:
            connection: Database connection
            **kwargs: Cursor options (buffered, named_tuple, dictionary, etc.)
        """
        self.connection: 'BaseConnection' = connection
        self._closed: bool = False
        self.arraysize: int = 1
        self._affected_rows: int = -1
        self._rowcount: int = -1
        self.description: Optional[List[Any]] = None
        self.lastrowid: Optional[int] = None
        self._completions: List[Completion] = []
        self._completion_index: int = 0
        self._cursor_config = None
        self._exception_factory = ExceptionFactory()
        self._buffered: bool = bool(kwargs.pop('buffered', True))
        self._result: Optional[Result] = None
        
        if kwargs:
            self._cursor_config = self.connection._configuration.from_dict(
                self.connection._configuration.to_dict()
            )
            
            rtype = kwargs.pop("named_tuple", False)
            if rtype:
                self._cursor_config.named_tuple = rtype
            else:
                rtype = kwargs.pop("dictionary", False)
                if rtype:
                    self._cursor_config.dictionary = rtype
            
            native_obj = kwargs.pop("native_object", None)
            if native_obj is not None:
                self._cursor_config.native_object = bool(native_obj)

    @property
    def rowcount(self) -> int:
        """Get the number of rows (read-only property)"""
        return self._rowcount
    
    def _get_config(self):
        """Get the effective configuration (cursor-specific or connection default)"""
        return getattr(self, '_cursor_config', None) or self.connection._configuration
        
    def _check_closed(self) -> None:
        """Check if cursor is closed"""
        if self._closed or self.connection._closed:
            raise self._exception_factory.create_exception(
                "Cursor is closed",
                errno=0,
                sql_state='42000'
            )

    @property
    def closed(self) -> bool:
        """Return True if cursor is closed"""
        return self._closed or self.connection._closed
    
    @property
    def warnings(self) -> int:
        """Get the number of warnings from the last executed statement"""
        if (hasattr(self, '_completions') and self._completions and 
            self._completion_index < len(self._completions)):
            completion = self._completions[self._completion_index]
            return getattr(completion, 'warning_count', 0)
        return 0

    @property
    def sp_outparams(self) -> bool:
        """Check if current result set contains output parameters"""
        if (self._completions and 
            self._completion_index < len(self._completions)):
            completion = self._completions[self._completion_index]
            return completion.is_output_parameters()
        return False
        
    @property
    def affected_rows(self) -> int:
        """Alias for rowcount"""
        return int(self.rowcount)

    @property
    def rownumber(self) -> Optional[int]:
        """Current row number (1-based, DB-API style)"""
        if self._result is not None:
            return self._result.row_number()
        return None

    @property
    def _resulttype(self) -> int:
        """Current result type"""
        config = self._get_config()
        if (config.named_tuple):
            return RESULT_NAMEDTUPLE
        elif (config.dictionary):
            return RESULT_DICTIONARY
        else:
            return RESULT_TUPLE

    def setinputsizes(self, sizes: Sequence[Optional[int]]) -> None:
        """Predefine memory areas for parameters (no-op in this implementation)"""
        pass
        
    def setoutputsize(self, size: int, column: Optional[int] = None) -> None:
        """Set a column buffer size for fetches (no-op in this implementation)"""
        pass

    # Abstract methods that must be implemented by subclasses
    @abstractmethod
    def close(self):
        """Close the cursor"""
        pass

    @abstractmethod
    def execute(self, sql: str, data: Optional[Union[Sequence[Any], dict]] = None, buffered: Optional[bool] = None):
        """Execute a database query or command"""
        pass

    @abstractmethod
    def executemany(self, sql: str, data: Sequence[Union[Sequence[Any], dict]], buffered: Optional[bool] = None):
        """Execute a statement multiple times"""
        pass

    @abstractmethod
    def fetchone(self) -> Optional[Any]:
        """Fetch the next row"""
        pass

    @abstractmethod
    def fetchmany(self, size: Optional[int] = None) -> List[Any]:
        """Fetch the next set of rows"""
        pass

    @abstractmethod
    def fetchall(self) -> List[Any]:
        """Fetch all remaining rows"""
        pass

    @abstractmethod
    def callproc(self, procname: str, args: Sequence[Any] = ()) -> Sequence[Any]:
        """Call a stored procedure"""
        pass

    def nextset(self) -> Optional[bool]:
        """
        Move to the next available result set
        
        Useful when executing multiple statements or stored procedures
        that return multiple result sets.
        
        Returns:
            True if there is another result set, None if no more result sets
            
        Raises:
            ProgrammingError: If cursor is closed
        """
        self._check_closed()
        
        # Move to next completion
        self._completion_index += 1
        
        # Check if there are more completions
        if self._completion_index >= len(self._completions):
            return None
        
        # Process the next completion
        self._process_current_completion()
        return True

    def scroll(self, value: int, mode: str = "relative") -> None:
        """
        Scroll the cursor in the result set to a new position according to mode.

        If mode is "relative" (default), value is taken as offset to the
        current position in the result set, if set to absolute, value states
        an absolute target position.
        
        Args:
            value: Position value
            mode: "relative" or "absolute"
            
        Raises:
            ProgrammingError: If cursor has no result set or invalid parameters
        """
        # Allow scrolling in buffered results even if connection is closed
        if self._closed:
            raise ProgrammingError("Cursor is closed")
        if self.connection._closed and (self._result is None or self._result.streaming()):
            raise ProgrammingError("Cursor is closed")
        
        # Check if we have a result set
        if self._result is None:
            raise ProgrammingError("Cursor doesn't have a result set")
        
        if self._result.streaming():
            raise ProgrammingError("Scroll not supported for unbuffered cursors")
        
        # Validate mode
        if mode not in ("absolute", "relative"):
            raise ProgrammingError("Invalid or unknown scroll mode specified.")
        
        # Delegate to Result object's scroll method
        try:
            self._result.scroll(value, mode)
        except ValueError as e:
            raise ProgrammingError(str(e))
    
    def _seek(self, offset: int) -> None:
        """
        Move the cursor to the specified row position
        
        Internal helper method for absolute positioning.
        
        Args:
            offset: Absolute row position
            
        Raises:
            ProgrammingError: If cursor is closed
            ValueError: If no result set or unbuffered cursor
        """
        # Allow seeking in buffered results even if connection is closed
        if self._closed:
            raise ProgrammingError("Cursor is closed")
        if self.connection._closed and (self._result is None or self._result.streaming()):
            raise ProgrammingError("Cursor is closed")
        
        if self._result is None:
            raise ValueError("No result set")
        if self._result.streaming():
            raise ValueError("Seek not supported for unbuffered cursors")
        # For CompleteResult, use scroll with absolute mode
        self._result.scroll(offset, mode='absolute')

    @abstractmethod
    def __iter__(self):
        """Return iterator for cursor"""
        pass

    @abstractmethod
    def __next__(self) -> Any:
        """Return next row"""
        pass

    # Common helper methods (non-async, pure data transformation)
    
    def _escape_parameter(self, param: Any) -> str:
        """
        Escape parameter value based on server status flags and parameter type.
        
        Args:
            param: Parameter value to escape
            
        Returns:
            str: Properly escaped parameter string
        """
        if param is None:
            return 'NULL'
        
        # Check server status for escaping mode
        server_status = self.connection._client.context.server_status
        no_backslash_escapes = bool(server_status & NO_BACKSLASH_ESCAPES)
        
        # Handle different parameter types using match (Python 3.10+)
        match param:
            case str():
                return StringEscaper.escape_string_with_quotes(param, no_backslash_escapes)
            case bytes():
                return self._escape_bytes(param, no_backslash_escapes)
            case bool():
                # Handle boolean before int/float since bool is a subclass of int in Python
                return '1' if param else '0'
            case int() | float():
                return str(param)
            case datetime.datetime():
                # DATETIME: 'YYYY-MM-DD HH:MM:SS.ffffff'
                if param.microsecond:
                    return f"'{param.strftime('%Y-%m-%d %H:%M:%S')}.{param.microsecond:06d}'"
                else:
                    return f"'{param.strftime('%Y-%m-%d %H:%M:%S')}'"
            case datetime.date():
                # DATE: 'YYYY-MM-DD'
                return f"'{param.strftime('%Y-%m-%d')}'"
            case datetime.time():
                # TIME: 'HH:MM:SS.ffffff'
                if param.microsecond:
                    return f"'{param.strftime('%H:%M:%S')}.{param.microsecond:06d}'"
                else:
                    return f"'{param.strftime('%H:%M:%S')}'"
            case datetime.timedelta():
                # Convert timedelta to TIME format (can be negative)
                total_seconds = int(param.total_seconds())
                hours, remainder = divmod(abs(total_seconds), 3600)
                minutes, seconds = divmod(remainder, 60)
                microseconds = param.microseconds
                
                sign = '-' if total_seconds < 0 else ''
                if microseconds:
                    return f"'{sign}{hours:02d}:{minutes:02d}:{seconds:02d}.{microseconds:06d}'"
                else:
                    return f"'{sign}{hours:02d}:{minutes:02d}:{seconds:02d}'"
            case decimal.Decimal():
                # DECIMAL/NUMERIC: no quotes needed, just string representation
                return str(param)
            case _:
                # For other types, convert to string and escape
                return "'" + StringEscaper.escape_string_with_quotes(str(param), no_backslash_escapes) + "'"
    
    def _escape_bytes(self, value: bytes, no_backslash_escapes: bool) -> str:
        """
        Escape bytes value for binary data.
        
        Args:
            value: Bytes value to escape
            no_backslash_escapes: Whether NO_BACKSLASH_ESCAPES is set
            
        Returns:
            str: Escaped bytes as binary literal
        """
        # Convert bytes to hex representation
        hex_value = value.hex()
        
        if no_backslash_escapes:
            # Use X'...' format for hex literals when NO_BACKSLASH_ESCAPES is set
            return f"X'{hex_value.upper()}'"
        else:
            # Use _binary'...' format with proper escaping
            escaped_hex = hex_value.replace('\\', '\\\\').replace("'", "\\'")
            return f"_binary'{escaped_hex}'"
    
    def _process_completions(self, completions: List[Any]) -> None:
        """
        Process completions from client execution
        
        Args:
            completions: List of completion objects
        """
        # Store all completions for nextset() functionality
        self._completions = completions
        self._completion_index = 0
        
        if not completions:
            self._rowcount = 0
            self._affected_rows = 0
            self.description = None
            self._result = None
            return
        
        # Process the first completion
        self._process_current_completion()
    
    def _process_current_completion(self) -> None:
        """
        Process the current completion (at _completion_index)
        """
        if (self._completion_index >= len(self._completions)):
            return
            
        completion = self._completions[self._completion_index]
        # Check if it's a result set or update count
        if completion.has_result_set():
            # It's a result set (SELECT query)
            # For streaming/unbuffered results, rowcount should be 0 until rows are fetched
            # For buffered results, rowcount is the total number of rows
            if completion.result_set.streaming():
                self._rowcount = 0  # Unbuffered - don't know row count yet
            else:
                self._rowcount = completion.result_set.get_row_count()  # Buffered - we have all rows
            self._affected_rows = completion.affected_rows
            self._process_rows_set_completion(completion.result_set)
        else:
            # It's an update count (INSERT/UPDATE/DELETE)
            self.description = None
            self._affected_rows = completion.affected_rows
            self._rowcount = completion.affected_rows
            self._result = None
            self.lastrowid = completion.insert_id is not None and completion.insert_id > 0 and completion.insert_id or None
    
    def _process_rows_set_completion(self, result_set: Result) -> None:
        """
        Process a result set completion
        
        Args:
            result_set: Result set completion object
        """
        self._result = result_set
        columns = result_set.columns
        
        # Extract column information for description
        description = []
        
        for col in columns:
            # Determine column type (override for JSON)
            col_type = JSON if col.ext_type_format == 'json' else col.column_type
            
            # Add NUM_FLAG for numeric types
            col_flags = col.flags
            if (col_type <= INT24 and (col_type != TIMESTAMP or col.column_length in (14, 8)) or 
                col_type in (YEAR, NEWDECIMAL, DECIMAL)):
                col_flags |= NUM_FLAG
            
            # Calculate display_length and packed_len
            max_char_len = self._get_charset_max_length(col.character_set)
            if max_char_len and max_char_len > 1:
                packed_len = col.column_length
                display_length = col.column_length // max_char_len
            else:
                packed_len = -1
                display_length = col.column_length
            
            # Handle decimal fields special case
            if col.decimals and col.decimals < 31:
                precision = col.column_length
                decimals = col.decimals
                display_length = precision + 1
            else:
                precision = 0
                decimals = col.decimals
            
            description.append((
                col.name, col_type, display_length, packed_len,
                precision, decimals, not (col_flags & 1), col_flags,
                col.table, col.org_name, col.org_table
            ))
        
        self.description = tuple(description) if description else None
    
    def _process_executemany_completions(self, completions: List[Any]) -> None:
        """
        Process completions from executemany - aggregate result sets with compatible metadata
        """
        if not completions:
            self.description = None
            self._result = None
            return
        
        # Find completions with result sets
        result_set_completions = [c for c in completions if c.has_result_set()]
        
        if not result_set_completions:
            first_completion = completions[0]
            affected = getattr(first_completion, 'affected_rows', 0)
            self._affected_rows = affected
            self._rowcount = affected
            self.description = None
            self._result = None
            return
        
        # Check if all result sets have compatible metadata
        first_rs = result_set_completions[0].get_result_set()
        if hasattr(first_rs, 'columns'):
            first_columns = first_rs.columns
        else:
            first_columns = first_rs.get('columns', [])
        
        compatible_completions = []
        for completion in result_set_completions:
            rs = completion.get_result_set()
            columns = rs.columns if hasattr(rs, 'columns') else rs.get('columns', [])
            if self._are_columns_compatible(first_columns, columns):
                compatible_completions.append(completion)
        
        if compatible_completions:
            aggregated_rows = []
            for completion in compatible_completions:
                rs = completion.get_result_set()
                rows = rs.rows if hasattr(rs, 'rows') else rs.get('rows', [])
                aggregated_rows.extend(rows)
            
            self.description = self._build_description(first_columns)
            self._result = CompleteResult(
                columns=first_columns,
                column_count=len(first_columns),
                config=self._get_config(),
                rows=aggregated_rows,
                is_binary=False
            )
            self._rowcount = len(aggregated_rows)
            self._affected_rows = sum(c.affected_rows for c in result_set_completions if hasattr(c, 'affected_rows'))
        else:
            first_rs = result_set_completions[0].get_result_set()
            first_columns = first_rs.columns if hasattr(first_rs, 'columns') else first_rs.get('columns', [])
            first_rows = first_rs.rows if hasattr(first_rs, 'rows') else first_rs.get('rows', [])
            
            self.description = self._build_description(first_columns)
            self._result = CompleteResult(
                columns=first_columns,
                column_count=len(first_columns),
                config=self._get_config(),
                rows=first_rows,
                is_binary=False
            )
            self._rowcount = len(first_rows)
            self._affected_rows = first_rs.affected_rows if hasattr(first_rs, 'affected_rows') else 0
    
    def _are_columns_compatible(self, columns1: List[ColumnDefinitionPacket], columns2: List[ColumnDefinitionPacket]) -> bool:
        """Check if two column definitions are compatible for aggregation"""
        if len(columns1) != len(columns2):
            return False
        
        for col1, col2 in zip(columns1, columns2):
            if (col1.name != col2.name or 
                col1.column_type != col2.column_type):
                return False
        
        return True
    
    def _build_description(self, columns: List[ColumnDefinitionPacket]) -> Optional[tuple]:
        """Build cursor description tuple from column definitions"""
        if not columns:
            return None
        
        description = []
        for col in columns:
            # Determine column type (override for JSON)
            col_type = JSON if col.ext_type_format == 'json' else col.column_type
            
            # Add NUM_FLAG for numeric types
            col_flags = col.flags
            if (col_type <= INT24 and (col_type != TIMESTAMP or col.column_length in (14, 8)) or 
                col_type in (YEAR, NEWDECIMAL, DECIMAL)):
                col_flags |= NUM_FLAG
            
            # Calculate display_length and packed_len
            max_char_len = self._get_charset_max_length(col.character_set)
            if max_char_len and max_char_len > 1:
                packed_len = col.column_length
                display_length = col.column_length // max_char_len
            else:
                packed_len = -1
                display_length = col.column_length
            
            # Handle decimal fields special case
            if col.decimals and col.decimals < 31:
                precision = col.column_length
                decimals = col.decimals
                display_length = precision + 1
            else:
                precision = 0
                decimals = col.decimals
            
            description.append((
                col.name, col_type, display_length, packed_len,
                precision, decimals, not (col_flags & 1), col_flags,
                col.table, col.org_name, col.org_table
            ))
        
        return tuple(description)
    
    def _create_named_tuple_class(self, columns: List[ColumnDefinitionPacket]) -> type:
        """Create a namedtuple class from column definitions"""
        if not columns:
            return namedtuple('Row', [])
        
        field_names = []
        for column in columns:
            name = column.name or column.org_name
            if not name or not name.isidentifier():
                name = f'column_{len(field_names)}'
            original_name = name
            counter = 1
            while name in field_names:
                name = f'{original_name}_{counter}'
                counter += 1
            field_names.append(name)
        
        return namedtuple('Row', field_names)
    
    def _convert_rows_to_named_tuples(self, rows: List[tuple], columns: List[ColumnDefinitionPacket]) -> List[Any]:
        """Convert regular tuples to named tuples"""
        if not rows or not columns:
            return rows
        
        RowClass = self._create_named_tuple_class(columns)
        return [RowClass(*row) for row in rows]
    
    def _convert_rows_to_dictionaries(self, rows: List[tuple], columns: List[ColumnDefinitionPacket]) -> List[Dict]:
        """Convert regular tuples to dictionaries"""
        if not rows or not columns:
            return rows
        
        field_names = []
        for column in columns:
            name = column.name or column.org_name
            if not name:
                name = f'column_{len(field_names)}'
            field_names.append(name)
        
        return [dict(zip(field_names, row)) for row in rows]
    
    def _apply_row_formatting(self, rows: List[Any]) -> List[Any]:
        """Apply row formatting (named_tuple or dictionary) based on configuration"""
        if not rows:
            return rows
        
        config = self._get_config()
        columns = self._result.columns if self._result else []
        
        if config.named_tuple and columns:
            return self._convert_rows_to_named_tuples(rows, columns)
        elif config.dictionary and columns:
            return self._convert_rows_to_dictionaries(rows, columns)
        
        return rows
    
    def _get_charset_max_length(self, charset_id: int) -> int:
        """Get maximum character length for a charset ID"""
        charset_max_lengths = {
            1: 2, 8: 1, 28: 2, 33: 3, 45: 4, 46: 4, 63: 1, 77: 1, 
            224: 4, 225: 4, 226: 4, 227: 4, 228: 4, 229: 4, 230: 4, 231: 4,
            232: 4, 233: 4, 234: 4, 235: 4, 236: 4, 237: 4, 238: 4, 239: 4,
            240: 4, 241: 4, 242: 4, 243: 4, 244: 4, 245: 4, 246: 4, 247: 4,
            248: 4, 249: 4, 250: 4, 255: 4
        }
        return charset_max_lengths.get(charset_id)
    
    def _process_callproc_completions(self, completions: List[Any]) -> None:
        """Process completions from callproc execution"""
        self._completions = completions
        self._completion_index = 0
        
        if not completions:
            self.description = None
            self._result = None
            self._rowcount = 0
            self._affected_rows = 0
            return
        
        self._process_current_completion()
    
    @property
    def metadata(self) -> Optional[Dict[str, tuple]]:
        """Get metadata information for result set columns"""
        self._check_closed()
        
        if not self.description:
            return None
        
        if not hasattr(self, '_completions') or not self._completions:
            return None
        
        completion = self._completions[self._completion_index]
        if not hasattr(completion, 'result_set') or not completion.result_set:
            return None
        
        result_set = completion.result_set
        columns: List[ColumnDefinitionPacket] = result_set.columns if hasattr(result_set, 'columns') else []
        
        if not columns:
            return None
        
        # Build metadata tuples
        catalog_tuple = tuple(col.catalog for col in columns)
        schema_tuple = tuple(col.schema for col in columns)  
        field_tuple = tuple(col.name for col in columns)
        org_field_tuple = tuple(col.org_name for col in columns)
        table_tuple = tuple(col.table for col in columns)
        org_table_tuple = tuple(col.org_table for col in columns)
        type_tuple = tuple(col.column_type for col in columns)
        charset_tuple = tuple(col.character_set for col in columns)
        length_tuple = tuple(col.column_length for col in columns)
        max_length_tuple = tuple(col.column_length for col in columns)
        decimals_tuple = tuple(col.decimals for col in columns)
        flags_tuple = tuple(col.flags for col in columns)
        
        # Calculate extended field type
        ext_type_list = []
        for col in columns:
            ext_field_type = EXT_FIELD_TYPE.NONE
            if col.ext_type_format:
                ext_format_lower = col.ext_type_format.lower()
                if ext_format_lower == 'json':
                    ext_field_type = EXT_FIELD_TYPE.JSON
            
            if col.ext_type_name:
                ext_name_lower = col.ext_type_name.lower()
                if ext_name_lower == 'json':
                    ext_field_type = EXT_FIELD_TYPE.JSON
                elif ext_name_lower == 'uuid':
                    ext_field_type = EXT_FIELD_TYPE.UUID
                elif ext_name_lower == 'inet4':
                    ext_field_type = EXT_FIELD_TYPE.INET4
                elif ext_name_lower == 'inet6':
                    ext_field_type = EXT_FIELD_TYPE.INET6
                elif ext_name_lower == 'point':
                    ext_field_type = EXT_FIELD_TYPE.POINT
                elif ext_name_lower == 'multipoint':
                    ext_field_type = EXT_FIELD_TYPE.MULTIPOINT
                elif ext_name_lower == 'linestring':
                    ext_field_type = EXT_FIELD_TYPE.LINESTRING
                elif ext_name_lower == 'multilinestring':
                    ext_field_type = EXT_FIELD_TYPE.MULTILINESTRING
                elif ext_name_lower == 'polygon':
                    ext_field_type = EXT_FIELD_TYPE.POLYGON
                elif ext_name_lower == 'multipolygon':
                    ext_field_type = EXT_FIELD_TYPE.MULTIPOLYGON
                elif ext_name_lower == 'geometrycollection':
                    ext_field_type = EXT_FIELD_TYPE.GEOMETRYCOLLECTION
            
            ext_type_list.append(ext_field_type)
        
        ext_type_tuple = tuple(ext_type_list)
        
        return {
            'catalog': catalog_tuple,
            'schema': schema_tuple,
            'field': field_tuple,
            'org_field': org_field_tuple,
            'table': table_tuple,
            'org_table': org_table_tuple,
            'type': type_tuple,
            'charset': charset_tuple,
            'length': length_tuple,
            'max_length': max_length_tuple,
            'decimals': decimals_tuple,
            'flags': flags_tuple,
            'ext_type_or_format': ext_type_tuple
        }
