# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from collections import namedtuple
from typing import Sequence, Optional, List, Any, Union, Dict, TYPE_CHECKING

from mariadb_shared.async_cursor_common import AsyncCursorCommon

from .impl.result import AsyncResult

from .base_cursor import BaseCursor, ROWS_ALL, RESULT_TUPLE, RESULT_NAMEDTUPLE, RESULT_DICTIONARY
from .exceptions import DatabaseError, ProgrammingError, NotSupportedError, OperationalError
from .impl.message.client.query_packet import QueryPacket, QueryWithParamPacket
from .impl.sql_parser import split_sql_parts
from .impl.message.server.prepare_stmt_packet import PrepareStmtPacket

if TYPE_CHECKING:
    from .base_connection import BaseConnection
    from .async_connection import AsyncConnection

class AsyncCursor(BaseCursor[AsyncResult, 'AsyncConnection'], AsyncCursorCommon):
    """
    Asynchronous MariaDB Cursor Object
    
    Provides async methods for executing SQL queries and retrieving results.
    Supports both regular queries and prepared statements.

    """
    
    # =========================================================================
    # Initialization and Lifecycle
    # =========================================================================

    def __init__(self, connection: 'BaseConnection', **kwargs):
        """
        Initialize asynchronous cursor with a connection
        
        Args:
            connection: Database connection object
            **kwargs: Cursor options:
                - buffered: Buffer all results immediately
                - named_tuple: Return rows as named tuples
                - dictionary: Return rows as dictionaries
        """
        super().__init__(connection, **kwargs)

    async def close(self) -> None:
        """
        Close the cursor and free resources
        
        Consumes any remaining streaming results before closing.
        After closing, the cursor cannot be used anymore.
        """
        if not self._closed:
            # Consume any remaining streaming results
            if self._result is not None and self._result.streaming():
                try:
                    await self._result.fetch_remaining()
                except Exception:
                    pass  # Ignore errors during close
            
            self._closed = True
            self.arraysize = 1
            self._completions = []
            self._completion_index = 0
            self._config = None
            self._result = None
    
    # =========================================================================
    # Query Execution Methods
    # =========================================================================
        
    async def execute(self, sql: str, data: Optional[Union[Sequence[Any], dict]] = None, buffered: Optional[bool] = None) -> None:
        """
        Execute a SQL query or command asynchronously
        
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
            >>> await cursor.execute("SELECT * FROM users WHERE id = ?", (1,))
            >>> await cursor.execute("INSERT INTO users VALUES (?, ?)", (1, 'John'))
        """
        """
        Execute a database query or command
        
        Args:
            sql: SQL statement to execute
            data: Optional parameters for the statement
            buffered: Override cursor's buffered setting for this execution
        """
        self._check_closed()
        
        # Validate SQL type
        if not isinstance(sql, str):
            raise TypeError("SQL statement must be a string")
        if (not sql):
            raise ProgrammingError("Empty SQL statement")

        # Consume any pending streaming results before executing new query
        if self._result is not None and self._result.streaming():
            await self._result.fetch_remaining()

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
                            await self.connection._client.close_prepared_statement(self._stmt)
                            self._stmt = None

                    if (self._stmt is None):
                        self._stmt = await self.connection._client.prepare_statement(sql)


                    # Execute with parameters using ExecutePacket
                    from .impl.message.client.execute_packet import ExecutePacket
                    execute_packet = ExecutePacket(self._stmt.statement_id, parameters, sql)
                    completions = await self.connection._client.execute(execute_packet, self._config, effective_buffered, prepare_stmt_packet=self._stmt)

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
                    completions = await self.connection._client.execute(query_packet, self._config, effective_buffered)

            else:
                # Use simple query packet
                query_packet = QueryPacket(sql)
                completions = await self.connection._client.execute(query_packet, self._config, effective_buffered)
            
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
        
    async def executemany(self, sql: str, data: Sequence[Union[Sequence[Any], dict]], buffered: Optional[bool] = None) -> None:
        """
        Execute a SQL statement multiple times with different parameter sets
        
        More efficient than calling execute() multiple times as it can
        batch operations and reduce round trips.
        
        Args:
            sql: SQL statement to execute (typically INSERT, UPDATE, DELETE)
            data: Sequence of parameter sequences, one for each execution
            buffered: Override cursor's buffered setting
                
        Raises:
            ProgrammingError: If cursor is closed
            DatabaseError: If execution fails
            
        Example:
            >>> await cursor.executemany(
            ...     "INSERT INTO users VALUES (?, ?)",
            ...     [(1, 'Alice'), (2, 'Bob'), (3, 'Charlie')]
            ... )
        """
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
        
        # Check if data is None or not an array-like type
        if data is None or not hasattr(data, '__iter__') or isinstance(data, (str, bytes)):
            raise ProgrammingError("No data provided")
        
        # Consume any pending streaming results before executing new query
        if self._result is not None and self._result.streaming():
            await self._result.fetch_remaining()

        # If data is an empty list/tuple, return early with rowcount=0
        if not data:
            self._rowcount = 0
            return
        
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
                compl = await self.connection._client.execute(query_packet, self._config, effective_buffered)
                completions.extend(compl)

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
        
    async def fetchone(self) -> Optional[Any]:
        """
        Fetch the next row from the result set
        
        Returns:
            Next row as tuple, named tuple, or dict (depending on cursor options),
            or None if no more rows available
            
        Raises:
            ProgrammingError: If cursor is closed or no result set available
            
        Example:
            >>> await cursor.execute("SELECT id, name FROM users")
            >>> row = await cursor.fetchone()
            >>> print(row)  # (1, 'Alice')
        """
        """Fetch the next row of a query result set"""
        if self._closed:
            raise ProgrammingError("Cursor is closed")

        # Allow fetching from buffered results even if connection is closed
        if self.connection._closed and (self._result is None or self._result.streaming()):
            raise ProgrammingError("Connection is closed")
        
        # DB-API 2.0: Raise error if no result set
        if self._result is None:
            raise ProgrammingError("No result set to fetch from")
        
        # Delegate to Result object
        row = await self._result.fetch_one()
        self._rowcount = self._result.get_row_count()
        if row is not None:
            # Apply row formatting
            row = self._apply_row_formatting([row])[0]
        return row

        
    async def fetchmany(self, size: Optional[int] = None) -> List[Any]:
        """
        Fetch the next set of rows from the result set
        
        Args:
            size: Number of rows to fetch (default: cursor.arraysize)
            
        Returns:
            List of rows (may be empty if no more rows)
            
        Raises:
            ProgrammingError: If cursor is closed or no result set available
            
        Example:
            >>> await cursor.execute("SELECT * FROM users")
            >>> rows = await cursor.fetchmany(10)  # Fetch 10 rows
        """
        """Fetch the next set of rows of a query result"""
        if self._closed:
            raise ProgrammingError("Cursor is closed")

        # Allow fetching from buffered results even if connection is closed
        if self.connection._closed and (self._result is None or self._result.streaming()):
            raise ProgrammingError("Connection is closed")
        
        # DB-API 2.0: Raise error if no result set (description is None)
        if self.description is None:
            raise ProgrammingError("No result set to fetch from")
        
        if size is None:
            size = self.arraysize
        result = []

        for _ in range(size):
            row = await self.fetchone()
            if row is None:
                break
            result.append(row)
        return result
        
    async def fetchall(self) -> List[Any]:
        """
        Fetch all remaining rows from the result set
        
        Warning: For large result sets, this may consume significant memory.
        Consider using fetchmany() or iterating over the cursor instead.
        
        Returns:
            List of all remaining rows (may be empty)
            
        Raises:
            ProgrammingError: If cursor is closed or no result set available
            
        Example:
            >>> await cursor.execute("SELECT * FROM users")
            >>> all_rows = await cursor.fetchall()
        """
        """Fetch all remaining rows of a query result"""
        if self._closed:
            raise ProgrammingError("Cursor is closed")

        # Allow fetching from buffered results even if connection is closed
        if self.connection._closed and (self._result is None or self._result.streaming()):
            raise ProgrammingError("Connection is closed")

        # DB-API 2.0: Raise error if no result set (description is None)
        if self._result is None:
            raise ProgrammingError("No result set to fetch from")
        
        # Delegate to Result object
        rows = await self._result.fetch_all()
        self._rowcount = self._result.get_row_count()
        return self._apply_row_formatting(rows)
    
    async def scroll(self, value: int, mode: str = "relative") -> None:
        """
        Scroll the cursor in the result set to a new position according to mode (async).

        If mode is "relative" (default), value is taken as offset to the
        current position in the result set, if set to absolute, value states
        an absolute target position.
        
        For streaming (unbuffered) cursors, only forward relative scrolling is supported.
        
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
            # Call async scroll for streaming results
            try:
                await self._result.scroll(value, mode)
            except ValueError as e:
                raise ProgrammingError(str(e))
        else:
            # Call sync scroll for buffered results
            try:
                await self._result.scroll(value, mode)
            except ValueError as e:
                raise ProgrammingError(str(e))
    
       
    # =========================================================================
    # Stored Procedures
    # =========================================================================
    
    async def callproc(self, procname: str, args: Sequence[Any] = ()) -> Sequence[Any]:
        """
        Call a stored procedure asynchronously
        
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
            >>> await cursor.callproc('get_user', (1,))
            >>> result = await cursor.fetchone()
        """
        self._check_closed()
        
        try:
            # Build CALL statement with placeholders
            placeholders = ', '.join(['?' for _ in args])
            call_sql = f"CALL {procname}({placeholders})"
            
            # Prepare the statement
            stmt: PrepareStmtPacket = await self.connection._client.prepare_statement(call_sql)
            
            try:
                # Execute with parameters using ExecutePacket
                from .impl.message.client.execute_packet import ExecutePacket
                execute_packet = ExecutePacket(stmt.statement_id, list(args), call_sql)
                completions = await self.connection._client.execute(execute_packet, self._config)
                self._process_completions(completions)
                
                return None  # Match C extension behavior
                
            finally:
                await self.connection._client.close_prepared_statement(stmt)
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
    
    def __aiter__(self) -> 'AsyncCursor':
        """
        Return the cursor itself for async iteration
        
        Allows using the cursor in async for loops:
            async for row in cursor:
                process(row)
        """
        """Return async iterator for cursor"""
        return self
        
    async def __anext__(self) -> Any:
        """
        Return the next row from the result set
        
        Raises:
            StopAsyncIteration: When no more rows are available
        """
        row = await self.fetchone()
        if row is None:
            raise StopAsyncIteration
        return row
    
    # Sync iterator methods raise error
    def __iter__(self):
        """
        Sync iteration not supported for async cursor
        
        Raises:
            TypeError: Always (use 'async for' instead)
        """
        raise TypeError("Use 'async for' with AsyncCursor")
        
    def __next__(self):
        """
        Sync iteration not supported for async cursor
        
        Raises:
            TypeError: Always (use 'async for' instead)
        """
        raise TypeError("Use 'async for' with AsyncCursor")
    
    # =========================================================================
    # Context Manager
    # =========================================================================

    
    async def __aenter__(self) -> 'AsyncCursor':
        """Async context manager entry"""
        return self
        
    async def __aexit__(self, exc_type: Optional[type], exc_val: Optional[Exception], exc_tb: Optional[Any]) -> bool:
        """Async context manager exit"""
        await self.close()
        return False
    
    # Sync context manager methods raise error
    def __enter__(self):
        """Sync context manager not supported for async cursor"""
        raise TypeError("Use 'async with' with AsyncCursor")
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Sync context manager not supported for async cursor"""
        raise TypeError("Use 'async with' with AsyncCursor")
    
    # =========================================================================
    # Result Creation
    # =========================================================================
    
    def _create_complete_result(self, columns: List[Any], column_count: int, 
                               rows: List[tuple], is_binary: bool = False):
        """Create an asynchronous complete result"""
        from .impl.result import AsyncCompleteResult
        return AsyncCompleteResult(
            columns=columns,
            column_count=column_count,
            config=self._config,
            rows=rows,
            is_binary=is_binary
        )
