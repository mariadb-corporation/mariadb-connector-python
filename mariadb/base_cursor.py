# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from __future__ import annotations

from mariadb.impl.client.base_client import BaseClient, PreparedStatementLRUCache
from mariadb.impl.configuration import Configuration

"""
Base cursor implementation with common functionality for sync and async cursors
"""

import copy
import warnings
from abc import ABC, abstractmethod
from collections import namedtuple
from typing import Sequence, List, Any, Dict, TYPE_CHECKING, TypeVar, Generic, Callable, TypedDict

from .impl.message.server.prepare_stmt_packet import PrepareStmtPacket

from .impl.completion import Completion
from .impl.message.server.column_definition_packet import ColumnsDefinition

from .exceptions import ProgrammingError
from .impl.client.exception_factory import ExceptionFactory
from .impl.result import Result
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

# One column's DB-API (PEP 249) description row. The first seven fields are the
# standard ones (name, type_code, display_size, internal_size, precision, scale,
# null_ok); the remaining four are MariaDB extensions (flags, table, org_name,
# org_table).
ColumnDescription = tuple[str, int, int, int, int, int, bool, int, str, str, str]


class ColumnMetadata(TypedDict):
    """Per-column result metadata (the ``cursor.metadata`` mapping). Each value
    is a tuple with one entry per column, in column order."""
    catalog: tuple[str, ...]
    schema: tuple[str, ...]
    field: tuple[str, ...]
    org_field: tuple[str, ...]
    table: tuple[str, ...]
    org_table: tuple[str, ...]
    type: tuple[int, ...]
    charset: tuple[int, ...]
    length: tuple[int, ...]
    max_length: tuple[int, ...]
    decimals: tuple[int, ...]
    flags: tuple[int, ...]
    ext_type_or_format: tuple[int, ...]


# Module-level lookup tables — built once at import, not rebuilt on every call.
# Both are used in the per-column metadata/description paths below.
_CHARSET_MAX_LENGTHS = {
    1: 2, 8: 1, 28: 2, 33: 3, 45: 4, 46: 4, 63: 1, 77: 1,
    224: 4, 225: 4, 226: 4, 227: 4, 228: 4, 229: 4, 230: 4, 231: 4,
    232: 4, 233: 4, 234: 4, 235: 4, 236: 4, 237: 4, 238: 4, 239: 4,
    240: 4, 241: 4, 242: 4, 243: 4, 244: 4, 245: 4, 246: 4, 247: 4,
    248: 4, 249: 4, 250: 4, 255: 4,
}

_EXT_TYPE_NAME_MAP = {
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
    b'geometrycollection': EXT_FIELD_TYPE.GEOMETRYCOLLECTION,
}


