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

import datetime
import decimal
from numbers import Number
from collections import namedtuple
from typing import Sequence, Optional, List, Any, Union, Dict

from .exceptions import DatabaseError, ProgrammingError, NotSupportedError, OperationalError
from .impl.message.client.query_packet import QueryPacket
from .impl.result import CompleteResult
from .impl.string_utils import StringEscaper
from .impl.client.exception_factory import ExceptionFactory
from mariadb_shared.constants.STATUS import NO_BACKSLASH_ESCAPES
from mariadb_shared.constants import EXT_FIELD_TYPE
from mariadb_shared.constants.FIELD_TYPE import (
    INT24, TIMESTAMP, YEAR, NEWDECIMAL, DECIMAL, JSON
)
from mariadb_shared.constants.FIELD_FLAG import NUMERIC as NUM_FLAG

# Forward reference to avoid circular import
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .connections import Connection

PARAMSTYLE_QMARK = 1
PARAMSTYLE_FORMAT = 2

ROWS_ALL = -1

RESULT_TUPLE = 0
RESULT_NAMEDTUPLE = 1
RESULT_DICTIONARY = 2

# Command types
SQL_NONE = 0,
SQL_INSERT = 1
SQL_UPDATE = 2
SQL_REPLACE = 3
SQL_DELETE = 4
SQL_CALL = 5
SQL_DO = 6
SQL_SELECT = 7
SQL_OTHER = 255

ROWS_EOF = -1

