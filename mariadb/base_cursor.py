# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Base cursor implementation with common functionality for sync and async cursors
"""

import copy
from abc import ABC, abstractmethod
from collections import namedtuple
from typing import Sequence, Optional, List, Any, Union, Dict, TYPE_CHECKING, TypeVar, Generic

from .impl.message.server.prepare_stmt_packet import PrepareStmtPacket

from .impl.completion import Completion
from .impl.message.server.column_definition_packet import ColumnDefinitionPacket

from .exceptions import ProgrammingError
from .impl.client.exception_factory import ExceptionFactory
from .impl.result import Result
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

TResult = TypeVar('TResult', bound=Result)
TConnection = TypeVar('TConnection', bound='BaseConnection')

class BaseCursor(ABC, Generic[TResult, TConnection]):
    """
    Base class for MariaDB Cursor Objects
    
    Provides common functionality for both synchronous and asynchronous cursors.
    Subclasses must implement abstract methods for sync or async behavior.
    
    Type Parameters:
        TResult: The result type (SyncResult or AsyncResult)
        TConnection: The connection type (SyncConnection or AsyncConnection)
    """
    
    __slots__ = (
        'connection',
        '_closed',
        'arraysize',
        '_completions',
        '_completion_index',
        '_current_completion',
        '_config',
        '_exception_factory',
        '_buffered',
        '_force_binary',
        '_stmt',
    )

    def __init__(self, connection: TConnection, **kwargs):
        """
        Initialize cursor with a connection
        
        Args:
            connection: Database connection
            **kwargs: Cursor options (buffered, named_tuple, dictionary, etc.)
        """
        self.connection: TConnection = connection
        self._closed: bool = False
        self.arraysize: int = 1
        self._completions: List[Completion] = []
        self._completion_index: int = 0
        self._current_completion: Optional[Completion] = None
        self._config = None
        self._exception_factory = ExceptionFactory()
        self._buffered: bool = bool(kwargs.pop('buffered', True))
        self._force_binary: bool = False
        self._stmt: Optional[PrepareStmtPacket] = None
        if kwargs:
            self._config = copy.copy(self.connection._configuration)
            
            rtype = kwargs.pop("named_tuple", False)
            if rtype:
                self._config.named_tuple = rtype
            else:
                rtype = kwargs.pop("dictionary", False)
                if rtype:
                    self._config.dictionary = rtype
            
            self._config.native_object = bool(kwargs.pop("native_object", self._config.native_object))
            self._force_binary = bool(kwargs.pop("binary", False))
        else:
            self._config = self.connection._configuration        

    def _check_closed(self) -> None:
        """Check if cursor is closed"""
        if self._closed:
            raise self._exception_factory.create_exception(
                "Cursor is closed",
                errno=0,
                sql_state='42000'
            )

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def affected_rows(self) -> int:
        """Alias for rowcount"""
        return int(self.rowcount)

    @property
    def closed(self) -> bool:
        """Return True if cursor is closed"""
        return self._closed or self.connection._closed

    @property
    def description(self) -> Optional[tuple]:
        """Get cursor description (computed on-demand from result set columns)"""
        if not self._result or not hasattr(self._result, 'columns'):
            return None
        return self._build_description(self._result.columns)

    @property
    def lastrowid(self) -> Optional[int]:
        """Get the last insert ID from the current completion"""
        # For executemany, return the last insert ID from all executions
        # Use cached _current_completion for performance
        if self._current_completion:
            return self._current_completion.insert_id or None
        return None

    @property
    def metadata(self) -> Optional[Dict[str, tuple]]:
        """Get metadata information for result set columns"""
        # Inline _check_closed for performance
        if self._closed:
            raise self._exception_factory.create_exception(
                "Cursor is closed",
                errno=0,
                sql_state='42000'
            )
        
        # Use cached _current_completion for performance
        if not self._current_completion or not self._current_completion.has_result_set():
            return None
        
        completion = self._current_completion
        
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
        type_tuple = tuple(col.type for col in columns)
        charset_tuple = tuple(col.character_set for col in columns)
        length_tuple = tuple(col.column_length for col in columns)
        max_length_tuple = tuple(col.column_length for col in columns)
        decimals_tuple = tuple(col.decimals for col in columns)
        flags_tuple = tuple(col.flags for col in columns)
        
        # Calculate extended field type - use dict lookup for performance
        ext_type_name_map = {
            b'json': EXT_FIELD_TYPE.JSON,
            b'uuid': EXT_FIELD_TYPE.UUID,
            b'inet4': EXT_FIELD_TYPE.INET4,
            b'inet6': EXT_FIELD_TYPE.INET6,
            b'point': EXT_FIELD_TYPE.POINT,
            b'multipoint': EXT_FIELD_TYPE.MULTIPOINT,
            b'linestring': EXT_FIELD_TYPE.LINESTRING,
            b'multilinestring': EXT_FIELD_TYPE.MULTILINESTRING,
            b'polygon': EXT_FIELD_TYPE.POLYGON,
            b'multipolygon': EXT_FIELD_TYPE.MULTIPOLYGON,
            b'geometrycollection': EXT_FIELD_TYPE.GEOMETRYCOLLECTION
        }
        
        ext_type_list = []
        for col in columns:
            ext_field_type = EXT_FIELD_TYPE.NONE
            if col.ext_type_format and col.ext_type_format.lower() == b'json':
                ext_field_type = EXT_FIELD_TYPE.JSON
            elif col.ext_type_name:
                ext_field_type = ext_type_name_map.get(col.ext_type_name.lower(), EXT_FIELD_TYPE.NONE)
            
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

    @property
    def rowcount(self) -> int:
        """Get the number of rows (read-only property)"""
        # Use cached _current_completion for performance
        if self._current_completion:
            # For result sets, return the current row count from the result set
            if self._current_completion.has_result_set():
                return self._current_completion.result_set.get_row_count()
            # For non-result operations (INSERT/UPDATE/DELETE), return affected_rows
            return self._current_completion.affected_rows
        # No completions yet
        return -1

    @property
    def rownumber(self) -> Optional[int]:
        """Current row number (1-based, DB-API style)"""
        # Use cached _current_completion for performance
        if self._current_completion and self._current_completion.has_result_set():
            return self._current_completion.result_set.row_number()
        return None

    @property
    def sp_outparams(self) -> bool:
        """Check if current result set contains output parameters"""
        # Use cached _current_completion for performance
        if self._current_completion:
            return self._current_completion.is_output_parameters()
        return False

    @property
    def warnings(self) -> int:
        """Get the number of warnings from the last executed statement"""
        # Use cached _current_completion for performance
        if self._current_completion:
            return getattr(self._current_completion, 'warning_count', 0)
        return 0

    # =========================================================================
    # Internal Properties
    # =========================================================================

    @property
    def _completion(self) -> Optional[Completion]:
        """Get the current completion"""
        if self._completion_index < len(self._completions):
            return self._completions[self._completion_index]
        return None

    @property
    def _result(self) -> Optional[TResult]:
        """Get the current result set (for backward compatibility)"""
        completion = self._completion
        if completion and completion.has_result_set():
            return completion.result_set
        return None

    @property
    def _resulttype(self) -> int:
        """Current result type"""
        config = self._config
        if config.named_tuple:
            return RESULT_NAMEDTUPLE
        elif config.dictionary:
            return RESULT_DICTIONARY
        return RESULT_TUPLE

    # =========================================================================
    # DB-API 2.0 Methods
    # =========================================================================

    @abstractmethod
    def callproc(self, procname: str, args: Sequence[Any] = ()) -> Sequence[Any]:
        """Call a stored procedure"""
        ...

    @abstractmethod
    def close(self):
        """Close the cursor"""
        ...

    @abstractmethod
    def execute(self, sql: str, data: Optional[Union[Sequence[Any], dict]] = None, buffered: Optional[bool] = None):
        """Execute a database query or command"""
        ...

    @abstractmethod
    def executemany(self, sql: str, data: Sequence[Union[Sequence[Any], dict]], buffered: Optional[bool] = None):
        """Execute a statement multiple times"""
        ...

    @abstractmethod
    def fetchall(self) -> List[Any]:
        """Fetch all remaining rows"""
        ...

    @abstractmethod
    def fetchmany(self, size: Optional[int] = None) -> List[Any]:
        """Fetch the next set of rows"""
        ...

    @abstractmethod
    def fetchone(self) -> Optional[Any]:
        """Fetch the next row"""
        ...

    def setinputsizes(self, sizes: Sequence[Optional[int]]) -> None:
        """Predefine memory areas for parameters (no-op in this implementation)"""
        pass
        
    def setoutputsize(self, size: int, column: Optional[int] = None) -> None:
        """Set a column buffer size for fetches (no-op in this implementation)"""
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
        
        self._completion_index += 1
        if self._completion_index >= len(self._completions):
            self._current_completion = None
            return None
        
        self._current_completion = self._completions[self._completion_index]
        return True

    # =========================================================================
    # Iterator Protocol
    # =========================================================================

    @abstractmethod
    def __iter__(self):
        """Return iterator for cursor"""
        ...

    @abstractmethod
    def __next__(self) -> Any:
        """Return next row"""
        ...

    # =========================================================================
    # Helper Methods (Data Transformation)
    # =========================================================================
    def _can_use_bulk_execute(self, parameter_sets: list) -> bool:
        """
        Check if all parameter sets have compatible types for COM_STMT_BULK_EXECUTE.
        
        COM_STMT_BULK_EXECUTE requires that all parameters at the same position
        across all parameter sets have the same type.
        
        Args:
            parameter_sets: List of parameter lists
            
        Returns:
            True if bulk execute can be used, False otherwise
        """
        if not parameter_sets or len(parameter_sets) == 0:
            return True
        
        num_params = len(parameter_sets[0])
        if num_params == 0:
            return False
        
        # If statement is prepared, validate parameter count
        expected_count = 0
        if self._stmt is not None:
            expected_count = self._stmt.parameter_count
        else:
            expected_count = num_params

        for param_set in parameter_sets:
            if len(param_set) != expected_count:
                # Parameter count mismatch - this is always an error
                from mariadb import ProgrammingError
                raise ProgrammingError(
                    f"Parameter count mismatch: expected {expected_count} parameters, "
                    f"but got {len(param_set)} parameters in one of the parameter sets"
                )
        
        # Check each parameter position for type compatibility
        from mariadb_shared.constants.INDICATOR import MrdbIndicator
        
        for param_idx in range(num_params):
            # Get the type of the first non-None, non-Indicator value at this position
            reference_type = None
            
            for param_set in parameter_sets:
                if param_idx < len(param_set):
                    param = param_set[param_idx]
                    # Skip None and Indicator types
                    if param is not None and not isinstance(param, MrdbIndicator):
                        if reference_type is None:
                            # First real value found - set as reference
                            reference_type = type(param)
                        elif type(param) != reference_type:
                            # Type mismatch found
                            return False
        
        return True
    
    def _process_executemany_completions(self, completions: List[List[Completion]]) -> None:
        """
        Process completions from executemany - aggregate all result sets.
        Since executemany runs the same query multiple times, all completions have identical metadata.
        
        Args:
            completions: List[List[Completion]] - one list per executed message
        """
        if not completions:
            return

        firstCompletion = completions[0]
        if not firstCompletion:
            return

        for u in range(1, len(completions)):
            unit_completions = completions[u]
            for i, c in enumerate(unit_completions):
                if c.affected_rows >= 0:
                    firstCompletion[i].affected_rows += c.affected_rows
                if c.insert_id is not None and c.insert_id > 0:
                    firstCompletion[i].insert_id = c.insert_id
                if c.has_result_set():
                    firstCompletion[i].result_set.rows.extend(c.result_set.rows)
        self._completions = firstCompletion
        self._completion_index = 0
    
    def _build_description(self, columns: List[ColumnDefinitionPacket]) -> Optional[tuple]:
        """Build cursor description tuple from column definitions"""
        if not columns:
            return None
        
        description = []
        for col in columns:
            # Determine column type (override for JSON)
            col_type = JSON if col.ext_type_format == b'json' else col.type
            
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
        RowClass = self._create_named_tuple_class(columns)
        return [RowClass(*row) for row in rows]
    
    def _convert_rows_to_dictionaries(self, rows: List[tuple], columns: List[ColumnDefinitionPacket]) -> List[Dict]:
        """Convert regular tuples to dictionaries"""
        field_names = []
        for column in columns:
            name = column.name or column.org_name
            if not name:
                name = f'column_{len(field_names)}'
            field_names.append(name)
        
        return [dict(zip(field_names, row)) for row in rows]
    
    def _apply_row_formatting(self, rows: List[Any]) -> List[Any]:
        """Apply row formatting (named_tuple or dictionary) based on configuration"""
        # Use cached _current_completion for performance
        if self._config.named_tuple or self._config.dictionary:
            if self._current_completion and self._current_completion.has_result_set():
                result = self._current_completion.result_set
                columns = result.columns
                if columns:
                    # Inline config checks for performance
                    if self._config.named_tuple:
                        return self._convert_rows_to_named_tuples(rows, columns)
                    elif self._config.dictionary:
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
