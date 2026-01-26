# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, List, Optional, Sequence, Union


class AsyncCursorCommon(ABC):
    """
    Synchronous MariaDB Cursor Interface
    """

    @abstractmethod
    async def close(self) -> None:
        """
        Close the cursor and free resources
        
        Consumes any remaining streaming results before closing.
        After closing, the cursor cannot be used anymore.
        """
        ...
    
    # =========================================================================
    # Query Execution Methods
    # =========================================================================
        
    @abstractmethod
    async def execute(self, sql: str, data: Optional[Union[Sequence[Any], dict]] = None, buffered: Optional[bool] = None) -> None:
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
        ...

    @abstractmethod
    async def executemany(self, sql: str, data: Sequence[Union[Sequence[Any], dict]], buffered: Optional[bool] = None) -> None:
        """
        Execute a statement multiple times with different parameter sets
        
        Args:
            sql: SQL statement to execute
            data: Sequence of parameter sequences
            buffered: Override cursor's buffered setting for this execution
        """
        ...
        
    # =========================================================================
    # Result Fetching Methods
    # =========================================================================
    @abstractmethod    
    async def fetchone(self) -> Optional[Any]:
        """Fetch the next row of a query result set
        
        Returns:
            The next row of the result set, or None if no more rows are available.
        
        Raises:
            ProgrammingError: If cursor is closed or no result set is available.
        """
        ...

    @abstractmethod
    async def fetchmany(self, size: Optional[int] = None) -> List[Any]:
        """Fetch the next set of rows of a query result"""
        ...
        
    @abstractmethod
    async def fetchall(self) -> List[Any]:
        """Fetch all remaining rows of a query result"""
        ...
    
    @abstractmethod
    async def scroll(self, value: int, mode: str = "relative") -> None:
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
        ...

    # =========================================================================
    # Stored Procedures
    # =========================================================================
    @abstractmethod
    async def callproc(self, procname: str, args: Sequence[Any] = ()) -> None:
        """
        Call a stored procedure
        
        Executes a stored procedure and processes all result sets.
        
        Args:
            procname: Name of the stored procedure to call
            args: Sequence of arguments to pass to the procedure
            
        Returns:
            None
            
        Raises:
            ProgrammingError: If cursor is closed
            DatabaseError: If procedure execution fails
            
        Example:
            >>> cursor.callproc('get_user', (1,))
            >>> result = cursor.fetchone()
        """
        ...
    
    # =========================================================================
    # Iterator Protocol
    # =========================================================================
    
    def __aiter__(self) -> AsyncCursorCommon:
        """
        Return the cursor itself for async iteration
        
        Allows using the cursor in async for loops:
            async for row in cursor:
                process(row)
        """
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
        
    def __next__(self):
        """
        Sync iteration not supported for async cursor
        
        Raises:
            TypeError: Always (use 'async for' instead)
        """
        raise TypeError("Use 'async for' with asynchronous ursor")

    def __iter__(self):
        """
        Sync iteration not supported for async cursor
        
        Raises:
            TypeError: Always (use 'async for' instead)
        """
        raise TypeError("Use 'async for' with asynchronous Cursor")

    # =========================================================================
    # Context Manager
    # =========================================================================

    
    async def __aenter__(self) -> AsyncCursorCommon:
        """Async context manager entry"""
        return self
        
    async def __aexit__(self, exc_type: Optional[type], exc_val: Optional[Exception], exc_tb: Optional[Any]) -> bool:
        """Async context manager exit"""
        await self.close()
        return False
    
    # Sync context manager methods raise error
    def __enter__(self):
        """Sync context manager not supported for async cursor"""
        raise TypeError("Use 'async with' with asynchronous Cursor")
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Sync context manager not supported for async cursor"""
        raise TypeError("Use 'async with' with asynchronous Cursor")
            