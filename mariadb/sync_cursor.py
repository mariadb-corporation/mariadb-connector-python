# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab


from collections import namedtuple
from typing import Sequence, Optional, List, Any, Union, TYPE_CHECKING

from .impl.result import SyncResult

from .impl.message.server.prepare_stmt_packet import PrepareStmtPacket
from .impl.client.sync_client import SyncClient

from .base_cursor import BaseCursor
from .exceptions import DatabaseError, ProgrammingError
from .impl.message.client.query_packet import QueryPacket, normalize_to_qmark
from mariadb_shared.sync_cursor_common import SyncCursorCommon
from mariadb_shared.constants.STATUS import NO_BACKSLASH_ESCAPES

if TYPE_CHECKING:
    from .base_connection import BaseConnection
    from .sync_connection import SyncConnection

class SyncCursor(BaseCursor[SyncResult, 'SyncConnection'], SyncCursorCommon):
    """
    Synchronous MariaDB Cursor Object
    
    Provides methods for executing SQL queries and retrieving results.
    Supports both regular queries and prepared statements.
    
    """
    
    __slots__ = ()  # No additional attributes beyond BaseCursor
    
    # =========================================================================
    # Initialization and Lifecycle
    # =========================================================================

    def __init__(self, connection: 'BaseConnection', **kwargs):
        """
        Initialize synchronous cursor with a connection
        
        Args:
            connection: Database connection object
            **kwargs: Cursor options:
                - buffered: Buffer all results immediately
                - named_tuple: Return rows as named tuples
                - dictionary: Return rows as dictionaries
        """
        super().__init__(connection, **kwargs)

    def close(self) -> None:
        """
        Close the cursor and free resources
        
        Consumes any remaining streaming results before closing.
        After closing, the cursor cannot be used anymore.
        """
        if not self._closed:

            if self._stmt:
                # Release cached statement reference
                self.connection._client.prepared_statement_cache.release(self._stmt)
                self._stmt = None

            # Consume any remaining streaming results
            if self._result is not None and self._result.streaming():
                try:
                    self._result.fetch_remaining()
                except Exception:
                    pass  # Ignore errors during close
            
            self._closed = True
    
    # =========================================================================
    # Query Execution Methods
    # =========================================================================
        
    def execute(self, sql: str, data: Optional[Union[Sequence[Any], dict]] = None, buffered: Optional[bool] = None) -> None:
        """
        Execute a SQL query or command
        
        Supports parameterized queries using ? placeholders or named placeholders.
        
        Args:
            sql: SQL statement to execute
            data: Optional parameters:
                - Sequence (list/tuple) for positional parameters (?)
                - Dict for named parameters (:name)
            buffered: Override cursor's buffered setting:
                - True: Fetch all results immediately
                - False: Stream results (default for large result sets)
                - None: Use cursor's default setting
                
        Raises:
            ProgrammingError: If cursor is closed or SQL is invalid
            DatabaseError: If execution fails
            
        Example:
            >>> cursor.execute("SELECT * FROM users WHERE id = ?", (1,))
            >>> cursor.execute("INSERT INTO users VALUES (?, ?)", (1, 'John'))
        """
        self._check_closed()
        
        # Validate SQL type
        if not isinstance(sql, str):
            raise TypeError("SQL statement must be a string")
        if (not sql):
            raise ProgrammingError("Empty SQL statement")

        # Consume any pending streaming results before executing new query
        if self._result is not None and self._result.streaming():
            self._result.fetch_remaining()

        try:
            # Use provided buffered parameter or fall back to cursor default
            effective_buffered = buffered if buffered is not None else self._buffered

            if data:
                if isinstance(data, (list, tuple)):
                    # Positional parameters
                    parameters = list(data)
                elif isinstance(data, dict):
                    # Named parameters
                    parameters = data
                else:
                    raise ProgrammingError(f"wrong parameter type")

                if self._force_binary and not isinstance(parameters, dict):

                    from .impl.message.client.execute_packet import ExecutePacket
                    execute_packet = ExecutePacket(None, parameters, sql)
                    self._completions = self.connection._client.execute_stmt(sql, [execute_packet], self._config, effective_buffered)[0]

                else:
                    no_backslash_escapes = (self.connection._client.context.server_status & NO_BACKSLASH_ESCAPES) > 0
                    query_packet = QueryPacket.from_substitute(sql, parameters, no_backslash_escapes)
                    self._completions = self.connection._client.execute(query_packet, self._config, effective_buffered)

            else:
                # Use simple query packet
                query_packet = QueryPacket.from_sql(sql)
                self._completions = self.connection._client.execute(query_packet, self._config, effective_buffered)
            
            # Process the completions to extract result data
            self._completion_index = 0
            self._current_completion = self._completions[0]
        except DatabaseError as e:
            raise e                
        except Exception as e:
            raise self._exception_factory.create_exception(
                f"Execute failed: {e}",
                errno=2013,
                sql_state='HY000'
            )

    def executemany(self, sql: str, data: Sequence[Union[Sequence[Any], dict]], buffered: Optional[bool] = None) -> None:
        """
        Execute a statement multiple times with different parameter sets
        
        Args:
            sql: SQL statement to execute
            data: Sequence of parameter sequences
            buffered: Override cursor's buffered setting for this execution
        """
        self._check_closed()
        
        # Validate SQL type
        if not isinstance(sql, str):
            raise TypeError("SQL statement must be a string")
        
        # Consume any pending streaming results before executing new query
        if self._result is not None and self._result.streaming():
            self._result.fetch_remaining()

        # Check if data is None or not an array-like type
        if data is None or not hasattr(data, '__iter__') or isinstance(data, (str, bytes)):
            raise ProgrammingError("No data provided")
        
        try:
            if data and len(data) > 0 and not isinstance(data, (list, tuple)):
                raise ProgrammingError(f"wrong parameter type")

            # Normalize SQL to qmark style and get parameter mapping
            normalized_sql, param_names = normalize_to_qmark(sql)
            
            # Reorder parameters if needed (for named/pyformat styles)
            if param_names is not None:
                # Named parameters - reorder each parameter set according to param_names
                reordered_data = []
                for param_set in data:
                    if isinstance(param_set, dict):
                        reordered = [param_set.get(name) for name in param_names]
                        reordered_data.append(reordered)
                    else:
                        raise ProgrammingError("Named placeholders require dict parameters")
                data = reordered_data
            
            # Check if server supports COM_STMT_BULK_EXECUTE
            from mariadb_shared import constants
            context = self.connection._client.context
            use_bulk = (context.has_capability(constants.CAPABILITY.BULK_OPERATIONS) and 
                       len(data) > 0 and len(data[0]) > 0)
            
            # Use binary protocol with normalized SQL (always qmark now)
            if use_bulk or self._force_binary:
                if use_bulk and self._can_use_bulk_execute(data):
                    # Use COM_STMT_BULK_EXECUTE for efficient bulk execution
                    from .impl.message.client.bulk_execute_packet import BulkExecutePacket
                    bulk_packet = BulkExecutePacket(None, data, normalized_sql)
                    self._completions = self.connection._client.execute_stmt(normalized_sql, [bulk_packet], self._config, True)[0]
                    self._completion_index = 0
                else: 
                    # Fallback to individual COM_STMT_EXECUTE packets (when bulk not available but binary forced)
                    from .impl.message.client.execute_packet import ExecutePacket
                    
                    # Create all execute packets
                    execute_packets = [ExecutePacket(None, params, normalized_sql) for params in data]
                    
                    # Execute all at once with single prepare
                    completions = self.connection._client.execute_stmt(normalized_sql, execute_packets, self._config, True)

                    self._process_executemany_completions(completions)   
            else:
                # Text protocol fallback (when bulk not available and binary not forced)
                # Get NO_BACKSLASH_ESCAPES status from connection
                no_backslash_escapes = (self.connection._client.context.server_status & NO_BACKSLASH_ESCAPES) > 0
                
                completions = [None] * len(data)
                for i in range(len(data)):
                    params = data[i]
                    parameters = list(params) if params else []
                    # from_substitute() will validate parameter count and raise ProgrammingError if mismatch
                    query_packet = QueryPacket.from_substitute(sql, parameters, no_backslash_escapes)
                    completions[i] = self.connection._client.execute(query_packet, self._config, True, self._stmt)

                self._process_executemany_completions(completions)
                self._current_completion = self._completions[0] if self._completions else None
            self._current_completion = self._completions[0]

        except DatabaseError as e:
            raise e            
        except Exception as e:
            raise self._exception_factory.create_exception(
                f"ExecuteMany failed: {e}",
                errno=2013,
                sql_state='HY000'
            )
        
    # =========================================================================
    # Result Fetching Methods
    # =========================================================================
        
    def fetchone(self) -> Optional[Any]:
        """Fetch the next row of a query result set
        
        Returns:
            The next row of the result set, or None if no more rows are available.
        
        Raises:
            ProgrammingError: If cursor is closed or no result set is available.
        """
        # Allow fetching from buffered results even if connection is closed
        if self._closed:
            raise ProgrammingError("Cursor is closed")
        
        # Use cached _current_completion for performance
        if not self._current_completion or not self._current_completion.has_result_set():
            raise ProgrammingError("No result set to fetch from")
        result = self._current_completion.result_set
        
        if self.connection._closed and result.streaming():
            raise ProgrammingError("Cursor is closed")
        
        row = result.fetch_one()
        self._rowcount = result.get_row_count()
        if row is not None:
            # Apply row formatting
            row = self._apply_row_formatting([row])[0]
        return row
            
    def fetchmany(self, size: Optional[int] = None) -> List[Any]:
        """Fetch the next set of rows of a query result"""
        # Allow fetching from buffered results even if connection is closed
        if self._closed:
            raise ProgrammingError("Cursor is closed")
        
        # Use cached _current_completion for performance
        if not self._current_completion or not self._current_completion.has_result_set():
            raise ProgrammingError("No result set to fetch from")
        result = self._current_completion.result_set
        
        if self.connection._closed and result.streaming():
            raise ProgrammingError("Cursor is closed")
        
        if size is None:
            size = self.arraysize
        
        # Optimize: fetch rows directly instead of calling fetchone repeatedly
        rows = []
        for _ in range(size):
            row = result.fetch_one()
            if row is None:
                break
            rows.append(row)
        
        if rows:
            self._rowcount = result.get_row_count()
            return self._apply_row_formatting(rows)
        return []
        
    def fetchall(self) -> List[Any]:
        """Fetch all remaining rows of a query result"""
        # Allow fetching from buffered results even if connection is closed
        if self._closed:
            raise ProgrammingError("Cursor is closed")
        
        # Use cached _current_completion for performance
        if not self._current_completion or not self._current_completion.has_result_set():
            raise ProgrammingError("No result set to fetch from")
        result = self._current_completion.result_set
        
        if self.connection._closed and result.streaming():
            raise ProgrammingError("Cursor is closed")
        
        # Delegate to Result object
        rows = result.fetch_all()
        self._rowcount = result.get_row_count()
        return self._apply_row_formatting(rows)
    
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
        
        result = self._result
        if result is None:
            raise ProgrammingError("Cursor doesn't have a result set")
        
        if self.connection._closed and result.streaming():
            raise ProgrammingError("Cursor is closed")

        # For streaming results, only forward relative scrolling is allowed
        if result.streaming():
            if mode != "relative":
                raise ProgrammingError("Streaming cursors only support relative scroll mode")
            if value < 0:
                raise ProgrammingError("Streaming cursors only support forward scrolling")
        
        # Delegate to Result object's scroll method
        try:
            result.scroll(value, mode)
        except ValueError as e:
            raise ProgrammingError(str(e))
    

    # =========================================================================
    # Stored Procedures
    # =========================================================================
    
    def callproc(self, procname: str, args: Sequence[Any] = ()) -> Sequence[Any]:
        """
        Call a stored procedure
        
        Executes a stored procedure and processes all result sets.
        
        Args:
            procname: Name of the stored procedure to call
            args: Sequence of arguments to pass to the procedure
            
        Returns:
            None (matches C extension behavior)
            
        Raises:
            ProgrammingError: If cursor is closed
            DatabaseError: If procedure execution fails
            
        Example:
            >>> cursor.callproc('get_user', (1,))
            >>> result = cursor.fetchone()
        """
        self._check_closed()
        
        try:
            # Build CALL statement with placeholders
            placeholders = ', '.join(['?' for _ in args])
            call_sql = f"CALL {procname}({placeholders})"
            
            # Use execute_stmt which handles prepared statement caching internally
            from .impl.message.client.execute_packet import ExecutePacket
            execute_packet = ExecutePacket(None, list(args), call_sql)  # None = will be filled by execute_stmt
            self._completions = self.connection._client.execute_stmt(call_sql, [execute_packet], self._config)[0]
            self._completion_index = 0
            self._current_completion = self._completions[0]
            return None  # Match C extension behavior
        except DatabaseError as e:
            raise e
        except Exception as e:
            raise self._exception_factory.create_exception(
                f"CallProc failed: {e}",
                errno=2013,
                sql_state='HY000'
            )
    
    # =========================================================================
    # Iterator Protocol
    # =========================================================================
    
    def __iter__(self) -> 'SyncCursor':
        """
        Return the cursor itself for iteration
        
        Allows using the cursor in for loops:
            for row in cursor:
                process(row)
        """
        return self
    
    def __next__(self) -> Any:
        """
        Return the next row from the result set
        
        Raises:
            StopIteration: When no more rows are available
        """
        row = self.fetchone()
        if row is None:
            raise StopIteration
        return row
    
    # =========================================================================
    # Context Manager
    # =========================================================================
    
    def __enter__(self) -> 'SyncCursor':
        """Context manager entry"""
        return self
        
    def __exit__(self, exc_type: Optional[type], exc_val: Optional[Exception], exc_tb: Optional[Any]) -> bool:
        """Context manager exit"""
        self.close()
        return False
    
    # =========================================================================
    # Result Creation
    # =========================================================================
    
    def _create_complete_result(self, columns: List[Any], column_count: int, 
                               rows: List[tuple]):
        """Create a synchronous complete result"""
        from .impl.result import SyncCompleteResult
        return SyncCompleteResult(
            columns=columns,
            column_count=column_count,
            config=self._config,
            rows=rows
        )
