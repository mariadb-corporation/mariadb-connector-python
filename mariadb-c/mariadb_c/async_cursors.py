# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

# PyPy compatibility check - prevent loading C extension async on PyPy
import sys
if hasattr(sys, 'pypy_version_info'):
    raise ImportError(
        "mariadb_c async implementation is not compatible with PyPy due to cpyext limitations. "
        "Please use the pure Python 'mariadb' package for async operations on PyPy."
    )

import asyncio
import datetime
from numbers import Number

# Import shared constants and exceptions to avoid circular dependencies
from mariadb_shared.constants import CURSOR, STATUS, CAPABILITY, INDICATOR
from mariadb_shared.exceptions import (
    ProgrammingError,
    NotSupportedError
)
from mariadb_shared.async_cursor_common import AsyncCursorCommon
from typing import Sequence, Optional, Any, List, Tuple
import decimal

# Concrete numeric types - tuple for isinstance (must support subclasses)
_NUMERIC_TYPES = (int, float, complex, decimal.Decimal)

PARAMSTYLE_QMARK = 1
PARAMSTYLE_FORMAT = 2
PARAMSTYLE_PYFORMAT = 3

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

# Wait status flags for non-blocking operations
MYSQL_WAIT_READ = 1
MYSQL_WAIT_WRITE = 2
MYSQL_WAIT_EXCEPT = 4
MYSQL_WAIT_TIMEOUT = 8

