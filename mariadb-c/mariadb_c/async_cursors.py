# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

# PyPy compatibility check - prevent loading C extension async on PyPy
import sys
if hasattr(sys, 'pypy_version_info'):
    raise ImportError(
        "mariadb_c async implementation is not compatible with PyPy due to cpyext limitations. "
        "Please use the pure Python 'mariadb' package for async operations on PyPy."
    )

# Import shared constants and exceptions to avoid circular dependencies
from mariadb_shared.constants import STATUS, CAPABILITY
from mariadb_shared.constants.STATUS import NO_BACKSLASH_ESCAPES as _NO_BACKSLASH_ESCAPES
from mariadb_shared.exceptions import (
    ProgrammingError,
    NotSupportedError
)
from mariadb_shared.text_protocol import substitute_params, normalize_to_qmark
from mariadb_shared.async_cursor_common import AsyncCursorCommon
from typing import Sequence, Optional, List, Any, Union, cast
from types import TracebackType
import decimal

_Decimal = decimal.Decimal

RESULT_TUPLE = 0
RESULT_NAMEDTUPLE = 1
RESULT_DICTIONARY = 2

# Import the C cursor base class
from mariadb_c._mariadb import cursor as CCursor
from .stmt_reuse_mixin import StmtReuseMixin

class AsyncCursor(StmtReuseMixin, CCursor, AsyncCursorCommon):
    """
    MariaDB Connector/Python Async Cursor Object
    """
    
    @property
    def buffered(self) -> bool:
        """Returns the user's buffered preference (not the C cursor's internal state)"""
        return self._user_buffered
    
    @buffered.setter
    def buffered(self, value: bool) -> None:
        """Set the user's buffered preference"""
        self._user_buffered = value
    
    def __init__(self, connection: Any, **kwargs: Any) -> None:
        """
        initialization
        """
        self._bulk: int = False  # 0/1 flag (False == 0)
        self._connection = connection
        self._resulttype = RESULT_TUPLE
        self._description: Any = None
        self._use_binary: Optional[bool] = None
        self._cache_entry: Any = None
        self._local_stmt_cache: Any = None
        self._resolved_stmt_cache: Any = None  # memoised _resolve_stmt_cache() result
        self._rowcount = 0
        self._data: Any = None
        self._closed: Optional[bool] = None
        self._buffered_rows: Optional[List[Any]] = None  # For buffered cursors: list of fetched rows
        self._row_index = 0  # Current position in buffered rows

        if not connection:
            raise ProgrammingError("Invalid or no connection provided")

        # Extract parameters (same pattern as sync cursor)
        named_tuple_val: bool = kwargs.pop("named_tuple", False)
        dictionary_val: bool = kwargs.pop("dictionary", False)
        buffered_val: bool = kwargs.pop("buffered", True)
        # Inherit connection-level binary default; cursor kwarg overrides
        binary_val: bool = kwargs.pop("binary", connection._binary)
        cursor_type_val: int = kwargs.pop("cursor_type", 0)
        
        # Set Python wrapper attributes
        if named_tuple_val:
            self._resulttype = RESULT_NAMEDTUPLE
        elif dictionary_val:
            self._resulttype = RESULT_DICTIONARY
        else:
            self._resulttype = RESULT_TUPLE
        self._use_binary = binary_val
        self._cursor_type: int = cursor_type_val

        # Store the user's buffered preference
        self._user_buffered = buffered_val
        
        # Call initialization of C extension cursor
        # IMPORTANT: Always pass buffered=False to C cursor - we handle buffering in Python
        super().__init__(connection,
                        named_tuple=named_tuple_val,
                        dictionary=dictionary_val,
                        buffered=False,  # Async always uses unbuffered C cursor
                        binary=binary_val,
                        **kwargs)

    def check_closed(self) -> None:
        if self._closed or super(AsyncCursor, self).closed:
            raise ProgrammingError("Cursor cannot be used anymore (it was already closed before).")
        self._connection._check_closed()

    @property
    def rownumber(self) -> Optional[int]:
        """Return the current row number (0-indexed position)"""
        # None if there is no result set or rows haven't been buffered yet;
        # otherwise the current index into the buffered rows.
        if self.field_count == 0 or self._buffered_rows is None:
            return None
        return self._row_index


    def _check_decimal_parameter(self, val: Any) -> None:
        """
        Internal use only

        Checks for unsupported parameters.
        The following parameters are not supported by MariaDB/MySQL (but also
        not part of the SQL Standard)

        - float("nan" | "inf" | "-inf")
        - Decimal("NaN" | "sNaN" | "Infinity" | "-Infinity")
        """

        if isinstance(val, float) and repr(val) in ("nan", "inf", "-inf"):
            raise NotSupportedError(f"Float value '{repr(val)}' is not supported.")
        elif isinstance(val, decimal.Decimal) and val.__str__() in ("NaN", "sNaN", "Infinity", "-Infinity"):
            raise NotSupportedError(f"Decimal value '{val.__str__()}' is not supported.")

        return None


    async def callproc(self, sp: str, data: Sequence = ()) -> None:
        """
        Executes a stored procedure sp. The data sequence must contain an
        entry for each parameter the procedure expects.

        Input/Output or Output parameters have to be retrieved by .fetch
        methods, the .sp_outparams attribute indicates if the result set
        contains output parameters.

        Arguments:
            - sp: Name of stored procedure.
            - data: Optional sequence containing data for placeholder
                    substitution.
        """
        params = ""
        if data and len(data):
            params = ("?," * len(data))[:-1]
        await self.execute("CALL %s(%s)" % (sp, params), data, _force_binary=True)

    async def nextset(self) -> Optional[bool]:
        """
        Will make the cursor skip to the next available result set,
        discarding any remaining rows from the current set.

        Returns True if another result set is available, or None if there are
        no more result sets (PEP-249).
        """

        self.check_closed()
        
        # Clear buffered rows from previous result set
        self._buffered_rows = None
        self._row_index = 0

        if self.field_count:
            await self._drain_rows()

        # Advance to the next result set without blocking the event loop
        result = self._async_next_result_start()
        while type(result) is int and result != 0:
            actual_status = await self.connection._wait_for_status(result)
            result = self._async_next_result_cont(actual_status)

        if result is False:
            # No more result sets.
            if self.connection._active_async_cursor is self:
                self.connection._active_async_cursor = None
            return None

        # A further result set is now current
        if not self._user_buffered:
            self.connection._active_async_cursor = self
        return True

    async def execute(self, statement: str, data: Sequence = (), buffered: Optional[bool] = None, _force_binary: bool = False) -> None:
        """
        Prepare and execute a SQL statement asynchronously.

        Parameters may be provided as sequence or mapping and will be bound
        to variables in the operation. Variables are specified as question
        marks (paramstyle ='qmark'), however for compatibility reasons MariaDB
        Connector/Python also supports the 'format' and 'pyformat' paramstyles
        with the restriction, that different paramstyles can't be mixed within
        a statement.

        A reference to the operation will be retained by the cursor.
        """
        self.check_closed()

        # Clear buffered rows from previous execute
        self._buffered_rows = None
        self._row_index = 0

        # Update Python-level buffering flag if specified
        if buffered is not None:
            self._user_buffered = buffered

        # Drain any active streaming result BEFORE cache operations.
        # Eviction calls db_command(COM_STMT_CLOSE, skip_check=1) which
        # bypasses mysql->status — pending unbuffered rows corrupt the protocol.
        # (Sync path handles this in StmtCache.put(); async needs an await here.)
        await self._consume_active_result()

        if not self._text:
            self._save_stmt_to_cache(self.statement)
        self._reset()

        # Mark this cursor as the active one on the connection ONLY if unbuffered
        if not self._user_buffered:
            self.connection._active_async_cursor = self

        self._rowcount = 0
        self._description = None

        # CONPY-218: Allow None as replacement for empty tuple
        data = data or ()

        if data:
            self._data = data

            # Parameterized query — decide protocol
            use_binary = _force_binary or self._use_binary

            if not isinstance(data, dict) and use_binary:
                # Validate unsupported decimal/float values for binary protocol.
                _check = self._check_decimal_parameter
                for val in data:
                    if type(val) is float or type(val) is _Decimal:
                        _check(val)
                # Binary protocol: server parses placeholders during prepare
                if self.statement != statement:
                    super()._set_statement(statement, len(data))
                    hit = self._restore_stmt_from_cache(statement)
                    self._reprepare = not hit
                    if not hit and self._local_stmt_cache is not None:
                        self._local_stmt_cache.clear()
                else:
                    self._reprepare = False
                await self._execute_binary_async()
            else:
                # Text protocol: shared parser handles placeholder discovery,
                # validation, and value conversion in a single pass.
                no_backslash = bool(self.connection.server_status & _NO_BACKSLASH_ESCAPES)
                self._transformed_statement = b"".join(substitute_params(statement, self._data, no_backslash))
                await self._execute_text_async(self._transformed_statement, statement)
        else:
            # No parameters — always text protocol
            await self._execute_text_async(statement)

        self._initresult()
        self._bulk = 0

        if self._user_buffered and self.field_count > 0:
            await self._buffer_all_rows()
    
    async def _drain_rows(self) -> None:
        """Discard all remaining rows of the current result set."""
        while await self._fetch_row_unbuffered() is not None:
            pass

    async def _buffer_all_rows(self) -> None:
        """Fetch all rows into memory for a buffered cursor.

        This is the default cursor path, so it inlines the per-row fetch and
        hoists the invariants (connection, the text/binary start/cont pair) out
        of the loop. Callers only reach here with a buffered cursor and
        field_count > 0; the end-of-result _active_async_cursor clear is
        replicated below.
        """
        rows: List[Any] = []
        self._buffered_rows = rows
        self._row_index = 0
        conn = self._connection
        drive = conn._drive
        append = rows.append
        if self._text:
            start, cont = self._async_fetch_row_start, self._async_fetch_row_cont
        else:
            start, cont = self._async_stmt_fetch_start, self._async_stmt_fetch_cont

        while True:
            row = await drive(start, cont)
            if row is None:
                if conn._active_async_cursor is self:
                    conn._active_async_cursor = None
                break
            append(row)

        # Set rowcount to the number of fetched rows
        self._rowcount = len(rows)

    async def _execute_text_async(self, sql_to_send: Union[str, bytes], original_statement: Optional[str] = None) -> None:
        """Execute text query using async non-blocking API.

        Also stores the statement for cursor.statement and sets is_text=1.
        When parameters were substituted, original_statement holds the SQL
        template while sql_to_send holds the substituted bytes.
        """
        # Store statement for cursor.statement and set is_text=1
        super()._set_text_statement(original_statement or sql_to_send)

        # Run the non-blocking query to completion
        await self.connection._drive(
            lambda: self.connection._async_real_query_start(sql_to_send),
            self.connection._async_real_query_cont)

        # Set field_count from connection so _initresult() can work properly
        self._set_field_count_from_connection()


    async def _execute_binary_async(self) -> None:
        """Execute binary query using async prepared statement protocol."""
        # Local setup only: stmt init, parameter binding (prebound), clear result.
        self._prepare_stmt_only()

        await self.connection._drive(self._async_stmt_prepare_start,
                                     self._async_stmt_prepare_cont)
        await self.connection._drive(self._async_stmt_execute_start,
                                     self._async_stmt_execute_cont)

        # Field count is already set by the C extension after stmt execution

    async def executemany(self, statement: str, parameters: Sequence[Sequence[Any] | dict[str, Any]]) -> None:
        """
        Prepare a database operation (INSERT,UPDATE,REPLACE or DELETE
        statement) and execute it against all parameter found in sequence.

        Exactly behaves like .execute() but accepts a list of tuples, where
        each tuple represents data of a row within a table.
        .executemany() only supports DML (insert, update, delete) statements.

        If the SQL statement contains a RETURNING clause, executemany()
        returns a result set containing the values for columns listed in the
        RETURNING clause.
        """

        self.check_closed()
        self._reset()

        # Reset buffered cursor state
        self._buffered_rows = None
        self._row_index = 0

        # Check if parameters is None or not an array-like type
        if parameters is None or not hasattr(parameters, '__iter__') or isinstance(parameters, (str, bytes)):
            raise ProgrammingError("No data provided")

        self.connection._last_executed_statement = statement

        # Consume any remaining rows from other cursors to avoid "Commands out of sync"
        await self._consume_active_result()
        
        # Mark this cursor as the active one on the connection ONLY if unbuffered
        if not self._user_buffered:
            self.connection._active_async_cursor = self

        # If parameters is an empty list/tuple, return early with rowcount=0
        if not len(parameters):
            self.buffered = True
            self._rowcount = 0
            return

        # If the server doesn't support bulk operations, we need to emulate
        # by looping
        # TODO: insert/replace statements are not optimized yet
        #       rowcount updating
        
        normalized_sql, param_names = normalize_to_qmark(statement)

        if param_names is not None:
            reordered: list = []
            for row in parameters:
                if not isinstance(row, dict):
                    raise ProgrammingError("Named placeholders require dict parameters")
                reordered.append([row.get(name) for name in param_names])
            parameters = reordered

        has_parameters = any(len(row) > 0 if hasattr(row, '__len__') else True for row in parameters)
        first_row = parameters[0] if hasattr(parameters, '__getitem__') else next(iter(parameters))

        if not (self.connection.extended_server_capabilities &
                (CAPABILITY.BULK_OPERATIONS >> 32)) or not has_parameters or isinstance(first_row, dict):
            count = 0
            accumulated_results: List[Any] = []

            for i, row in enumerate(parameters):
                await self.execute(normalized_sql, row)
                count += self.rowcount
                
                # If this statement has a RETURNING clause, accumulate buffered results
                # BEFORE the next execute() clears them. (cast: execute() above
                # repopulates _buffered_rows, which mypy can't see — it still has
                # it narrowed to None from the reset at the top of executemany.)
                buffered = cast(Optional[List[Any]], self._buffered_rows)
                if self.field_count > 0 and buffered is not None:
                    accumulated_results.extend(buffered)
            
            self._rowcount = count
            
            # If we accumulated results from RETURNING, restore them
            if accumulated_results:
                self._buffered_rows = accumulated_results
                self._row_index = 0
                self._user_buffered = True
        else:
            # Bulk execute: QMARK/FORMAT rows only.
            # paramcount from first row (computed above) — no SQL parse needed.
            if self.statement != normalized_sql or not self._bulk:
                super()._set_statement(normalized_sql, len(first_row))
                self._reprepare = True
            else:
                self._reprepare = False
            self._data = parameters
            self._text = False
            self._rowcount = 0
            try:
                self._prepare_bulk_only()
                await self.connection._drive(self._async_stmt_prepare_start,
                                             self._async_stmt_prepare_cont)
                await self.connection._drive(self._async_stmt_execute_start,
                                             self._async_stmt_execute_cont)
                self._finalize_bulk_result()
            except BaseException:
                if self.connection._active_async_cursor is self:
                    self.connection._active_async_cursor = None
                try:
                    self._reset()
                except Exception:
                    pass
                raise
            self._bulk = 1

    async def _consume_active_result(self) -> None:
        """
        Consume any remaining rows from the active cursor on this connection.

        Drains both _active_streaming_result (sync text + binary unbuffered)
        and _active_async_cursor (async unbuffered) to prevent "Commands out
        of sync" when executing a new query with pending results.
        """
        active = getattr(self.connection, "_active_streaming_result", None)
        if active is not None:
            active._clear_result()

        if self.connection._active_async_cursor is not None:
            active_cursor = self.connection._active_async_cursor
            try:
                if (not active_cursor._closed and
                        active_cursor.field_count > 0):
                    try:
                        await active_cursor._drain_rows()
                    except Exception:
                        pass
            except Exception:
                pass
            self.connection._active_async_cursor = None

    async def _fetch_row_unbuffered(self) -> Optional[Any]:
        """
        Internal use only.

        Fetch a single row,
        Uses cursor-level fetch_row_start/cont for the text protocol and
        stmt_fetch_start/cont for the binary protocol (prepared statements).
        """
        self.check_closed()

        if not self._text:
            result = await self.connection._drive(self._async_stmt_fetch_start,
                                                  self._async_stmt_fetch_cont)
        else:
            result = await self.connection._drive(self._async_fetch_row_start,
                                                  self._async_fetch_row_cont)

        if result is None and self.connection._active_async_cursor is self:
            self.connection._active_async_cursor = None
        return result

    async def close(self) -> None:
        """
        Closes the cursor.

        If the cursor has pending or unread results, .close() will cancel them
        so that further operations using the same connection can be executed.

        The cursor will be unusable from this point forward; an Error
        (or subclass) exception will be raised if any operation is attempted
        with the cursor.
        """
        if self._closed:
            return

        if not self._text:
            self._save_stmt_to_cache(self.statement)

        # Close the per-cursor prepared statement (if connection cache off).
        self._close_local_stmt_cache()

        # CONPY-231: fix memory leak
        if self._data:
            del self._data

        if not self.connection._closed:
            if self.connection._active_async_cursor is self and self.field_count > 0:
                try:
                    # Drain the current result set, then any further sets
                    await self._drain_rows()
                    while await self.nextset() is not None:
                        pass
                except Exception:
                    pass
                self.connection._active_async_cursor = None
            super().close()

        if self.connection._active_async_cursor is self:
            self.connection._active_async_cursor = None

        self._closed = True

    async def fetchone(self) -> Optional[Any]:
        """
        Fetch the next row of a query result set, returning a single sequence,
        or None if no more data is available.

        An exception will be raised if the previous call to execute() didn't
        produce a result set or execute() wasn't called before.
        """
        if not (self.buffered and self._text):
            self.check_closed()

        # Check if there's a result set
        if self.field_count == 0:
            raise ProgrammingError("Cursor doesn't have a result set")

        # Lazy buffering: buffer rows if needed (e.g., after nextset())
        if self._user_buffered and self._buffered_rows is None and self.field_count > 0:
            await self._buffer_all_rows()

        # If buffered mode, serve from buffer
        if self._user_buffered and self._buffered_rows is not None:
            if self._row_index < len(self._buffered_rows):
                row = self._buffered_rows[self._row_index]
                self._row_index += 1
                return row
            return None
        
        row = await self._fetch_row_unbuffered()
        return row

    async def fetchmany(self, size: int = 0) -> List[Any]:
        """
        Fetch the next set of rows of a query result, returning a sequence
        of sequences (e.g. a list of tuples). An empty sequence is returned
        when no more rows are available.

        The number of rows to fetch per call is specified by the parameter.
        If it is not given, the cursor's arraysize determines the number
        of rows to be fetched. The method should try to fetch as many rows
        as indicated by the size parameter.
        If this is not possible due to the specified number of rows not being
        available, fewer rows may be returned.

        An exception will be raised if the previous call to execute() didn't
        produce a result set or execute() wasn't called before.
        """
        if not (self.buffered and self._text):
            self.check_closed()

        # Check if there's a result set
        if self.field_count == 0:
            raise ProgrammingError("Cursor doesn't have a result set")

        if size == 0:
            size = self.arraysize

        # Lazy buffering: buffer rows if needed (e.g., after nextset())
        if self._user_buffered and self._buffered_rows is None and self.field_count > 0:
            await self._buffer_all_rows()

        # If buffered mode, serve from buffer
        if self._user_buffered and self._buffered_rows is not None:
            end_index = min(self._row_index + size, len(self._buffered_rows))
            rows = self._buffered_rows[self._row_index:end_index]
            self._row_index = end_index
            return rows

        # For unbuffered cursors, fetch rows and update rowcount cumulatively
        rows = []
        for _ in range(size):
            row = await self._fetch_row_unbuffered()
            if row is None:
                break
            rows.append(row)
        
        # Update rowcount cumulatively for unbuffered cursors
        self._rowcount += len(rows)
        return rows

    async def fetchall(self) -> List[Any]:
        """
        Fetch all remaining rows of a query result, returning them as a
        sequence of sequences (e.g. a list of tuples).

        An exception will be raised if the previous call to execute() didn't
        produce a result set or execute() wasn't called before.
        """

        if not (self.buffered and self._text):
            self.check_closed()
        
        # Check if there's a result set
        if self.field_count == 0:
            raise ProgrammingError("Cursor doesn't have a result set")
        
        # Lazy buffering: buffer rows if needed (e.g., after nextset())
        if self._user_buffered and self._buffered_rows is None and self.field_count > 0:
            await self._buffer_all_rows()
        
        # If buffered mode, serve remaining rows from buffer
        if self._user_buffered and self._buffered_rows is not None:
            rows = self._buffered_rows[self._row_index:]
            self._row_index = len(self._buffered_rows)
            return rows
        
        # For unbuffered cursors, fetch all rows and update rowcount
        rows = []
        while True:
            row = await self._fetch_row_unbuffered()
            if row is None:
                break
            rows.append(row)
        
        # Update rowcount for unbuffered cursors
        self._rowcount = len(rows)
        return rows

    def __aiter__(self) -> "AsyncCursor":
        return self
    
    async def __anext__(self) -> Any:
        row = await self.fetchone()
        if row is None:
            raise StopAsyncIteration
        return row

    async def scroll(self, value: int, mode: str = "relative") -> None:
        """
        Scroll the cursor in the result set to a new position according to
        mode.

        If mode is "relative" (default), value is taken as offset to the
        current position in the result set, if set to absolute, value states
        an absolute target position.
        """
        if not (self.buffered and self._text):
            self.check_closed()

        if self.field_count == 0:
            raise ProgrammingError("Cursor doesn't have a result set")

        if not self._user_buffered:
            raise ProgrammingError("This method is available only "
                                           "for cursors with a buffered "
                                           "result set.")

        if mode != "absolute" and mode != "relative":
            raise ProgrammingError("Invalid or unknown scroll "
                                           "mode specified.")

        if value == 0 and mode == "relative":
            return

        # For buffered cursors, use _row_index instead of rownumber
        if mode == "relative":
            new_pos = self._row_index + value
        else:
            new_pos = value

        # Validate position
        if new_pos < 0 or new_pos > len(self._buffered_rows or []):
            raise ProgrammingError("Position value is out of range.")

        self._row_index = new_pos

    def setinputsizes(self, size: int) -> None:
        """
        Required by PEP-249. Does nothing in MariaDB Connector/Python
        """

        return

    def setoutputsize(self, size: int) -> None:
        """
        Required by PEP-249. Does nothing in MariaDB Connector/Python
        """

        return

    async def __aenter__(self) -> "AsyncCursor":
        """Returns a copy of the cursor."""

        return self

    async def __aexit__(self, exc_type: Optional[type[BaseException]], exc_val: Optional[BaseException], exc_tb: Optional[TracebackType]) -> None:
        """Closes cursor."""
        await self.close()

    @property
    def rowcount(self) -> int:
        """
        This read-only attribute specifies the number of rows that the last\
        execute*() produced (for DQL statements like SELECT) or affected
        (for DML statements like UPDATE or INSERT).
        The return value is -1 in case no .execute*() has been performed
        on the cursor or the rowcount of the last operation  cannot be
        determined by the interface.
        """

        # Even if PEP-249 permits operations on a closed cursor, we don't
        # raise an exception if the cursor or the underlying connection
        # was closed (See CONPY-269), instead we will return -1
        try:
            self.check_closed()
        except ProgrammingError:
            return -1

        # For buffered SELECT statements, return the number of buffered rows
        if self._user_buffered and self._buffered_rows is not None:
            return len(self._buffered_rows)
        
        # For executemany() aggregation, return accumulated rowcount
        if self._rowcount > 0:
            return self._rowcount
        count: int = super().rowcount
        return count

    @property
    def sp_outparams(self) -> bool:
        """
        Indicates if the current result set contains in out or out parameter
        from a previous executed stored procedure
        """
        self.check_closed()

        return bool(self.connection.server_status & STATUS.PS_OUT_PARAMS)

    @property
    def lastrowid(self) -> Optional[int]:
        """
        Returns the ID generated by a query on a table with a column having
        the AUTO_INCREMENT attribute or the value for the last usage of
        LAST_INSERT_ID().

        If the last query wasn't an INSERT or UPDATE
        statement or if the modified table does not have a column with the
        AUTO_INCREMENT attribute and LAST_INSERT_ID was not used, the returned
        value will be None
        """
        self.check_closed()

        id: int = self.insert_id
        if id > 0:
            return id
        return None

    @property
    def connection(self) -> Any:
        """
        Read-Only attribute which returns the reference to the connection
        object on which the cursor was created.
        """

        return self._connection