class Cursor:
    """
    MariaDB Cursor Object
    """

    def __init__(self, connection: 'Connection', **kwargs):
        """
        Initialize cursor with a connection
        
        Args:
            connection: Database connection
            **kwargs: Cursor options (buffered, named_tuple, dictionary, etc.)
        """
        self.connection: 'Connection' = connection
        self._closed: bool = False
        self.arraysize: int = 1
        self.rowcount: int = -1
        self.description: Optional[List[Any]] = None
        self.lastrowid: Optional[int] = None
        self._completions: List[Any] = []  # Store all completions for nextset()
        self._completion_index: int = 0    # Current completion index
        self._cursor_config = None  # Will be set by connection if cursor options are provided
        self._exception_factory = ExceptionFactory()  # For consistent error handling
        
        # Result object state
        self._buffered: bool = kwargs.pop('buffered', True)  # Default is buffered
        self._result: Optional[Any] = None  # Active Result object (CompleteResult or StreamingResult)
        
        if kwargs:
            # create a clone of the connection configuration
            self._cursor_config = self.connection._configuration.from_dict(self.connection._configuration.to_dict())
            
            rtype = kwargs.pop("named_tuple", False)
            if rtype:
                self._cursor_config.named_tuple = rtype
            else:
                rtype = kwargs.pop("dictionary", False)
                if rtype:
                    self._cursor_config.dictionary = rtype
            
            # Handle native_object option
            native_obj = kwargs.pop("native_object", None)
            if native_obj is not None:
                self._cursor_config.native_object = bool(native_obj)

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
        """
        Get the number of warnings from the last executed statement
        
        Returns:
            Number of warnings, or 0 if there are no warnings
        """
        # Get warning count from the current completion
        if (hasattr(self, '_completions') and self._completions and 
            self._completion_index < len(self._completions)):
            completion = self._completions[self._completion_index]
            return getattr(completion, 'warning_count', 0)
        return 0

    def close(self) -> None:
        """Close the cursor"""
        if not self._closed:
            # Consume any remaining streaming results
            if self._result is not None and self._result.streaming():
                try:
                    self._result.fetch_remaining()
                except Exception:
                    pass  # Ignore errors during close
            
            self._closed = True
            self.arraysize = 1
            self.rowcount = -1
            self.description = None
            self.lastrowid = None
            self._completions = []  # Store all completions for nextset()
            self._completion_index = 0    # Current completion index
            self._cursor_config = None
            self._result = None 
        
    def execute(self, sql: str, data: Optional[Union[Sequence[Any], dict]] = None, buffered: Optional[bool] = None) -> None:
        """
        Execute a database query or command
        
        Args:
            sql: SQL statement to execute
            data: Optional parameters for the statement
            buffered: Override cursor's buffered setting for this execution
        """
        self._check_closed()
        
        # Consume any pending streaming results before executing new query
        if self._result is not None and self._result.streaming():
            self._result.fetch_remaining()
        
        if (not sql):
            self._process_completions(None)
            return
        try:
            
            # Convert data to list format for parameter binding
            parameters = None
            if data:
                if isinstance(data, (list, tuple)):
                    parameters = list(data)
                elif isinstance(data, dict):
                    # For named parameters, we'd need to convert SQL from :name to ? format
                    # For now, raise an error to indicate this needs implementation
                    raise NotSupportedError("Named parameters not yet implemented with enhanced parameter binding")
            
            # Create query packet with direct parameter binding (no string substitution!)
            query_packet = QueryPacket(sql, parameters)
            # Use provided buffered parameter or fall back to cursor default
            effective_buffered = buffered if buffered is not None else self._buffered
            completions = self.connection._client.execute(query_packet, config=self._get_config(), can_redo=False, buffered=effective_buffered)
            
            # Process the completions to extract result data
            self._process_completions(completions)
        except DatabaseError as e:
            raise e                
        except Exception as e:
            raise self._exception_factory.create_exception(
                f"Execute failed: {e}",
                errno=2013,
                sql_state='HY000'
            )
        
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
            self.rowcount = 0
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
        if completion.is_result_set:
            # It's a result set
            self._process_rows_set_completion(completion)
        else:
            # It's an update count
            self.rowcount = completion.affected_rows
            self.description = None
            self._result = None
            self.lastrowid = completion.insert_id is not None and completion.insert_id > 0 and completion.insert_id or None
       
    
    def _process_rows_set_completion(self, completion: Any) -> None:
        """
        Process a result set completion
        
        Args:
            completion: Result set completion object
        """
        try:
            # Extract result set from completion
            if hasattr(completion, 'result_set') and completion.result_set:
                result_set = completion.result_set
                
                # Check if it's a Result object (CompleteResult or StreamingResult)
                if hasattr(result_set, 'streaming'):
                    # New Result object approach
                    self._result = result_set
                    columns = result_set.columns
                    self.rowcount = result_set.get_row_count()
                else:
                    # Legacy dict format - wrap in CompleteResult for consistency
                    rows = result_set.get('rows', [])
                    columns = result_set.get('columns', [])
                    
                    # Don't format here - will be formatted in fetchone()
                    # Create CompleteResult to wrap legacy data
                    self._result = CompleteResult(
                        columns=columns,
                        column_count=len(columns),
                        config=self._get_config(),
                        rows=rows,
                        is_binary=False
                    )
                    self.rowcount = len(rows)
                
                # Extract column information for description
                description = []
                
                for col in columns:
                    # Create description tuple to match C extension: 
                    # (name, type, display_length, packed_len, precision, decimals, nullable, flags, table, org_name, org_table)
                    col_name = col.get('name', 'unknown')
                    col_type = col.get('column_type', 253)  # Default to VARCHAR
                    if (col['ext_type_format'] == 'json'):
                        col_type = JSON
                    col_length = col.get('column_length', 0)
                    col_flags = col.get('flags', 0)
                    col_decimals = col.get('decimals', 0)
                    col_charset = col.get('character_set', 63)  # Default to binary charset
                    col_table = col.get('table', '')
                    col_org_name = col.get('org_name', '')
                    col_org_table = col.get('org_table', '')
                    
                    if (col_type <= INT24 and (col_type != TIMESTAMP or col_length == 14 or col_length == 8) or col_type == YEAR or col_type== NEWDECIMAL or col_type == DECIMAL):
                        col_flags |= NUM_FLAG

                    # Check if column is nullable (flag bit 0 = NOT NULL)
                    nullable = not (col_flags & 1)
                    
                    # Calculate display_length and packed_len following C extension logic
                    # Use max_length if available, otherwise use length
                    display_length = col_length  # We don't have max_length in our implementation
                    packed_len = 0
                    precision = 0
                    decimals = col_decimals
                    
                    # Handle charset-specific display length calculation
                    max_char_len = self._get_charset_max_length(col_charset)
                    if max_char_len and max_char_len > 1:
                        packed_len = display_length
                        display_length = display_length // max_char_len
                    else:
                        # For single-byte charsets, packed_len would be from pack_len table
                        # We'll use a simplified approach
                        packed_len = -1
                    
                    # Handle decimal fields special case
                    if col_decimals and col_decimals < 31:
                        decimals = col_decimals
                        precision = col_length
                        display_length = precision + 1
                    
                    description.append((
                        col_name,           # name
                        col_type,           # type
                        display_length,     # display_length
                        packed_len,         # packed_len
                        precision,          # precision
                        decimals,           # decimals
                        nullable,           # nullable
                        col_flags,          # flags
                        col_table,          # table
                        col_org_name,       # org_name
                        col_org_table       # org_table
                    ))
                
                self.description = tuple(description) if description else None
            else:
                # No result set data available
                self._result = None
                self.rowcount = 0
                self.description = None

            
        except Exception as e:
            raise self._exception_factory.create_exception(
                f"Failed to process result set: {e}",
                errno=2013,
                sql_state='HY000'
            )
    
    def _process_executemany_completions(self, completions: List[Any]) -> None:
        """
        Process completions from executemany - aggregate result sets with compatible metadata
        
        Args:
            completions: List of completion objects from multiple executions
        """
        if not completions:
            self.description = None
            self._result = None
            return
        
        # Find completions with result sets
        result_set_completions = [c for c in completions if c.has_result_set()]
        
        if not result_set_completions:
            # No result sets - just use the first completion for metadata
            first_completion = completions[0]
            self.rowcount = getattr(first_completion, 'affected_rows', 0)
            self.description = None
            self._result = None
            return
        
        # Check if all result sets have compatible metadata (same columns)
        first_rs = result_set_completions[0].get_result_set()
        # Get columns from Result object or legacy dict
        if hasattr(first_rs, 'columns'):
            first_columns = first_rs.columns
        else:
            first_columns = first_rs.get('columns', [])
        
        compatible_completions = []
        for completion in result_set_completions:
            rs = completion.get_result_set()
            # Get columns from Result object or legacy dict
            if hasattr(rs, 'columns'):
                columns = rs.columns
            else:
                columns = rs.get('columns', [])
            
            # Check if columns are compatible (same count and types)
            if self._are_columns_compatible(first_columns, columns):
                compatible_completions.append(completion)
        
        if compatible_completions:
            # Aggregate rows from all compatible result sets
            aggregated_rows = []
            
            for completion in compatible_completions:
                rs = completion.get_result_set()
                # Get rows from Result object or legacy dict
                if hasattr(rs, 'rows'):
                    rows = rs.rows
                else:
                    rows = rs.get('rows', [])
                aggregated_rows.extend(rows)
            
            # Set up cursor state with aggregated data
            self.description = self._build_description(first_columns)
            self._result = CompleteResult(
                columns=first_columns,
                column_count=len(first_columns),
                config=self._get_config(),
                rows=aggregated_rows,
                is_binary=False
            )
            self.rowcount = len(aggregated_rows)
        else:
            # Fallback to first result set if no compatible ones found
            first_rs = result_set_completions[0].get_result_set()
            # Get columns and rows from Result object or legacy dict
            if hasattr(first_rs, 'columns'):
                first_columns = first_rs.columns
                first_rows = first_rs.rows
            else:
                first_columns = first_rs.get('columns', [])
                first_rows = first_rs.get('rows', [])
            
            self.description = self._build_description(first_columns)
            self._result = CompleteResult(
                columns=first_columns,
                column_count=len(first_columns),
                config=self._get_config(),
                rows=first_rows,
                is_binary=False
            )
            self.rowcount = len(first_rows)
    
    def _are_columns_compatible(self, columns1: List[Dict], columns2: List[Dict]) -> bool:
        """
        Check if two column definitions are compatible for aggregation
        
        Args:
            columns1: First set of column definitions
            columns2: Second set of column definitions
            
        Returns:
            True if columns are compatible (same count, names, and types)
        """
        if len(columns1) != len(columns2):
            return False
        
        for col1, col2 in zip(columns1, columns2):
            # Check column name and type compatibility
            if (col1.get('name') != col2.get('name') or 
                col1.get('column_type') != col2.get('column_type')):
                return False
        
        return True
    
    def _build_description(self, columns: List[Dict]) -> Optional[tuple]:
        """
        Build cursor description tuple from column definitions
        
        Args:
            columns: List of column definition dictionaries
            
        Returns:
            Tuple of column descriptions or None if no columns
        """
        if not columns:
            return None
        
        description = []
        for column in columns:
            name = column.get('name', '')
            column_type = column.get('column_type', 0)
            display_size = column.get('display_size')
            internal_size = column.get('internal_size', 0)
            precision = column.get('precision', 0)
            scale = column.get('scale', 0)
            nullable = not bool(column.get('flags', 0) & 1)  # NOT_NULL flag
            
            description.append((
                name,           # name
                column_type,    # type_code
                display_size,   # display_size
                internal_size,  # internal_size
                precision,      # precision
                scale,          # scale
                nullable        # null_ok
            ))
        
        return tuple(description)
    
    def _create_named_tuple_class(self, columns: List[Dict]) -> type:
        """
        Create a namedtuple class from column definitions
        
        Args:
            columns: List of column definition dictionaries
            
        Returns:
            namedtuple class
        """
        if not columns:
            return namedtuple('Row', [])
        
        # Extract column names, using name if available, otherwise org_name
        field_names = []
        for column in columns:
            name = column.get('name', '') or column.get('org_name', '')
            # Ensure valid Python identifier
            if not name or not name.isidentifier():
                name = f'column_{len(field_names)}'
            # Handle duplicate names
            original_name = name
            counter = 1
            while name in field_names:
                name = f'{original_name}_{counter}'
                counter += 1
            field_names.append(name)
        
        return namedtuple('Row', field_names)
    
    def _convert_rows_to_named_tuples(self, rows: List[tuple], columns: List[Dict]) -> List[Any]:
        """
        Convert regular tuples to named tuples
        
        Args:
            rows: List of tuple rows
            columns: List of column definitions
            
        Returns:
            List of named tuple rows
        """
        if not rows or not columns:
            return rows
        
        RowClass = self._create_named_tuple_class(columns)
        return [RowClass(*row) for row in rows]
    
    def _convert_rows_to_dictionaries(self, rows: List[tuple], columns: List[Dict]) -> List[Dict]:
        """
        Convert regular tuples to dictionaries
        
        Args:
            rows: List of tuple rows
            columns: List of column definitions
            
        Returns:
            List of dictionary rows
        """
        if not rows or not columns:
            return rows
        
        # Extract column names
        field_names = []
        for column in columns:
            name = column.get('name', '') or column.get('org_name', '')
            if not name:
                name = f'column_{len(field_names)}'
            field_names.append(name)
        
        return [dict(zip(field_names, row)) for row in rows]
        
    def executemany(self, sql: str, data: Sequence[Union[Sequence[Any], dict]], buffered: Optional[bool] = None) -> None:
        """
        Execute a statement multiple times with different parameter sets
        
        Args:
            sql: SQL statement to execute
            data: Sequence of parameter sequences
            buffered: Override cursor's buffered setting for this execution
        """
        self._check_closed()
        
        if not data:
            return
        
        # Reset result state
        self.description = None
        self._result = None
        total_affected = 0
        lastrowid = None
        
        try:
            completions = list()
            # Execute the statement for each parameter set
            for params in data:
                # Execute with current parameter set
                # Convert data to list format for parameter binding
                parameters = None
                if params:
                    if isinstance(params, (list, tuple)):
                        parameters = list(params)
                    elif isinstance(params, dict):
                        raise NotSupportedError("Named parameters not yet implemented")
                
                # Create query packet and execute
                query_packet = QueryPacket(sql, parameters)
                # Use provided buffered parameter or fall back to cursor default
                effective_buffered = buffered if buffered is not None else self._buffered
                compl = self.connection._client.execute(query_packet, config=self._get_config(), can_redo=False, buffered=effective_buffered)
                completions.extend(compl)
                for c in compl:
                    if c.affected_rows >= 0:
                        total_affected += c.affected_rows
                    if c.insert_id is not None and c.insert_id > 0:
                        lastrowid = c.insert_id

            # Process the completions - aggregate result sets with compatible metadata
            self._process_executemany_completions(completions)
            
            # Accumulate affected rows from all completions

            # Set final rowcount to total affected rows
            self.rowcount = total_affected           
            self.lastrowid = lastrowid is not None and lastrowid > 0 and lastrowid or None

        except DatabaseError as e:
            raise e            
        except Exception as e:
            raise self._exception_factory.create_exception(
                f"ExecuteMany failed: {e}",
                errno=2013,
                sql_state='HY000'
            )
        
    def fetchone(self) -> Optional[Any]:
        """Fetch the next row of a query result set"""
        # Allow fetching from buffered results even if connection is closed
        if self._closed:
            raise ProgrammingError("Cursor is closed")
        if self.connection._closed and (self._result is None or self._result.streaming()):
            raise ProgrammingError("Cursor is closed")
        
        # DB-API 2.0: Raise error if no result set (description is None)
        if self.description is None:
            raise ProgrammingError("No result set to fetch from")
        
        # Delegate to Result object
        if self._result is not None:
            row = self._result.fetch_one()
            if row is not None:
                # Apply row formatting
                row = self._apply_row_formatting([row])[0]
            return row
        
        return None

    def _seek(self, offset: int) -> None:
        """Move the cursor to the specified row"""
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
        
    def fetchmany(self, size: Optional[int] = None) -> List[Any]:
        """Fetch the next set of rows of a query result"""
        # Allow fetching from buffered results even if connection is closed
        if self._closed:
            raise ProgrammingError("Cursor is closed")
        if self.connection._closed and (self._result is None or self._result.streaming()):
            raise ProgrammingError("Cursor is closed")
        
        # DB-API 2.0: Raise error if no result set (description is None)
        if self.description is None:
            raise ProgrammingError("No result set to fetch from")
        
        if size is None:
            size = self.arraysize
        result = []
        for _ in range(size):
            row = self.fetchone()
            if row is None:
                break
            result.append(row)
        return result
        
    def fetchall(self) -> List[Any]:
        """Fetch all remaining rows of a query result"""
        # Allow fetching from buffered results even if connection is closed
        if self._closed:
            raise ProgrammingError("Cursor is closed")
        if self.connection._closed and (self._result is None or self._result.streaming()):
            raise ProgrammingError("Cursor is closed")
        
        # DB-API 2.0: Raise error if no result set (description is None)
        if self.description is None:
            raise ProgrammingError("No result set to fetch from")
        
        # Delegate to Result object
        if self._result is not None:
            rows = self._result.fetch_all()
            return self._apply_row_formatting(rows)
        
        return []
        
    def nextset(self) -> Optional[bool]:
        """Skip to the next available result set"""
        self._check_closed()
        
        # Move to next completion
        self._completion_index += 1
        
        # Check if there are more completions
        if self._completion_index >= len(self._completions):
            return None
        
        # Process the next completion
        self._process_current_completion()
        return True
    
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
        
    def setinputsizes(self, sizes: Sequence[Optional[int]]) -> None:
        """Predefine memory areas for parameters (no-op in this implementation)"""
        pass
        
    def setoutputsize(self, size: int, column: Optional[int] = None) -> None:
        """Set a column buffer size for fetches (no-op in this implementation)"""
        pass
        
    def __iter__(self) -> 'Cursor':
        """Return iterator for cursor"""
        return self
        
    def __next__(self) -> Any:
        """Return next row"""
        row = self.fetchone()
        if row is None:
            raise StopIteration
        return row
    
    def callproc(self, procname: str, args: Sequence[Any] = ()) -> Sequence[Any]:
        """
        Call a stored procedure with the given name and arguments
        
        Args:
            procname: Name of the stored procedure
            args: Sequence of arguments for the procedure
            
        Returns:
            Sequence of arguments (modified for output parameters)
        """
        self._check_closed()
        
        try:
            # Build CALL statement with placeholders
            placeholders = ', '.join(['?' for _ in args])
            call_sql = f"CALL {procname}({placeholders})"
            
            # Prepare the statement
            stmt = self.connection._client.prepare_statement(call_sql)
            
            try:
                # Execute with parameters using ExecutePacket
                from .impl.message.client.execute_packet import ExecutePacket
                execute_packet = ExecutePacket(stmt.statement_id, list(args), call_sql)
                completions = self.connection._client.execute(execute_packet, config=self._get_config(), can_redo=False)
                
                # Process all completions
                self._process_callproc_completions(completions)
                
                return None  # Match C extension behavior
                
            finally:
                # Always close the prepared statement
                self.connection._client.close_prepared_statement(stmt)
        except DatabaseError as e:
            raise e                            
        except Exception as e:
            raise self._exception_factory.create_exception(
                f"CallProc failed: {e}",
                errno=2013,
                sql_state='HY000'
            )
    
    def _process_callproc_completions(self, completions: List[Any]) -> None:
        """
        Process completions from callproc execution
        
        Args:
            completions: List of completion objects from procedure call
        """
        # Store all completions for nextset() functionality
        self._completions = completions
        self._completion_index = 0
        
        if not completions:
            # No result sets with data
            self.description = None
            self._result = None
            self.rowcount = 0
            return
        
        # Process the current completion
        self._process_current_completion()
    
    @property
    def sp_outparams(self) -> bool:
        """
        Check if current result set contains output parameters
        
        Returns:
            True if current result set is output parameters, False otherwise
        """
        if (self._completions and 
            self._completion_index < len(self._completions)):
            completion = self._completions[self._completion_index]
            return getattr(completion, 'is_output_parameters', False)
        return False
        
    @property
    def affected_rows(self) -> int:
        """
        alias for rowcount
        
        Returns:
            rowcount changed by last execution
        """
        return int(self.rowcount)


    def nextset(self) -> Optional[bool]:
        """
        Move to the next result set
        
        Returns:
            True if there are more result sets, False if no more, None if not supported
        """
        self._check_closed()
        
        if not hasattr(self, '_completions') or not self._completions:
            return None
        
        # Move to next completion
        self._completion_index += 1
        
        if self._completion_index >= len(self._completions):
            return False
        
        # Process the next completion
        self._process_current_completion()
        return True
    
    def _get_charset_max_length(self, charset_id: int) -> int:
        """
        Get maximum character length for a charset ID based on MariaDB charset encoding lengths
        
        Args:
            charset_id: MySQL/MariaDB charset ID
            
        Returns:
            Maximum bytes per character for the charset, or None if unknown
        """
        # Key charset encoding lengths from MariaDB Java connector (truncated for space)
        charset_max_lengths = {
            1: 2, 8: 1, 28: 2, 33: 3, 45: 4, 46: 4, 63: 1, 77: 1, 
            224: 4, 225: 4, 226: 4, 227: 4, 228: 4, 229: 4, 230: 4, 231: 4,
            232: 4, 233: 4, 234: 4, 235: 4, 236: 4, 237: 4, 238: 4, 239: 4,
            240: 4, 241: 4, 242: 4, 243: 4, 244: 4, 245: 4, 246: 4, 247: 4,
            248: 4, 249: 4, 250: 4, 255: 4
        }
        return charset_max_lengths.get(charset_id)
    
    @property
    def metadata(self) -> Optional[Dict[str, tuple]]:
        """
        Get metadata information for result set columns
        
        Returns:
            Dictionary with column metadata or None if no result set
        """
        self._check_closed()
        
        if not self.description:
            return None
        
        # Extract column information from the current result set
        if not hasattr(self, '_completions') or not self._completions:
            return None
        
        completion = self._completions[self._completion_index]
        if not hasattr(completion, 'result_set') or not completion.result_set:
            return None
        
        # Get columns from Result object or legacy dict
        result_set = completion.result_set
        if hasattr(result_set, 'columns'):
            columns = result_set.columns
        else:
            columns = result_set.get('columns', [])
        
        if not columns:
            return None
        
        field_count = len(columns)
        
        # Initialize tuples for each metadata field
        catalog_tuple = tuple(col.get('catalog', '') for col in columns)
        schema_tuple = tuple(col.get('schema', '') for col in columns)  
        field_tuple = tuple(col.get('name', '') for col in columns)
        org_field_tuple = tuple(col.get('org_name', '') for col in columns)
        table_tuple = tuple(col.get('table', '') for col in columns)
        org_table_tuple = tuple(col.get('org_table', '') for col in columns)
        type_tuple = tuple(col.get('column_type', 0) for col in columns)
        charset_tuple = tuple(col.get('character_set', 0) for col in columns)
        length_tuple = tuple(col.get('column_length', 0) for col in columns)
        max_length_tuple = tuple(col.get('column_length', 0) for col in columns)  # We don't have max_length, use length
        decimals_tuple = tuple(col.get('decimals', 0) for col in columns)
        flags_tuple = tuple(col.get('flags', 0) for col in columns)
        
        # Calculate extended field type dynamically based on ext_type_name or ext_type_format
        ext_type_list = []
        for col in columns:
            ext_field_type = EXT_FIELD_TYPE.NONE
            
            ext_type_format = col.get('ext_type_format')
            ext_type_name = col.get('ext_type_name')
            
            if ext_type_format:
                ext_format_lower = ext_type_format.lower()
                if ext_format_lower == 'json':
                    ext_field_type = EXT_FIELD_TYPE.JSON
            
            if ext_type_name:
                ext_name_lower = ext_type_name.lower()
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
    
    def _apply_row_formatting(self, rows: List[Any]) -> List[Any]:
        """
        Apply row formatting (named_tuple or dictionary) based on configuration
        
        Args:
            rows: List of row tuples
            
        Returns:
            Formatted rows
        """
        if not rows:
            return rows
        
        config = self._get_config()
        columns = self._result.columns if self._result else []
        
        if config.named_tuple and columns:
            return self._convert_rows_to_named_tuples(rows, columns)
        elif config.dictionary and columns:
            return self._convert_rows_to_dictionaries(rows, columns)
        
        return rows
        
    def __enter__(self) -> 'Cursor':
        """Context manager entry"""
        return self
        
    def __exit__(self, exc_type: Optional[type], exc_val: Optional[Exception], exc_tb: Optional[Any]) -> bool:
        """Context manager exit"""
        self.close()
        return False
