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


if TYPE_CHECKING:
    from .base_connection import BaseConnection
    from .sync_connection import SyncConnection

class SyncCursor(BaseCursor[SyncResult, 'SyncConnection']):
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
                self._client.close_prepared_statement(self._stmt)
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
                            self._client.close_prepared_statement(self._stmt)
                            self._stmt = None

                    if (self._stmt is None):
                        self._stmt = self._client.prepare_statement(sql)


                    # Execute with parameters using ExecutePacket
                    from .impl.message.client.execute_packet import ExecutePacket
                    execute_packet = ExecutePacket(self._stmt.statement_id, parameters, sql)
                    completions = self._client.execute(execute_packet, self._config, effective_buffered, prepare_stmt_packet=self._stmt)

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
                    completions = self._client.execute(query_packet, self._config, effective_buffered)

            else:
                # Use simple query packet
                query_packet = QueryPacket(sql)
                completions = self._client.execute(query_packet, self._config, effective_buffered)
            
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

    @property
    def _client(self) -> SyncClient:
        return self.connection._client

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
        
        # Reset result state
        self._result = None
        
        try:
            completions = list()

            if data and len(data) > 0 and not isinstance(data, (list, tuple)):
                raise ProgrammingError(f"wrong parameter type")
            # Pre-parse SQL once for optimization (avoid re-parsing for each row)
            sql_bytes = None
            param_positions = None
            param_names = None
            placeholder_count = 0
            
            # For positional parameters, parse SQL once
            sql_bytes, param_positions = split_sql_parts(sql)
            placeholder_count = len(param_positions) // 2

            # Execute the statement for each parameter set
            for params in data:
                # Execute with current parameter set
                # Convert data to list format for parameter binding
                parameters = None
                if params:
                    parameters = list(params)
                
                # Validate parameter count matches placeholders
                if parameters:
                    if len(parameters) < placeholder_count:
                        raise ProgrammingError(
                            f"Parameter count mismatch: SQL has {placeholder_count} placeholders, "
                            f"but only {len(parameters)} parameters provided"
                        )
                
                # Create query packet and execute with bytes
                query_packet = QueryWithParamPacket(sql_bytes, param_positions, parameters)
                # Use provided buffered parameter or fall back to cursor default
                effective_buffered = buffered if buffered is not None else self._buffered
                compl_list = self._client.execute(query_packet, self._config, effective_buffered)
                completions.extend(compl_list)

            # Process the completions - aggregate result sets with compatible metadata
            self._process_executemany_completions(completions)

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
        if self.connection._closed and (self._result is None or self._result.streaming()):
            raise ProgrammingError("Cursor is closed")
        
        # DB-API 2.0: Raise error if no result set
        if self._result is None:
            raise ProgrammingError("No result set to fetch from")
        
        row = self._result.fetch_one()
        self._rowcount = self._result.get_row_count()
        if row is not None:
            # Apply row formatting
            row = self._apply_row_formatting([row])[0]
        return row
            
    def fetchmany(self, size: Optional[int] = None) -> List[Any]:
        """Fetch the next set of rows of a query result"""
        # Allow fetching from buffered results even if connection is closed
        if self._closed:
            raise ProgrammingError("Cursor is closed")
        if self.connection._closed and (self._result is None or self._result.streaming()):
            raise ProgrammingError("Cursor is closed")
        
        # DB-API 2.0: Raise error if no result set
        if self._result is None:
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
        
        # DB-API 2.0: Raise error if no result set
        if self._result is None:
            raise ProgrammingError("No result set to fetch from")
        
        # Delegate to Result object
        rows = self._result.fetch_all()
        self._rowcount = self._result.get_row_count()
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
        if self.connection._closed and (self._result is None or self._result.streaming()):
            raise ProgrammingError("Cursor is closed")
        
        # Check if we have a result set
        if self._result is None:
            raise ProgrammingError("Cursor doesn't have a result set")

        # For streaming results, only forward relative scrolling is allowed
        if self._result.streaming():
            if mode != "relative":
                raise ProgrammingError("Streaming cursors only support relative scroll mode")
            if value < 0:
                raise ProgrammingError("Streaming cursors only support forward scrolling")
        
        # Delegate to Result object's scroll method
        try:
            self._result.scroll(value, mode)
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
            
            # Prepare the statement
            if (self._stmt is not None and self._stmt.sql != call_sql):
                self._client.close_prepared_statement(self._stmt)
                self._stmt = None

            if (self._stmt is None):
                self._stmt = self._client.prepare_statement(call_sql)
            
            # Execute with parameters using ExecutePacket
            from .impl.message.client.execute_packet import ExecutePacket
            execute_packet = ExecutePacket(self._stmt.statement_id, list(args), call_sql)
            completions = self._client.execute(execute_packet, self._config, self._stmt)
            self._process_completions(completions)

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
                               rows: List[tuple], is_binary: bool = False):
        """Create a synchronous complete result"""
        from .impl.result import SyncCompleteResult
        return SyncCompleteResult(
            columns=columns,
            column_count=column_count,
            config=self._config,
            rows=rows,
            is_binary=is_binary
        )
