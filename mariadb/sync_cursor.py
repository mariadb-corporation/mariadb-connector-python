#
# Copyright (C) 2020-2021 Georg Richter and MariaDB Corporation AB

# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Library General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.

# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Library General Public License for more details.

# You should have received a copy of the GNU Library General Public
# License along with this library; if not see <http://www.gnu.org/licenses>
# or write to the Free Software Foundation, Inc.,
# 51 Franklin St., Fifth Floor, Boston, MA 02110, USA
#

import datetime
import decimal
from numbers import Number
from collections import namedtuple
from typing import Sequence, Optional, List, Any, Union, TYPE_CHECKING

from .impl.message.server.prepare_stmt_packet import PrepareStmtPacket
from .impl.client.sync_client import SyncClient

from .base_cursor import BaseCursor, ROWS_ALL, RESULT_TUPLE, RESULT_NAMEDTUPLE, RESULT_DICTIONARY
from .exceptions import DatabaseError, ProgrammingError, NotSupportedError, OperationalError
from .impl.message.client.query_packet import QueryPacket
from mariadb_shared.constants.STATUS import NO_BACKSLASH_ESCAPES
from mariadb_shared.constants.FIELD_TYPE import (
    INT24, TIMESTAMP, YEAR, NEWDECIMAL, DECIMAL, JSON
)
from mariadb_shared.constants.FIELD_FLAG import NUMERIC as NUM_FLAG

if TYPE_CHECKING:
    from .base_connection import BaseConnection

