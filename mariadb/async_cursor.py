# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from __future__ import annotations

from collections import namedtuple
from typing import Sequence, Optional, List, Any, Union, Dict, TYPE_CHECKING
import asyncio
import warnings

from mariadb_shared.async_cursor_common import AsyncCursorCommon

from .impl.result import AsyncResult

from .base_cursor import BaseCursor, ROWS_ALL, RESULT_TUPLE, RESULT_NAMEDTUPLE, RESULT_DICTIONARY
from .exceptions import DatabaseError, ProgrammingError, NotSupportedError, OperationalError
from .impl.message.client.query_packet import QueryPacket, normalize_to_qmark
from mariadb_shared.constants.STATUS import NO_BACKSLASH_ESCAPES
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
    
    __slots__ = ()  # No additional attributes beyond BaseCursor
    
    def __del__(self) -> None:
        """
        Cleanup when cursor is garbage collected.
        
        If the cursor has unconsumed streaming results, schedule async cleanup
        to consume remaining data and prevent connection state corruption.
        """
        if not self._closed and self._result is not None and self._result.streaming():
            # Cursor has unconsumed streaming results - need to clean up
            try:
                # Try to get the current event loop
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Schedule async cleanup task
                    asyncio.create_task(self._async_cleanup())
                else:
                    # No running loop - warn about potential connection state issue
                    warnings.warn(
                        "AsyncCursor with unconsumed results was deleted without proper cleanup. "
                        "This may leave the connection in a bad state. "
                        "Always call 'await cursor.close()' explicitly.",
                        ResourceWarning,
                        stacklevel=2
                    )
            except RuntimeError:
                # No event loop available
                warnings.warn(
                    "AsyncCursor with unconsumed results was deleted outside of async context. "
                    "This may leave the connection in a bad state.",
                    ResourceWarning,
                    stacklevel=2
                )
    
    async def _async_cleanup(self) -> None:
        """Internal async cleanup method called from __del__"""
        try:
            await self.close()
        except Exception:
            # Ignore errors during cleanup from __del__
            pass
    
    # =========================================================================
    # Initialization and Lifecycle
    # =========================================================================

    def __init__(self, connection: 'AsyncConnection', **kwargs: Any) -> None:
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

    async def close(self) -> None:  # type: ignore[override]
        """
        Close the cursor and free resources
        
        Consumes any remaining streaming results before closing.
        After closing, the cursor cannot be used anymore.
        """
        if not self._closed:
            client = self.connection._client
            if self._stmt:
                # Release cached statement reference
                if client.prepared_statement_cache is not None:
                    client.prepared_statement_cache.release(self._stmt)
                self._stmt = None

            # Consume any remaining streaming results
            if self._result is not None and self._result.streaming():
                try:
                    await self._result.fetch_remaining()  # type: ignore[attr-defined]
                except Exception:
                    pass  # Ignore errors during close
            
            self._closed = True
            self.arraysize = 1
            self._completions = []
            self._completion_index = 0
            self._current_completion = None
        
    # =========================================================================
    # Query Execution Methods
    # =========================================================================
        
    async def execute(self, sql: str, data: Optional[Union[Sequence[Any], dict]] = None, buffered: Optional[bool] = None) -> None:  # type: ignore[override]
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
        self._check_closed()
        
        # Validate SQL type
        if not isinstance(sql, str):
            raise TypeError("SQL statement must be a string")
        if (not sql):
            raise ProgrammingError("Empty SQL statement")

        # Note: The client already handles draining active streaming results
        # before executing new commands (see AsyncClient.execute())

        try:
            # Use provided buffered parameter or fall back to cursor default
            if buffered is not None:
                self._buffered = buffered

            if data:
                if isinstance(data, list):
                    parameters = data
                elif isinstance(data, tuple):
                    parameters = list(data)
                elif isinstance(data, dict):
                    # Named parameters
                    parameters = data  # type: ignore[assignment]
                else:
                    raise ProgrammingError(f"wrong parameter type")

                client = self.connection._client
                config = self._config or self.connection._configuration
                if not isinstance(parameters, dict) and self._use_binary:  # type: ignore[unreachable]
                    from .impl.message.client.execute_packet import ExecutePacket
                    execute_packet = ExecutePacket(None, parameters, sql)  # type: ignore[arg-type]
                    self._completions = (await client.execute_stmt(sql, [execute_packet], config, self._buffered))[0]
                else:
                    # Named parameters use text protocol with substitution
                    no_backslash_escapes = (client.context.server_status & NO_BACKSLASH_ESCAPES) > 0
                    query_packet = QueryPacket.from_substitute(sql, parameters, no_backslash_escapes)
                    self._completions = await client.execute(query_packet, config, self._buffered)

            else:
                client = self.connection._client
                config = self._config or self.connection._configuration
                # Use simple query packet
                query_packet = QueryPacket.from_sql(sql)
                self._completions = await client.execute(query_packet, config, self._buffered)
            
            self._completion_index = 0
            self._current_completion = self._completions[0]
                
        except DatabaseError as e:
            raise e                
        except Exception as e:
            raise self._exception_factory.create_exception(
                f"Execute failed: {e}",
                errno=2013,
                sql_state='HY000',
                sql= sql
            )
        
    async def executemany(self, sql: str, data: Sequence[Union[Sequence[Any], dict]], buffered: Optional[bool] = None) -> None:  # type: ignore[override]
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
            await self._result.fetch_remaining()  # type: ignore[attr-defined]

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
            client = self.connection._client
            config = self._config or self.connection._configuration
            context = client.context
            
            # Use BULK_UNIT_RESULTS capability (MariaDB 11.5+) instead of BULK_OPERATIONS
            # to avoid MariaDB 10.6-11.4 bug where bulk execute with cached statements
            # returns error packets with errno=0 and empty messages
            # Don't use bulk if all parameter sets are empty (no parameters)
            has_parameters = len(data) > 0 and any(len(params) > 0 for params in data)
            use_bulk = (context.has_capability(constants.CAPABILITY.BULK_UNIT_RESULTS) and 
                       has_parameters)
            
            # Use binary protocol with normalized SQL (always qmark now)
            if use_bulk or self._use_binary:
                if use_bulk and self._can_use_bulk_execute(data):  # type: ignore[arg-type]
                    # Use COM_STMT_BULK_EXECUTE for efficient bulk execution
                    from .impl.message.client.bulk_execute_packet import BulkExecutePacket
                    bulk_packet = BulkExecutePacket(None, data, normalized_sql)  # type: ignore[arg-type]
                    self._completions = (await client.execute_stmt(normalized_sql, [bulk_packet], config, True))[0]
                    self._completion_index = 0
                else: 
                    # Fallback to individual COM_STMT_EXECUTE packets (when bulk not available but binary forced)
                    from .impl.message.client.execute_packet import ExecutePacket
                    
                    # Create all execute packets
                    execute_packets = [ExecutePacket(None, params, normalized_sql) for params in data]  # type: ignore[arg-type]
                    
                    # Execute all at once with single prepare
                    completions = await client.execute_stmt(normalized_sql, execute_packets, config, True)  # type: ignore[arg-type]

                    self._process_executemany_completions(completions)
            else:
                # Text protocol fallback (when bulk not available and binary not forced)
                # Get NO_BACKSLASH_ESCAPES status from connection
                no_backslash_escapes = (client.context.server_status & NO_BACKSLASH_ESCAPES) > 0
                
                completions = [None] * len(data)  # type: ignore[list-item]
                for i in range(len(data)):
                    params = data[i]
                    parameters = list(params) if params else []
                    # Use normalized_sql (qmark style) since parameters are already reordered
                    query_packet = QueryPacket.from_substitute(normalized_sql, parameters, no_backslash_escapes)
                    completions[i] = await client.execute(query_packet, config, True, self._stmt)

                self._process_executemany_completions(completions)
            if self._completions:
                self._current_completion = self._completions[0]

        except DatabaseError as e:
            raise e            
        except Exception as e:
            raise self._exception_factory.create_exception(
                f"ExecuteMany failed: {e}",
                errno=2013,
                sql_state='HY000',
                sql= sql
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
        if self._closed:
            raise ProgrammingError("Cursor is closed")
        
        result = self._result
        if result is None:
            raise ProgrammingError("No result set to fetch from")

        # Allow fetching from buffered results even if connection is closed
        if self.connection._closed and result.streaming():
            raise ProgrammingError("Connection is closed")
        
        # Delegate to Result object
        row = await result.fetch_one()
        if row is not None:
            # Apply row formatting
            row = self._apply_row_formatting([row])[0]
        return row

        
    async def fetchmany(self, size: Optional[int] = None) -> List[Any]:  # type: ignore[override]
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
        if self._closed:
            raise ProgrammingError("Cursor is closed")
        
        result = self._result
        if result is None:
            raise ProgrammingError("No result set to fetch from")

        # Allow fetching from buffered results even if connection is closed
        if self.connection._closed and result.streaming():
            raise ProgrammingError("Connection is closed")
        
        if size is None:
            size = self.arraysize
        
        # Optimize: fetch rows directly instead of calling fetchone repeatedly
        rows = []
        for _ in range(size):
            row = await result.fetch_one()
            if row is None:
                break
            rows.append(row)
        
        if rows:
            return self._apply_row_formatting(rows)
        return []
        
    async def fetchall(self) -> List[Any]:  # type: ignore[override]
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
        if self._closed:
            raise ProgrammingError("Cursor is closed")
        
        result = self._result
        if result is None:
            raise ProgrammingError("No result set to fetch from")

        # Allow fetching from buffered results even if connection is closed
        if self.connection._closed and result.streaming():
            raise ProgrammingError("Connection is closed")
        
        # Delegate to Result object
        rows = await result.fetch_all()
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
            await result.scroll(value, mode)
        except ValueError as e:
            raise ProgrammingError(str(e))
    
       
    # =========================================================================
    # Stored Procedures
    # =========================================================================
    
    async def callproc(self, procname: str, args: Sequence[Any] = ()) -> Sequence[Any]:  # type: ignore[override]
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
            
            # Use execute_stmt which handles prepared statement caching internally
            from .impl.message.client.execute_packet import ExecutePacket
            execute_packet = ExecutePacket(None, list(args), call_sql)  # type: ignore[arg-type]
            client = self.connection._client
            config = self._config or self.connection._configuration
            self._completions = (await client.execute_stmt(call_sql, [execute_packet], config))[0]
            self._completion_index = 0
            self._current_completion = self._completions[0]
            return None  # type: ignore[return-value]  # Match C extension behavior
        except DatabaseError as e:
            raise e
        except Exception as e:
            raise self._exception_factory.create_exception(
                f"CallProc failed: {e}",
                errno=2013,
                sql_state='HY000'
            )
        

    # =========================================================================
    # Result Creation
    # =========================================================================
    
    def _create_complete_result(self, columns: Any, column_count: int, 
                               rows: List[tuple]) -> Any:
        """Create an asynchronous complete result"""
        from .impl.result import AsyncCompleteResult
        return AsyncCompleteResult(
            columns=columns,
            column_count=column_count,
            config=self._config,  # type: ignore[arg-type]
            rows=rows
        )
