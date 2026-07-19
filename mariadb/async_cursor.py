# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from __future__ import annotations

from typing import Dict, Sequence, List, Any, TYPE_CHECKING
import warnings

from mariadb.impl.completion import Completion
from mariadb_shared.async_cursor_common import AsyncCursorCommon

from .impl.result import AsyncResult

from .base_cursor import BaseCursor
from .exceptions import DatabaseError, ProgrammingError, NotSupportedError
from .impl.message.client.query_packet import QueryPacket, normalize_to_qmark
from mariadb_shared.constants.STATUS import NO_BACKSLASH_ESCAPES, MORE_RESULTS_EXIST

if TYPE_CHECKING:
    from .async_connection import AsyncConnection
    from .impl.message.server.column_definition_packet import ColumnsDefinition
    from .impl.result import AsyncCompleteResult

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
            warnings.warn(
                "AsyncCursor with unconsumed streaming results was garbage "
                "collected without an explicit 'await cursor.close()'. Always "
                "close async cursors explicitly (or use 'async with'); the "
                "connection may otherwise hold an undrained result set.",
                ResourceWarning,
                stacklevel=2,
            )

    # =========================================================================
    # Initialization and Lifecycle
    # =========================================================================

    async def close(self) -> None:  # type: ignore[override]
        """
        Close the cursor and free resources

        Consumes any remaining streaming results before closing.
        After closing, the cursor cannot be used anymore.
        """
        if not self._closed:
            client = self.connection._client # pyright: ignore[reportPrivateUsage]
            if self._stmt:
                # Release cached statement reference
                if client.prepared_statement_cache is not None:
                    client.prepared_statement_cache.release(self._stmt)
                self._stmt = None

            # Close the per-cursor prepared statement (if connection cache off).
            self._close_local_stmt_cache()

            # Drain any remaining streaming result(s) so the connection is left
            # ready for the next command.
            await client.drain_streaming_result(self._result, self._use_binary, False)

            self._closed = True
            self.arraysize = 1
            self._completions = []
            self._completion_index = 0
            self._current_completion = None

    # =========================================================================
    # Query Execution Methods
    # =========================================================================

    async def execute(self, sql: str, data: Sequence[Any] | dict[str, Any] | None = None, buffered: bool | None = None) -> None:  # type: ignore[override]
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
        if not isinstance(sql, str): # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("SQL statement must be a string")
        if (not sql):
            raise ProgrammingError("Empty SQL statement")

        # Note: The client already handles draining active streaming results
        # before executing new commands (see AsyncClient.execute())

        try:
            # Use provided buffered parameter or fall back to cursor default
            if buffered is not None:
                self._buffered = buffered

            client = self.connection._client # pyright: ignore[reportPrivateUsage]
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

                
                if not isinstance(parameters, dict) and self._use_binary:  # type: ignore[unreachable]
                    from .impl.message.client.execute_packet import ExecutePacket
                    execute_packet = ExecutePacket(None, parameters, sql)
                    self._completions = (await client.execute_stmt(sql, [execute_packet], self._config, self._buffered, self._resolve_stmt_cache()))[0]
                else:
                    # Named parameters use text protocol with substitution
                    no_backslash_escapes = (client.context.server_status & NO_BACKSLASH_ESCAPES) > 0
                    query_packet = QueryPacket.from_substitute(sql, parameters, no_backslash_escapes)
                    self._completions = await client.execute(query_packet, self._config, self._buffered)
            else:
                # Use simple query packet
                query_packet = QueryPacket.from_sql(sql)
                self._completions = await client.execute(query_packet, self._config, self._buffered)

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

    async def executemany(self, sql: str, data: Sequence[Sequence[Any] | dict[str, Any]], buffered: bool | None = None) -> None:  # type: ignore[override]
        """
        Execute a statement multiple times with different parameter sets

        Args:
            sql: SQL statement to execute
            data: Sequence of parameter sequences
            buffered: Override cursor's buffered setting for this execution
        """
        self._check_closed()

        # Validate SQL type
        if not isinstance(sql, str): # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("SQL statement must be a string")

        # Consume any pending streaming results before executing new query
        if self._result is not None and self._result.streaming():
            await self._result.fetch_remaining()  # type: ignore[attr-defined]

        # Check if data is None or not an array-like type
        if data is None or not hasattr(data, '__iter__') or isinstance(data, (str, bytes)): # pyright: ignore[reportUnnecessaryComparison]
            raise ProgrammingError("No data provided")

        try:
            if data and len(data) > 0 and not isinstance(data, (list, tuple)):
                raise ProgrammingError(f"wrong parameter type")

            # Normalize SQL to qmark style and get parameter mapping
            normalized_sql, param_names = normalize_to_qmark(sql)

            # Reorder parameters if needed (for named/pyformat styles)
            if param_names is not None:
                # Named parameters - reorder each parameter set according to param_names
                reordered_data : List[List[Any]] = []
                for param_set in data:
                    if isinstance(param_set, dict):
                        reordered = [param_set.get(name) for name in param_names]
                        reordered_data.append(reordered)
                    else:
                        raise ProgrammingError("Named placeholders require dict parameters")
                data = reordered_data

            # Check if server supports COM_STMT_BULK_EXECUTE
            from mariadb_shared import constants
            client = self.connection._client # pyright: ignore[reportPrivateUsage]

            context = client.context

            # Use BULK_UNIT_RESULTS capability (MariaDB 11.5+) instead of BULK_OPERATIONS
            # to avoid MariaDB 10.6-11.4 bug where bulk execute with cached statements
            # returns error packets with errno=0 and empty messages
            # Don't use bulk if all parameter sets are empty (no parameters)
            has_parameters = len(data) > 0 and any(len(params) > 0 for params in data)
            use_bulk = (context.has_capability(constants.CAPABILITY.BULK_UNIT_RESULTS) and
                       has_parameters)
            completions : List[List[Completion]] 
            # Use binary protocol with normalized SQL (always qmark now)
            if use_bulk or self._use_binary:
                if use_bulk and self._can_use_bulk_execute(data):  # type: ignore[arg-type]
                    # Use COM_STMT_BULK_EXECUTE for efficient bulk execution
                    from .impl.message.client.bulk_execute_packet import BulkExecutePacket
                    bulk_packet = BulkExecutePacket(None, data, normalized_sql)  # type: ignore[arg-type]
                    self._completions = (await client.execute_stmt(normalized_sql, [bulk_packet], self._config, True, self._resolve_stmt_cache()))[0]
                    self._completion_index = 0
                else:
                    # Fallback to individual COM_STMT_EXECUTE packets (when bulk not available but binary forced)
                    from .impl.message.client.execute_packet import ExecutePacket

                    # Create all execute packets
                    execute_packets = [ExecutePacket(None, params, normalized_sql) for params in data]  # type: ignore[arg-type]

                    # Execute all at once with single prepare
                    completions = await client.execute_stmt(normalized_sql, execute_packets, self._config, True, self._resolve_stmt_cache())  # type: ignore[arg-type]

                    self._process_executemany_completions(completions)
            else:
                # Text protocol fallback (when bulk not available and binary not forced)
                # Get NO_BACKSLASH_ESCAPES status from connection
                no_backslash_escapes = (client.context.server_status & NO_BACKSLASH_ESCAPES) > 0

                completions = []
                for i in range(len(data)):
                    params = data[i]
                    parameters = list(params) if params else []
                    # Use normalized_sql (qmark style) since parameters are already reordered
                    query_packet = QueryPacket.from_substitute(normalized_sql, parameters, no_backslash_escapes)
                    # Text-protocol fallback has no prepared statement to thread.
                    completions.append(await client.execute(query_packet, self._config, True, None))

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

    async def fetchone(self) -> tuple[Any, ...] | Dict[str, Any] | None:  # type: ignore[override]
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
        if self.connection.is_closed and result.streaming():
            raise ProgrammingError("Connection is closed")

        # Delegate to Result object
        row = await result.fetch_one()
        if row is not None:
            # Apply row formatting
            return self._apply_row_formatting([row])[0]
        return row


    async def fetchmany(self, size: int | None = None) -> List[tuple[Any, ...]] | List[Dict[str, Any]]:  # type: ignore[override]
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
        if self.connection.is_closed and result.streaming():
            raise ProgrammingError("Connection is closed")

        if size is None:
            size = self.arraysize

        # Optimize: fetch rows directly instead of calling fetchone repeatedly
        rows : List[tuple[Any, ...]]= []
        for _ in range(size):
            row = await result.fetch_one()
            if row is None:
                break
            rows.append(row)

        if rows:
            return self._apply_row_formatting(rows)
        return []

    async def fetchall(self) -> List[tuple[Any, ...]] | List[Dict[str, Any]]:  # type: ignore[override]
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
        if self.connection.is_closed and result.streaming():
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

        if self.connection.is_closed and result.streaming():
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


    async def nextset(self) -> bool | None:  # type: ignore[override]
        """Advance to the next available result set.

        Returns True if another result set is available, or None if there are no
        more.
        """
        self._check_closed()

        # Buffered cursors: execute() already read every result set into
        # _completions, so just advance the in-memory index (no wire I/O).
        if self._buffered:
            self._completion_index += 1
            if self._completion_index >= len(self._completions):
                self._current_completion = None
                return None
            self._current_completion = self._completions[self._completion_index]
            return True

        # Streaming (unbuffered) cursor: read the next set from the wire.
        client = self.connection._client # pyright: ignore[reportPrivateUsage]
        completion = self._current_completion
        result_set = completion.result_set if (completion is not None and completion.has_result_set()) else None
        if result_set is not None and result_set.streaming():
            await client.drain_streaming_result(self._result, self._use_binary, True)

        if (client.context.server_status & MORE_RESULTS_EXIST) == 0:
            self._current_completion = None
            return None
        if self._use_binary:
            raise NotSupportedError(
                "nextset() across multiple result sets is not supported on a "
                "binary streaming cursor (binary=True, buffered=False); use a "
                "buffered cursor for multi-result binary statements")
        next_completion = await client.read_next_result(False, self._config)
        if next_completion is None:
            self._current_completion = None
            return None
        self._completions.append(next_completion)
        self._completion_index += 1
        self._current_completion = next_completion
        return True


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
            execute_packet = ExecutePacket(None, list(args), call_sql)
            client = self.connection._client # pyright: ignore[reportPrivateUsage]
            self._completions = (await client.execute_stmt(call_sql, [execute_packet], self._config, True, self._resolve_stmt_cache()))[0]
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

    def _create_complete_result(self, columns: 'ColumnsDefinition', column_count: int,
                               rows: List[tuple[Any, ...]]) -> 'AsyncCompleteResult':
        """Create an asynchronous complete result"""
        from .impl.result import AsyncCompleteResult
        return AsyncCompleteResult(
            columns=columns,
            column_count=column_count,
            config=self._config,
            rows=rows
        )