class SyncCursor(BaseCursor):
    """
    Synchronous MariaDB Cursor Object
    """

    def __init__(self, connection: 'BaseConnection', **kwargs):
        """
        Initialize synchronous cursor with a connection
        
        Args:
            connection: Database connection
            **kwargs: Cursor options (buffered, named_tuple, dictionary, etc.)
        """
        super().__init__(connection, **kwargs)

    def close(self) -> None:
        """Close the cursor asynchronously"""
        if not self._closed:
            # Consume any remaining streaming results
            if self._result is not None and self._result.streaming():
                try:
                    self._result.fetch_remaining()
                except Exception:
                    pass  # Ignore errors during close
            
            self._closed = True
            self.arraysize = 1
            self._rowcount = -1
            self._affected_rows = -1
            self.description = None
            self.lastrowid = None
            self._completions = []
            self._completion_index = 0
            self._cursor_config = None
            self._result = None 
        
    def execute(self, sql: str, data: Optional[Union[Sequence[Any], dict]] = None, buffered: Optional[bool] = None) -> None:
        """
        Execute a database query or command
        
        Args:
            sql: SQL statement to execute
            data: Optional parameters for the statement
            buffered: Override cursor's buffered setting for this execution
        """
        self._check_closed()
        
        # Consume any pending streaming results before executing new query
        if self._result is not None and self._result.streaming():
            self._result.fetch_remaining()
        
        if (not sql):
            self._process_completions(None)
            return
        try:
            
            # Convert data to list format for parameter binding
            parameters = None
            if data:
                if isinstance(data, (list, tuple)):
                    parameters = list(data)
                elif isinstance(data, dict):
                    # For named parameters, we'd need to convert SQL from :name to ? format
                    # For now, raise an error to indicate this needs implementation
                    raise NotSupportedError("Named parameters not yet implemented with enhanced parameter binding")
            
            # Create query packet with direct parameter binding (no string substitution!)
            query_packet = QueryPacket(sql, parameters)
            # Use provided buffered parameter or fall back to cursor default
            effective_buffered = buffered if buffered is not None else self._buffered
            completions = self._client.execute(query_packet, self._get_config(), False, effective_buffered)
            
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
        
        if not data:
            return
        
        # Reset result state
        self.description = None
        self._result = None
        total_affected = 0
        lastrowid = None
        
        try:
            completions = list()
            # Execute the statement for each parameter set
            for params in data:
                # Execute with current parameter set
                # Convert data to list format for parameter binding
                parameters = None
                if params:
                    if isinstance(params, (list, tuple)):
                        parameters = list(params)
                    elif isinstance(params, dict):
                        raise NotSupportedError("Named parameters not yet implemented")
                
                # Create query packet and execute
                query_packet = QueryPacket(sql, parameters)
                # Use provided buffered parameter or fall back to cursor default
                effective_buffered = buffered if buffered is not None else self._buffered
                compl_list = self._client.execute(query_packet, self._get_config(), False, effective_buffered)
                completions.extend(compl_list)
                for c in compl_list:
                    if c.affected_rows >= 0:
                        total_affected += c.affected_rows
                    if c.insert_id is not None and c.insert_id > 0:
                        lastrowid = c.insert_id

            # Process the completions - aggregate result sets with compatible metadata
            self._process_executemany_completions(completions)
            
            # Accumulate affected rows from all completions

            # Set final rowcount to total affected rows
            self._affected_rows = total_affected
            self._rowcount = total_affected
            self.lastrowid = lastrowid is not None and lastrowid > 0 and lastrowid or None

        except DatabaseError as e:
            raise e            
        except Exception as e:
            raise self._exception_factory.create_exception(
                f"ExecuteMany failed: {e}",
                errno=2013,
                sql_state='HY000'
            )
        
    def fetchone(self) -> Optional[Any]:
        """Fetch the next row of a query result set"""
        # Allow fetching from buffered results even if connection is closed
        if self._closed:
            raise ProgrammingError("Cursor is closed")
        if self.connection._closed and (self._result is None or self._result.streaming()):
            raise ProgrammingError("Cursor is closed")
        
        # DB-API 2.0: Raise error if no result set (description is None)
        if self.description is None:
            raise ProgrammingError("No result set to fetch from")
        
        # Delegate to Result object
        if self._result is not None:
            row = self._result.fetch_one()
            self._rowcount = self._result.get_row_count()
            if row is not None:
                # Apply row formatting
                row = self._apply_row_formatting([row])[0]
            return row
        
        return None

    def _seek(self, offset: int) -> None:
        """Move the cursor to the specified row"""
        # Allow seeking in buffered results even if connection is closed
        if self._closed:
            raise ProgrammingError("Cursor is closed")
        if self.connection._closed and (self._result is None or self._result.streaming()):
            raise ProgrammingError("Cursor is closed")
        
        if self._result is None:
            raise ValueError("No result set")
        if self._result.streaming():
            raise ValueError("Seek not supported for unbuffered cursors")
        # For CompleteResult, use scroll with absolute mode
        self._result.scroll(offset, mode='absolute')
        
    def fetchmany(self, size: Optional[int] = None) -> List[Any]:
        """Fetch the next set of rows of a query result"""
        # Allow fetching from buffered results even if connection is closed
        if self._closed:
            raise ProgrammingError("Cursor is closed")
        if self.connection._closed and (self._result is None or self._result.streaming()):
            raise ProgrammingError("Cursor is closed")
        
        # DB-API 2.0: Raise error if no result set (description is None)
        if self.description is None:
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
        
        # DB-API 2.0: Raise error if no result set (description is None)
        if self.description is None:
            raise ProgrammingError("No result set to fetch from")
        
        # Delegate to Result object
        if self._result is not None:
            rows = self._result.fetch_all()
            self._rowcount = self._result.get_row_count()
            return self._apply_row_formatting(rows)
        
        return []
        
    def nextset(self) -> Optional[bool]:
        """Skip to the next available result set"""
        self._check_closed()
        
        # Move to next completion
        self._completion_index += 1
        
        # Check if there are more completions
        if self._completion_index >= len(self._completions):
            return None
        
        # Process the next completion
        self._process_current_completion()
        return True

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
        
        if self._result.streaming():
            raise ProgrammingError("Scroll not supported for unbuffered cursors")
        
        # Validate mode
        if mode not in ("absolute", "relative"):
            raise ProgrammingError("Invalid or unknown scroll mode specified.")
        
        # Delegate to Result object's scroll method
        try:
            self._result.scroll(value, mode)
        except ValueError as e:
            raise ProgrammingError(str(e))
        
    # Sync iterator
    def __iter__(self) -> 'SyncCursor':
        """Return iterator for cursor"""
        return self
        
    def __next__(self) -> Any:
        """Return next row"""
        row = self.fetchone()
        if row is None:
            raise StopIteration
        return row
    
    def callproc(self, procname: str, args: Sequence[Any] = ()) -> Sequence[Any]:
        """
        Call a stored procedure with the given name and arguments
        
        Args:
            procname: Name of the stored procedure
            args: Sequence of arguments for the procedure
            
        Returns:
            Sequence of arguments (modified for output parameters)
        """
        self._check_closed()
        
        try:
            # Build CALL statement with placeholders
            placeholders = ', '.join(['?' for _ in args])
            call_sql = f"CALL {procname}({placeholders})"
            
            # Prepare the statement
            stmt: PrepareStmtPacket = self._client.prepare_statement(call_sql)
            
            try:
                # Execute with parameters using ExecutePacket
                from .impl.message.client.execute_packet import ExecutePacket
                execute_packet = ExecutePacket(stmt.statement_id, list(args), call_sql)
                completions = self._client.execute(execute_packet, self._get_config(), can_redo=False)
                
                # Process all completions
                self._process_callproc_completions(completions)
                
                return None  # Match C extension behavior
                
            finally:
                # Always close the prepared statement
                self._client.close_prepared_statement(stmt)
        except DatabaseError as e:
            raise e                            
        except Exception as e:
            raise self._exception_factory.create_exception(
                f"CallProc failed: {e}",
                errno=2013,
                sql_state='HY000'
            )
    
    def nextset(self) -> Optional[bool]:
        """
        Move to the next result set
        
        Returns:
            True if there are more result sets, False if no more, None if not supported
        """
        self._check_closed()
        
        if not hasattr(self, '_completions') or not self._completions:
            return None
        
        # Move to next completion
        self._completion_index += 1
        
        if self._completion_index >= len(self._completions):
            return False
        
        # Process the next completion
        self._process_current_completion()
        return True
    
    # Sync context manager
    def __enter__(self) -> 'SyncCursor':
        """Context manager entry"""
        return self
        
    def __exit__(self, exc_type: Optional[type], exc_val: Optional[Exception], exc_tb: Optional[Any]) -> bool:
        """Context manager exit"""
        self.close()
        return False