# Import the C cursor base class
from mariadb_c._mariadb import cursor as CCursor
class AsyncCursor(CCursor, AsyncCursorCommon):
    """
    MariaDB Connector/Python Async Cursor Object
    """
    
    @property
    def buffered(self):
        """Returns the user's buffered preference (not the C cursor's internal state)"""
        return self._user_buffered
    
    @buffered.setter
    def buffered(self, value):
        """Set the user's buffered preference"""
        self._user_buffered = value
    
    def __init__(self, connection, **kwargs):
        """
        initialization
        """
        self._bulk = False
        self._dictionary = False
        self._named_tuple = False
        self._connection = connection
        self._resulttype = RESULT_TUPLE
        self._description = None
        self._transformed_statement = None
        self._prepared = False
        self._prev_stmt = None
        self._use_binary = None
        self._rowcount = 0
        self._parseinfo = None
        self._data = None
        self._thread_id = connection.thread_id
        self._closed= None
        self._buffered_rows = None  # For buffered cursors: list of fetched rows
        self._row_index = 0  # Current position in buffered rows

        if not connection:
            raise ProgrammingError("Invalid or no connection provided")

        # Extract parameters (same pattern as sync cursor)
        named_tuple_val = kwargs.pop("named_tuple", False)
        dictionary_val = kwargs.pop("dictionary", False)
        buffered_val = kwargs.pop("buffered", True)
        prepared_val = kwargs.pop("prepared", False)
        # Inherit connection-level binary default; cursor kwarg overrides
        binary_val = kwargs.pop("binary", connection._binary)
        cursor_type_val = kwargs.pop("cursor_type", 0)
        
        # Set Python wrapper attributes
        if named_tuple_val:
            self._resulttype = RESULT_NAMEDTUPLE
        elif dictionary_val:
            self._resulttype = RESULT_DICTIONARY
        else:
            self._resulttype = RESULT_TUPLE
        self._prepared = prepared_val
        self._use_binary = binary_val
        self._cursor_type = cursor_type_val
        
        # Store the user's buffered preference
        self._user_buffered = buffered_val
        
        # Call initialization of C extension cursor
        # IMPORTANT: Always pass buffered=False to C cursor - we handle buffering in Python
        super().__init__(connection,
                        named_tuple=named_tuple_val,
                        dictionary=dictionary_val, 
                        buffered=False,  # Async always uses unbuffered C cursor
                        prepared=prepared_val,
                        binary=binary_val,
                        **kwargs)

    def check_closed(self):
        # Skip thread_id check if auto_reconnect is enabled, since the connection
        # may have reconnected and thread_id will be updated on next execute()
        if not self.connection.auto_reconnect:
            if self._thread_id != self.connection.thread_id:
                raise ProgrammingError(f"Cursor cannot be used anymore (the connection aborted and reconnected).")
        # Check both Python-level _closed and C cursor's closed attribute
        if self._closed or super(AsyncCursor, self).closed:
            raise ProgrammingError("Cursor cannot be used anymore (it was already closed before).")
        self._connection._check_closed()

    @property
    def rownumber(self):
        """Return the current row number (0-indexed position)"""
        # Return None if there's no result set
        if self.field_count == 0:
            return None
        
        # For buffered cursors, return current index
        if self._user_buffered and self._buffered_rows is not None:
            return self._row_index
        
        # For unbuffered cursors or before first fetch, return None
        if self._buffered_rows is None:
            return None
            
        # Otherwise return the current row index
        return self._row_index

    def _substitute_parameters(self):
        """
        Internal use only.

        When running in text protocol, this method will replace placeholders
        by supplied values.

        For values which aren't numbers, strings or bytes string representation
        will be used.
        """

        if not self._paramlist:
            return self.statement.encode("utf8")

        stmt = self.statement.encode("utf8")
        paramlist = self._paramlist
        n = len(paramlist)
        is_pyformat = self._paramstyle == PARAMSTYLE_PYFORMAT

        # Split statement into fragments between placeholders (O(n))
        # result = fragment[0] + converted[0] + fragment[1] + ... + fragment[n]
        result = [None] * (2 * n + 1)
        prev = 0
        for i in range(n):
            ofs = paramlist[i]
            result[2 * i] = stmt[prev:ofs]
            prev = ofs + 1

            if is_pyformat:
                val = self._data[self._keys[i]]
            else:
                val = self._data[i]

            vtype = type(val)
            if val is None:
                result[2 * i + 1] = b"NULL"
            elif vtype is INDICATOR.MrdbIndicator:
                if val == INDICATOR.NULL:
                    result[2 * i + 1] = b"NULL"
                elif val == INDICATOR.DEFAULT:
                    result[2 * i + 1] = b"DEFAULT"
                else:
                    result[2 * i + 1] = b"NULL"
            elif isinstance(val, _NUMERIC_TYPES):
                result[2 * i + 1] = val.__str__().encode("utf8")
            elif vtype is bytes or vtype is bytearray:
                result[2 * i + 1] = ("'%s'" % self.connection.escape_string(
                    val.decode(encoding='latin1'))).encode("utf8")
            else:
                result[2 * i + 1] = ("'%s'" % self.connection.escape_string(
                    val.__str__())).encode("utf8")

        result[2 * n] = stmt[prev:]
        return b"".join(result)

    def _check_decimal_parameter(self, val):
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


    async def callproc(self, sp: str, data: Sequence = ()):
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

        if self.connection.auto_reconnect:
            self._thread_id= self.connection.thread_id
        self.check_closed()
        self._reset()

        # CALL always uses binary protocol for OUT params
        params = ""
        if data and len(data):
            params = ("?," * len(data))[:-1]
        statement = "CALL %s(%s)" % (sp, params)
        self._rowcount = 0
        await self._execute(statement, data, use_binary=True)

    def nextset(self):
        """
        Will make the cursor skip to the next available result set,
        discarding any remaining rows from the current set.
        """

        self.check_closed()
        
        # Clear buffered rows from previous result set
        self._buffered_rows = None
        self._row_index = 0
        
        # Move to next result set
        result = super()._nextset()
        
        # If buffered mode and there's a new result set, we need to buffer it
        # However, nextset() is synchronous, so we can't await here
        # The buffering will need to happen on first fetch
        
        return result

    async def execute(self, statement: str, data: Sequence = (), buffered=None):
        """
        Prepare and execute a SQL statement asynchronously.

        Parameters may be provided as sequence or mapping and will be bound
        to variables in the operation. Variables are specified as question
        marks (paramstyle ='qmark'), however for compatibility reasons MariaDB
        Connector/Python also supports the 'format' and 'pyformat' paramstyles
        with the restriction, that different paramstyles can't be mixed within
        a statement.

        A reference to the operation will be retained by the cursor.
        If the cursor was created with attribute prepared=True the statement
        string for following execute operations will be ignored.
        This is most effective for algorithms where the same operation is used,
        but different parameters are bound to it (many times).
        """
        if self.connection.auto_reconnect:
            self._thread_id= self.connection.thread_id

        self.check_closed()
        if not self._prepared:
            self._reset()

        # Clear buffered rows from previous execute
        self._buffered_rows = None
        self._row_index = 0

        # Update Python-level buffering flag if specified
        if buffered is not None:
            self._user_buffered = buffered

        # Consume any remaining rows from other cursors to avoid "Commands out of sync"
        await self._consume_active_result()
        
        # Mark this cursor as the active one on the connection ONLY if unbuffered
        if not self._user_buffered:
            self.connection._active_async_cursor = self

        # Prepared cursor reuses previous statement
        if self._prepared and self.statement:
            statement = self.statement

        await self._execute(statement, data, use_binary=self._use_binary)

    async def _execute(self, statement: str, data: Sequence = (), use_binary=False):
        """
        Internal execute — shared by execute() and callproc().

        Args:
            statement: SQL statement
            data: parameters
            use_binary: force binary protocol (True for CALL, or from cursor setting)
        """
        self.connection._last_executed_statement = statement
        self._rowcount = 0
        self._description = None

        # CONPY-218: Allow None as replacement for empty tuple
        data = data or ()

        if data:
            self._data = data

            # Validate unsupported decimal/float values
            for val in (data.values() if isinstance(data, dict) else data):
                self._check_decimal_parameter(val)

            # Parameterized query — decide protocol
            # CALL statements always need binary protocol for OUT params
            if not use_binary and not isinstance(data, dict):
                first_word = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else ""
                if first_word == "CALL":
                    use_binary = True

            if not isinstance(data, dict) and (use_binary or self._check_text_types()):
                # Binary protocol: server parses placeholders during prepare
                if self.statement != statement:
                    super()._set_statement(statement, len(data))
                    self._reprepare = True
                else:
                    self._reprepare = False
                await self._execute_binary_async()
            else:
                # Text protocol: parse for paramstyle + substitute values
                if self.statement != statement:
                    super()._parse(statement, True)
                    self._reprepare = True
                else:
                    self._reprepare = False

                # Validate param style matches data type
                if isinstance(data, dict):
                    if self._paramstyle != PARAMSTYLE_PYFORMAT:
                        raise ProgrammingError("Data argument must be Tuple or List")
                    # Validate all referenced keys exist in dict
                    if self._keys:
                        for key in self._keys:
                            if key not in data:
                                raise ProgrammingError(
                                    "Dictionary doesn't contain key '%s'" % key)
                else:
                    if self._paramstyle == PARAMSTYLE_PYFORMAT:
                        raise ProgrammingError("Data argument must be Dictionary")
                    if self._paramlist and len(data) != len(self._paramlist):
                        raise ProgrammingError(
                            "statement (%s) doesn't match the number of data elements"
                            " (%s)." % (len(self._paramlist), len(data)))

                self._transformed_statement = self._substitute_parameters()
                await self._execute_text_async(self._transformed_statement)
        else:
            # No parameters — always text protocol
            if self.statement != statement:
                super()._set_statement(statement, 0)
                self._reprepare = True
            else:
                self._reprepare = False
            self._text = True
            await self._execute_text_async(statement)

        self._initresult()
        self._bulk = 0
        
        if self._user_buffered and self.field_count > 0:
            await self._buffer_all_rows()
    
    async def _buffer_all_rows(self):
        """Fetch all rows into memory for buffered cursor"""
        self._buffered_rows = []
        self._row_index = 0
        
        while True:
            row = await self._fetch_row()
            if row is None:
                break
            self._buffered_rows.append(row)
        
        # Set rowcount to the number of fetched rows
        self._rowcount = len(self._buffered_rows)
    
    async def _execute_text_async(self, statement: str):
        """Execute text query using async non-blocking API"""
        # Start non-blocking query execution
        wait_status = self.connection._async_real_query_start(statement)
        
        # Wait for query to complete
        while wait_status:
            actual_status = await self.connection._wait_for_status(wait_status)
            wait_status = self.connection._async_real_query_cont(actual_status)
        
        # Set field_count from connection so _initresult() can work properly
        self._set_field_count_from_connection()
        
        # Ensure parseinfo.is_text is set to 1 for text protocol
        # This is needed so Mrdb_GetFieldInfo() knows to call mysql_use_result()
        self._text = True

    async def _execute_binary_async(self):
        """Execute binary query using async prepared statement protocol
        
        LIMITATION: mysql_stmt_prepare() is synchronous (no async version in MariaDB C API).
        This means statement preparation will block the event loop briefly.
        
        However, statement execution and fetching are fully async, which is where
        most of the network I/O happens.
        """
        # Prepare statement (synchronous - blocks event loop, but typically fast)
        # This includes stmt init, parameter binding, and mysql_stmt_prepare()
        self._prepare_stmt_only()
        
        # Execute statement asynchronously (network I/O)
        wait_status = self._async_stmt_execute_start()
        
        while wait_status:
            actual_status = await self.connection._wait_for_status(wait_status)
            wait_status = self._async_stmt_execute_cont(actual_status)
        
        # Field count is already set by the C extension after stmt execution

    async def executemany(self, statement, parameters):
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

        if self.connection.auto_reconnect:
            self._thread_id= self.connection.thread_id

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
        
        # Check if all parameter sets are empty (no parameters)
        # If so, use non-bulk execution to avoid parameter binding errors
        has_parameters = any(len(row) > 0 if hasattr(row, '__len__') else True for row in parameters)

        if not (self.connection.extended_server_capabilities &
                (CAPABILITY.BULK_OPERATIONS >> 32)) or not has_parameters:
            count = 0
            accumulated_results = []
            
            for i, row in enumerate(parameters):
                await self.execute(statement, row)
                count += self.rowcount
                
                # If this statement has a RETURNING clause, accumulate buffered results
                # BEFORE the next execute() clears them
                if self.field_count > 0 and self._buffered_rows is not None:
                    accumulated_results.extend(self._buffered_rows)
            
            self._rowcount = count
            
            # If we accumulated results from RETURNING, restore them
            if accumulated_results:
                self._buffered_rows = accumulated_results
                self._row_index = 0
                self._user_buffered = True
            else:
                # No results accumulated - this is expected for non-RETURNING statements
                # but for RETURNING statements, this indicates an issue
                pass
        else:
            # Bulk execute: always binary, needs full parse for INSERT...VALUES detection
            if self.statement != statement or not self._bulk:
                super()._parse(statement, False)
                self._reprepare = True
            else:
                self._reprepare = False
            self._data = parameters
            self._text = False
            self._rowcount = 0
            self._execute_bulk()
            self._bulk = 1

    async def _consume_active_result(self):
        """
        Consume any remaining rows from the active cursor on this connection.
        
        This prevents "Commands out of sync" errors when executing a new query
        while there are still pending results. This handles both cases:
        - Another cursor has pending results on this connection
        - This same cursor is re-executing before finishing previous results
        """
        if self.connection._active_async_cursor is not None:
            active_cursor = self.connection._active_async_cursor
            try:
                if (not active_cursor._closed and 
                    active_cursor.field_count > 0):
                    # Drain all remaining rows asynchronously
                    try:
                        while True:
                            row = await active_cursor._fetch_row()
                            if row is None:
                                break
                    except:
                        pass
            except:
                pass
            # Clear using C extension's field (with proper reference counting)
            self.connection._active_async_cursor = None

    async def _fetch_row(self):
        """
        Internal use only

        fetches row and converts values, if connection has a converter.
        Uses cursor-level fetch_row_start/cont for text protocol (reuses field_fetch_fromtext).
        Uses stmt_fetch_start/cont for binary protocol (prepared statements).
        """
        if not self.buffered and not self.connection.auto_reconnect:
            self.check_closed()

        if not self.field_count:
            raise ProgrammingError("Cursor doesn't have a result set")
        
        if not self._text:
            result = self._async_stmt_fetch_start()
            
            while isinstance(result, int) and result != 0:
                actual_status = await self.connection._wait_for_status(result)
                result = self._async_stmt_fetch_cont(actual_status)
            
            if result is None and self.connection._active_async_cursor is self:
                self.connection._active_async_cursor = None
            return result
        else:
            result = self._async_fetch_row_start()
            
            while isinstance(result, int) and result != 0:
                actual_status = await self.connection._wait_for_status(result)
                result = self._async_fetch_row_cont(actual_status)
            
            if result is None and self.connection._active_async_cursor is self:
                self.connection._active_async_cursor = None
            return result

    async def close(self):
        """
        Closes the cursor.

        If the cursor has pending or unread results, .close() will cancel them
        so that further operations using the same connection can be executed.

        The cursor will be unusable from this point forward; an Error
        (or subclass) exception will be raised if any operation is attempted
        with the cursor."
        """

        # CONPY-231: fix memory leak
        if self._data:
            del self._data

        if not self.connection._closed:
            super().close()
            
        if self.connection._active_async_cursor is self:
            self.connection._active_async_cursor = None

        self._closed= True

    async def fetchone(self):
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
        
        row = await self._fetch_row()
        return row

    async def fetchmany(self, size: int = 0):
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
            row = await self._fetch_row()
            if row is None:
                break
            rows.append(row)
        
        # Update rowcount cumulatively for unbuffered cursors
        self._rowcount += len(rows)
        return rows

    async def fetchall(self):
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
            row = await self._fetch_row()
            if row is None:
                break
            rows.append(row)
        
        # Update rowcount for unbuffered cursors
        self._rowcount = len(rows)
        return rows

    def __aiter__(self):
        return self
    
    async def __anext__(self):
        row = await self.fetchone()
        if row is None:
            raise StopAsyncIteration
        return row

    async def scroll(self, value: int, mode="relative"):
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
        if new_pos < 0 or new_pos > len(self._buffered_rows):
            raise ProgrammingError("Position value is out of range.")

        self._row_index = new_pos

    def setinputsizes(self, size: int):
        """
        Required by PEP-249. Does nothing in MariaDB Connector/Python
        """

        return

    def setoutputsize(self, size: int):
        """
        Required by PEP-249. Does nothing in MariaDB Connector/Python
        """

        return

    async def __aenter__(self):
        """Returns a copy of the cursor."""

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Closes cursor."""
        await self.close()

    @property
    def rowcount(self):
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
        if hasattr(self, '_rowcount') and self._rowcount > 0:
            return self._rowcount
        return super().rowcount

    @property
    def sp_outparams(self):
        """
        Indicates if the current result set contains in out or out parameter
        from a previous executed stored procedure
        """
        self.check_closed()

        return bool(self.connection.server_status & STATUS.PS_OUT_PARAMS)

    @property
    def lastrowid(self):
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

        id = self.insert_id
        if id > 0:
            return id
        return None

    @property
    def connection(self):
        """
        Read-Only attribute which returns the reference to the connection
        object on which the cursor was created.
        """

        return self._connection