class BaseCursor(ABC, Generic[TResult, TConnection]):
    """
    Base class for MariaDB Cursor Objects
    
    Provides common functionality for both synchronous and asynchronous cursors.
    Subclasses must implement abstract methods for sync or async behavior.
    
    Type Parameters:
        TResult: The result type (SyncResult or AsyncResult)
        TConnection: The connection type (SyncConnection or AsyncConnection)
    """

    # Whether this cursor class honors the deprecated 1.x ``prepared`` option.
    # Only the synchronous cursor sets this True
    _prepared_supported: bool = False

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
        '_use_binary',
        '_stmt',
        '_local_stmt_cache',
        '_prepared',
        '_prepared_sql',
    )

    def __init__(self, connection: TConnection, configuration: Configuration, **kwargs: Any) -> None:
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
        self._current_completion: Completion | None = None
        self._exception_factory = ExceptionFactory()
        self._buffered: bool = bool(kwargs.pop('buffered', True))
        self._use_binary: bool = configuration.binary
        self._stmt: PrepareStmtPacket | None = None
        self._local_stmt_cache: PreparedStatementLRUCache | None = None
        self._prepared: bool = False
        self._prepared_sql: str | None = None
        if kwargs:
            self._config = copy.copy(configuration)
            
            rtype = kwargs.pop("named_tuple", False)
            if rtype:
                self._config.named_tuple = rtype
            else:
                rtype = kwargs.pop("dictionary", False)
                if rtype:
                    self._config.dictionary = rtype
            
            self._config.native_object = bool(kwargs.pop("native_object", self._config.native_object))
            if self._prepared_supported and "prepared" in kwargs:
                self._prepared = bool(kwargs.pop("prepared"))
                warnings.warn(
                    "The 'prepared' cursor option is deprecated. It keeps the "
                    "1.x behavior where every execute() after the first ignores "
                    "its SQL and re-runs the first prepared statement. Prefer "
                    "'binary=True', which reuses the prepared statement while "
                    "the SQL is unchanged without ever ignoring the SQL.",
                    DeprecationWarning,
                    stacklevel=2,
                )
                if self._prepared:
                    self._use_binary = True
            if "binary" in kwargs:
                self._use_binary = bool(kwargs.pop("binary"))
        else:
            self._config = configuration        

    def _check_closed(self) -> None:
        """Check if cursor is closed"""
        if self._closed:
            raise self._exception_factory.create_exception(
                "Cursor is closed",
                errno=0,
                sql_state='42000'
            )

    def _resolve_stmt_cache(self) -> PreparedStatementLRUCache | None:
        """Return the prepared-statement cache to use for binary execution.

        When the connection-level cache is enabled, returns ``None`` so the
        client uses its shared cache (statements reused across all cursors).
        When it is disabled, lazily creates and returns a per-cursor size-1
        cache, giving "keep the last prepared statement, reuse it while the SQL
        is unchanged, close it otherwise" semantics scoped to this cursor.
        """
        client: BaseClient = self.connection._client  # pyright: ignore[reportPrivateUsage]
        if client.prepared_statement_cache is not None:
            return None
        if self._local_stmt_cache is None:
            self._local_stmt_cache = client.make_prepared_statement_cache(1)
        return self._local_stmt_cache

    def _close_local_stmt_cache(self) -> None:
        """Evict and close the per-cursor prepared statement, if any.

        Clearing the cache triggers the eviction callback, which sends
        COM_STMT_CLOSE for the kept statement.
        """
        if self._local_stmt_cache is not None:
            try:
                self._local_stmt_cache.clear()
            except Exception:
                pass
            self._local_stmt_cache = None

    def _apply_prepared_sql(self, sql: str) -> str:
        """Apply 1.x ``prepared`` cursor semantics to *sql*."""
        if not self._prepared:
            return sql
        if self._prepared_sql is not None:
            return self._prepared_sql
        if sql:  # only remember a valid statement as the prepared one
            self._prepared_sql = sql
        return sql

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def affected_rows(self) -> int:
        """Alias for rowcount"""
        return int(self.rowcount)

    @property
    def buffered(self) -> bool:
        """Return True if cursor is buffered"""
        return self._buffered

    @property
    def closed(self) -> bool:
        """Return True if cursor is closed"""
        return self._closed or self.connection.is_closed

    @property
    def field_count(self) -> int:
        """Number of columns in the current result set, or 0 if none."""
        result = self._result
        if result is not None:
            return result.column_count
        return 0

    @property
    def description(self) -> tuple[ColumnDescription, ...] | None:
        """Get cursor description (computed on-demand from result set columns)"""
        if not self._result or not hasattr(self._result, 'columns'):
            return None
        return self._build_description(self._result.columns)

    @property
    def lastrowid(self) -> int | None:
        """Get the last insert ID from the current completion"""
        # For executemany, return the last insert ID from all executions
        # Use cached _current_completion for performance
        if self._current_completion:
            return self._current_completion.insert_id or None
        return None

    @property
    def metadata(self) -> ColumnMetadata | None:
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
        columns: Any = result_set.columns if hasattr(result_set, 'columns') else None  # type: ignore[union-attr]
        
        if not columns or columns.count == 0:
            return None
        
        n = columns.count
        
        # Build metadata tuples from parallel arrays
        catalog_tuple = tuple(columns.get_catalog(i) for i in range(n))
        schema_tuple = tuple(columns.get_schema(i) for i in range(n))
        field_tuple = tuple(columns.get_name(i) for i in range(n))
        org_field_tuple = tuple(columns.get_org_name(i) for i in range(n))
        table_tuple = tuple(columns.get_table(i) for i in range(n))
        org_table_tuple = tuple(columns.get_org_table(i) for i in range(n))
        type_tuple = tuple(columns.types)
        charset_tuple = tuple(columns.charsets)
        length_tuple = tuple(columns.column_lengths)
        max_length_tuple = length_tuple
        decimals_tuple = tuple(columns.decimals_arr)
        flags_tuple = tuple(columns.flags)
        
        # Calculate extended field type - module-level dict lookup (see _EXT_TYPE_NAME_MAP)
        ext_type_list : List[int] = []
        for i in range(n):
            ext_field_type : int = EXT_FIELD_TYPE.NONE
            etf = columns.ext_type_formats[i]
            etn = columns.ext_type_names[i]
            if etf and etf.lower() == b'json':
                ext_field_type = EXT_FIELD_TYPE.JSON
            elif etn:
                ext_field_type = _EXT_TYPE_NAME_MAP.get(etn.lower(), EXT_FIELD_TYPE.NONE)
            
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
                return self._current_completion.result_set.get_row_count()  # type: ignore[union-attr]
            # For non-result operations (INSERT/UPDATE/DELETE), return affected_rows
            return self._current_completion.affected_rows
        # No completions yet
        return -1

    @property
    def rownumber(self) -> int | None:
        """Current row number (1-based, DB-API style)"""
        # Use cached _current_completion for performance
        if self._current_completion and self._current_completion.has_result_set():
            return self._current_completion.result_set.row_number()  # type: ignore[union-attr]
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
    def _completion(self) -> Completion | None:
        """Get the current completion"""
        if self._completion_index < len(self._completions):
            return self._completions[self._completion_index]
        return None

    @property
    def _result(self) -> TResult | None:
        """Get the current result set (for backward compatibility)"""
        completion = self._completion
        if completion and completion.has_result_set():
            return completion.result_set  # type: ignore[return-value]
        return None

    @property
    def _resulttype(self) -> int:
        """Current result type"""
        if self._config.named_tuple:
            return RESULT_NAMEDTUPLE
        elif self._config.dictionary:
            return RESULT_DICTIONARY
        return RESULT_TUPLE

    # =========================================================================
    # DB-API 2.0 Methods
    # =========================================================================

    @abstractmethod
    def callproc(self, procname: str, args: Sequence[Any] = ()) -> None:
        """Call a stored procedure"""
        ...

    @abstractmethod
    def close(self) -> None:
        """Close the cursor"""
        ...

    @abstractmethod
    def execute(self, sql: str, data: Sequence[Any] | dict[str, Any] | None = None, buffered: bool | None = None) -> None:
        """Execute a database query or command"""
        ...

    @abstractmethod
    def executemany(self, sql: str, data: Sequence[Sequence[Any] | dict[str, Any]], buffered: bool | None = None) -> None:
        """Execute a statement multiple times"""
        ...

    @abstractmethod
    def fetchall(self) -> List[tuple[Any, ...]] | List[Dict[str, Any]]:
        """Fetch all remaining rows"""
        ...

    @abstractmethod
    def fetchmany(self, size: int | None = None) -> List[tuple[Any, ...]] | List[Dict[str, Any]]:
        """Fetch the next set of rows"""
        ...

    @abstractmethod
    def fetchone(self) -> tuple[Any, ...] | Dict[str, Any] | None:
        """Fetch the next row"""
        ...

    def setinputsizes(self, sizes: Sequence[int | None]) -> None:
        """Predefine memory areas for parameters (no-op in this implementation)"""
        pass
        
    def setoutputsize(self, size: int, column: int | None = None) -> None:
        """Set a column buffer size for fetches (no-op in this implementation)"""
        pass

    def nextset(self) -> bool | None:
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
    # Helper Methods (Data Transformation)
    # =========================================================================
    def _can_use_bulk_execute(self, parameter_sets: List[List[Any]]) -> bool:
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
                            reference_type = type(param) # pyright: ignore[reportUnknownVariableType]
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

        first_len = len(firstCompletion)
        for u in range(1, len(completions)):
            unit_completions = completions[u]
            for i, c in enumerate(unit_completions):
                if i >= first_len:
                    break
                if c.affected_rows >= 0:
                    firstCompletion[i].affected_rows += c.affected_rows
                if c.insert_id > 0:
                    firstCompletion[i].insert_id = c.insert_id
                if c.has_result_set():
                    firstCompletion[i].result_set.rows.extend(c.result_set.rows)  # type: ignore[union-attr]
        self._completions = firstCompletion
        self._completion_index = 0
    
    def _build_description(self, columns: 'ColumnsDefinition') -> tuple[ColumnDescription, ...] | None:
        """Build cursor description tuple from column definitions"""
        if not columns or columns.count == 0:
            return None
        
        n = columns.count
        col_types = columns.types
        col_flags_arr = columns.flags
        col_charsets = columns.charsets
        col_lengths = columns.column_lengths
        col_decimals = columns.decimals_arr
        col_ext_type_formats = columns.ext_type_formats
        
        description: list[ColumnDescription] = []
        for i in range(n):
            # Determine column type (override for JSON)
            col_type = JSON if col_ext_type_formats[i] == b'json' else col_types[i]
            
            # Add NUM_FLAG for numeric types
            col_flags = col_flags_arr[i]
            col_len = col_lengths[i]
            if (col_type <= INT24 and (col_type != TIMESTAMP or col_len in (14, 8)) or 
                col_type in (YEAR, NEWDECIMAL, DECIMAL)):
                col_flags |= NUM_FLAG
            
            # Calculate display_length and packed_len
            max_char_len = self._get_charset_max_length(col_charsets[i])
            if max_char_len and max_char_len > 1:
                packed_len = col_len
                display_length = col_len // max_char_len
            else:
                packed_len = -1
                display_length = col_len
            
            # Handle decimal fields special case
            dec = col_decimals[i]
            if dec and dec < 31:
                precision = col_len
                decimals = dec
                display_length = precision + 1
            else:
                precision = 0
                decimals = dec
            
            description.append((
                columns.get_name(i), col_type, display_length, packed_len,
                precision, decimals, not (col_flags & 1), col_flags,
                columns.get_table(i), columns.get_org_name(i), columns.get_org_table(i)
            ))
        
        return tuple(description)
    
    def _create_named_tuple_class(self, columns: 'ColumnsDefinition') -> Callable[..., tuple[Any, ...]]:
        """Create a namedtuple class from column definitions.

        Typed as a callable row factory rather than ``type[tuple[...]]``: the
        fields are dynamic (from the result columns), so the per-field
        constructor ``Row(*values)`` can't be expressed as a tuple subtype.
        """

        field_names: list[str] = []
        for i in range(columns.count):
            name = columns.get_name(i) or columns.get_org_name(i)
            if not name or not name.isidentifier():
                name = f'column_{len(field_names)}'
            original_name = name
            counter = 1
            while name in field_names:
                name = f'{original_name}_{counter}'
                counter += 1
            field_names.append(name)
        
        # namedtuple (not typing.NamedTuple) is required: field names are only
        # known at runtime, so the fields can't be statically typed.
        return namedtuple('Row', field_names)  # pyright: ignore[reportUntypedNamedTuple]
    
    def _convert_rows_to_named_tuples(self, rows: List[tuple[Any, ...]], columns: 'ColumnsDefinition') -> List[tuple[Any, ...]]:
        """Convert regular tuples to named tuples"""
        RowClass = self._create_named_tuple_class(columns)
        return [RowClass(*row) for row in rows]
    
    def _convert_rows_to_dictionaries(self, rows: List[tuple[Any, ...]], columns: 'ColumnsDefinition') -> List[Dict[str, Any]]:
        """Convert regular tuples to dictionaries"""
        field_names: list[str] = []
        for i in range(columns.count):
            name = columns.get_name(i) or columns.get_org_name(i)
            if not name:
                name = f'column_{len(field_names)}'
            field_names.append(name)
        
        return [dict(zip(field_names, row)) for row in rows]
    
    def _apply_row_formatting(self, rows: List[tuple[Any, ...]]) -> List[tuple[Any, ...]] | List[Dict[str, Any]]:
        """Apply row formatting (named_tuple or dictionary) based on configuration"""
        # Use cached _current_completion for performance
        if self._config and (self._config.named_tuple or self._config.dictionary):
            if self._current_completion and self._current_completion.has_result_set():
                result = self._current_completion.result_set
                columns = result.columns  # type: ignore[union-attr]
                if columns:
                    # Inline config checks for performance
                    if self._config.named_tuple:
                        return self._convert_rows_to_named_tuples(rows, columns)
                    elif self._config.dictionary:
                        return self._convert_rows_to_dictionaries(rows, columns)
        
        return rows
    
    def _get_charset_max_length(self, charset_id: int) -> int | None:
        """Get maximum character length for a charset ID"""
        return _CHARSET_MAX_LENGTHS.get(charset_id)
