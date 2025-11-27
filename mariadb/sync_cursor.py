# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab


from collections import namedtuple
from typing import Sequence, Optional, List, Any, Union, TYPE_CHECKING

from .impl.result import SyncResult

from .impl.message.server.prepare_stmt_packet import PrepareStmtPacket
from .impl.client.sync_client import SyncClient

from .base_cursor import BaseCursor
from .exceptions import DatabaseError, ProgrammingError
from .impl.message.client.query_packet import QueryPacket, QueryWithParamPacket
from .impl.sql_parser import split_sql_parts
from mariadb_shared.sync_cursor_common import SyncCursorCommon

if TYPE_CHECKING:
    from .base_connection import BaseConnection
    from .sync_connection import SyncConnection

class SyncCursor(BaseCursor[SyncResult, 'SyncConnection'], SyncCursorCommon):
    """
    Synchronous MariaDB Cursor Object
    
    Provides methods for executing SQL queries and retrieving results.
    Supports both regular queries and prepared statements.
    
    """
    
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
                self.connection._client.close_prepared_statement(self._stmt)
                self._stmt = None

            # Consume any remaining streaming results
            if self._result is not None and self._result.streaming():
                try:
                    self._result.fetch_remaining()
                except Exception:
                    pass  # Ignore errors during close
            
            self._closed = True
    
    # =========================================================================
    # Helper Methods
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
            return True
        
        # If statement is prepared, validate parameter count
        if self._stmt is not None:
            expected_count = self._stmt.parameter_count
            for param_set in parameter_sets:
                if len(param_set) != expected_count:
                    # Parameter count mismatch - cannot use bulk
                    return False
        
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
                parameters = None

                if isinstance(data, (list, tuple)):
                    # Positional parameters
                    parameters = list(data)
                else:
                    raise ProgrammingError(f"wrong parameter type")

                if self._force_binary:
                    # Prepare the statement

                    if (self._stmt is not None):
                        if (self._stmt.sql != sql):
                            self.connection._client.close_prepared_statement(self._stmt)
                            self._stmt = None

                    if (self._stmt is None):
                        self._stmt = self.connection._client.prepare_statement(sql)


                    # Execute with parameters using ExecutePacket
                    from .impl.message.client.execute_packet import ExecutePacket
                    execute_packet = ExecutePacket(self._stmt.statement_id, parameters, sql)
                    self._completions = self.connection._client.execute(execute_packet, self._config, effective_buffered, prepare_stmt_packet=self._stmt)

                else:

                    sql_bytes, param_positions = split_sql_parts(sql)

                    # Validate parameter count
                    placeholder_count = len(param_positions) // 2  # Positions come in pairs
                    if len(parameters) < placeholder_count:
                        raise ProgrammingError(
                            f"Parameter count mismatch: SQL has {placeholder_count} placeholders, "
                            f"but only {len(parameters)} parameters provided"
                        )
                    # Use parameterized query packet with bytes
                    query_packet = QueryWithParamPacket(sql_bytes, param_positions, parameters)
                    self._completions = self.connection._client.execute(query_packet, self._config, effective_buffered)

            else:
                # Use simple query packet
                query_packet = QueryPacket(sql)
                self._completions = self.connection._client.execute(query_packet, self._config, effective_buffered)
            
            # Process the completions to extract result data
            self._completion_index = 0
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

            # Check if server supports COM_STMT_BULK_EXECUTE (check once for both paths)
            from mariadb_shared import constants
            context = self.connection._client.context
            use_bulk = context.has_capability(constants.CAPABILITY.BULK_OPERATIONS) and len(data) > 0 and len(data[0]) > 0
            
            commands = []
            
            # Always prepare statement when using bulk operations (required for COM_STMT_BULK_EXECUTE)
            if use_bulk or self._force_binary:
                if (self._stmt is not None):
                    if (self._stmt.sql != sql):
                        self.connection._client.close_prepared_statement(self._stmt)
                        self._stmt = None

                if (self._stmt is None):
                    self._stmt = self.connection._client.prepare_statement(sql)
                
                if use_bulk and self._can_use_bulk_execute(data):
                    # Use COM_STMT_BULK_EXECUTE for efficient bulk execution
                    from .impl.message.client.bulk_execute_packet import BulkExecutePacket
                    bulk_packet = BulkExecutePacket(self._stmt.statement_id, data, sql)
                    self._completions = self.connection._client.execute(bulk_packet, self._config, True)
                    self._completion_index = 0
                else: 
                    # Fallback to individual COM_STMT_EXECUTE packets (when bulk not available but binary forced)
                    from .impl.message.client.execute_packet import ExecutePacket
                    
                    for params in data:
                        parameters = None
                        if params:
                            parameters = list(params)
                        
                        if parameters:
                            if len(parameters) < self._stmt.parameter_count:
                                raise ProgrammingError(
                                    f"Parameter count mismatch: SQL has {self._stmt.parameter_count} placeholders, "
                                    f"but only {len(parameters)} parameters provided"
                                )
                        
                        execute_packet = ExecutePacket(self._stmt.statement_id, parameters, sql)
                        commands.append(execute_packet)
                    completions = self.connection._client.execute_many(commands, self._config, True, self._stmt)
                    self._process_executemany_completions(completions)   
            else:
                # Text protocol fallback (when bulk not available and binary not forced)
                sql_bytes, param_positions = split_sql_parts(sql)

                placeholder_count = len(param_positions) // 2  # Positions come in pairs

                for params in data:
                    parameters = None
                    if params:
                        parameters = list(params)

                    if parameters:
                        if len(parameters) < placeholder_count:
                            raise ProgrammingError(
                                f"Parameter count mismatch: SQL has {placeholder_count} placeholders, "
                                f"but only {len(parameters)} parameters provided"
                                )
                    query_packet = QueryWithParamPacket(sql_bytes, param_positions, parameters)
                    commands.append(query_packet)

                self._completions = self.connection._client.execute_many(commands, self._config, True, self._stmt)
                self._process_executemany_completions(self._completions)

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
        
        result = self._result
        if result is None:
            raise ProgrammingError("No result set to fetch from")
        
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
        
        result = self._result
        if result is None:
            raise ProgrammingError("No result set to fetch from")
        
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
        
        result = self._result
        if result is None:
            raise ProgrammingError("No result set to fetch from")
        
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
            
            # Cache client reference
            client = self.connection._client
            
            # Prepare the statement
            stmt = self._stmt
            if stmt is not None and stmt.sql != call_sql:
                client.close_prepared_statement(stmt)
                self._stmt = None
                stmt = None

            if stmt is None:
                self._stmt = client.prepare_statement(call_sql)
            
            # Execute with parameters using ExecutePacket
            from .impl.message.client.execute_packet import ExecutePacket
            execute_packet = ExecutePacket(self._stmt.statement_id, list(args), call_sql)
            self._completions = client.execute(execute_packet, self._config, self._stmt)
            self._completion_index = 0
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
