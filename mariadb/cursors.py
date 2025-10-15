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
from typing import Sequence, Optional, List, Any, Union

from .exceptions import ProgrammingError, NotSupportedError, OperationalError
from .impl.message.client.query_packet import QueryPacket
from .constants.STATUS import NO_BACKSLASH_ESCAPES

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

    def __init__(self, connection: 'Connection'):
        """
        Initialize cursor with a connection
        
        Args:
            connection: Database connection
        """
        self.connection: 'Connection' = connection
        self._closed: bool = False
        self.arraysize: int = 1
        self.rowcount: int = -1
        self.description: Optional[List[Any]] = None
        self.lastrowid: int = 0
        self._result: List[Any] = []
        self._result_index: int = 0
        
        
    def _check_closed(self) -> None:
        """Check if cursor is closed"""
        if self._closed:
            raise ProgrammingError("Cursor is closed")

    def close(self) -> None:
        """Close the cursor"""
        if not self._closed:
            self._closed = True
        
    def execute(self, sql: str, data: Optional[Union[Sequence[Any], dict]] = None, buffered: bool = False) -> None:
        """
        Execute a database query or command
        
        Args:
            sql: SQL statement to execute
            data: Optional parameters for the statement
        """
        self._check_closed()
        
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
            completions = self.connection._client.execute(query_packet, can_redo=False)
            
            # Process the completions to extract result data
            self._process_completions(completions)
            
        except Exception as e:
            raise OperationalError(f"Execute failed: {e}")
        
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
                return self._escape_string(param, no_backslash_escapes)
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
                return f"'{self.connection._client.escape_string(str(param))}'"
    
    
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
        if not completions:
            self.rowcount = 0
            self.description = None
            self._result = []
            self._result_index = 0
            return
        
        # Handle the first completion
        completion = completions[0]
        
        # Check if it's a result set or update count
        if completion.is_result_set:
            # It's a result set
            self._process_result_set_completion(completion)
        else:
            # It's an update count
            self.rowcount = completion.affected_rows
            self.description = None
            self._result = []
            self.lastrowid = completion.insert_id
        
        self._result_index = 0
    
    def _process_result_set_completion(self, completion: Any) -> None:
        """
        Process a result set completion
        
        Args:
            completion: Result set completion object
        """
        try:
            # Extract real result set data from completion
            if hasattr(completion, 'result_set') and completion.result_set:
                result_set = completion.result_set
                
                # Extract rows
                rows = result_set.get('rows', [])
                self._result = rows
                self.rowcount = len(rows)
                
                # Extract column information for description
                columns = result_set.get('columns', [])
                description = []
                
                for col in columns:
                    # Create description tuple: (name, type_code, display_size, internal_size, precision, scale, null_ok)
                    col_name = col.get('name', 'unknown')
                    col_type = col.get('column_type', 253)  # Default to VARCHAR
                    col_length = col.get('column_length', 0)
                    col_flags = col.get('flags', 0)
                    col_decimals = col.get('decimals', 0)
                    
                    # Check if column is nullable (flag bit 0 = NOT NULL)
                    nullable = not (col_flags & 1)
                    
                    description.append((
                        col_name,
                        col_type,
                        None,  # display_size
                        col_length,  # internal_size
                        col_length,  # precision
                        col_decimals,  # scale
                        nullable  # null_ok
                    ))
                
                self.description = tuple(description) if description else None
                
            else:
                # No result set data available
                self._result = []
                self.rowcount = 0
                self.description = None
            
        except Exception as e:
            raise OperationalError(f"Failed to process result set: {e}")
    
    
        
    def executemany(self, sql: str, data: Sequence[Sequence[Any]]) -> None:
        """
        Execute a database query or command for multiple rows
        
        This method executes the given SQL statement for each parameter sequence
        in the data sequence. It's essentially a loop of execute() calls.
        
        Args:
            sql: SQL statement to execute
            data: Sequence of parameter sequences
        """
        self._check_closed()
        
        if not data:
            return
        
        # Reset result state
        self.description = None
        self._result = []
        self._result_index = 0
        total_affected = 0
        
        try:
            # Execute the statement for each parameter set
            for params in data:
                # Execute with current parameter set
                self.execute(sql, params)
                
                # Accumulate affected rows (if available)
                if hasattr(self, 'rowcount') and self.rowcount >= 0:
                    total_affected += self.rowcount
            
            # Set final rowcount to total affected rows
            self.rowcount = total_affected
            
        except Exception as e:
            raise OperationalError(f"ExecuteMany failed: {e}")
        
    def fetchone(self) -> Optional[Any]:
        """Fetch the next row of a query result set"""
        self._check_closed()
        if self._result_index >= len(self._result):
            return None
        row = self._result[self._result_index]
        self._result_index += 1
        return row
        
    def fetchmany(self, size: Optional[int] = None) -> List[Any]:
        """Fetch the next set of rows of a query result"""
        self._check_closed()
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
        self._check_closed()
        result = self._result[self._result_index:]
        self._result_index = len(self._result)
        return result
        
    def callproc(self, procname: str, args: Sequence[Any] = ()) -> Any:
        """Call a stored procedure"""
        self._check_closed()
        raise NotSupportedError("Pure Python implementation - callproc not yet implemented")
        
    def nextset(self) -> Optional[bool]:
        """Skip to the next available result set"""
        self._check_closed()
        return None
        
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
        
    def __enter__(self) -> 'Cursor':
        """Context manager entry"""
        return self
        
    def __exit__(self, exc_type: Optional[type], exc_val: Optional[Exception], exc_tb: Optional[Any]) -> bool:
        """Context manager exit"""
        self.close()
        return False
