# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Generic, Iterator, List, Sequence, Type

from .rows import RowT_co

if TYPE_CHECKING:
    from types import TracebackType


class SyncCursorCommon(ABC, Generic[RowT_co]):
    """Cursor interface, generic over the row type it produces (see rows.py)."""
    """
    Synchronous MariaDB Cursor Interface
    """

    @abstractmethod
    def close(self) -> None:
        """
        Close the cursor and free resources
        
        Consumes any remaining streaming results before closing.
        After closing, the cursor cannot be used anymore.
        """
        ...

    def __enter__(self) -> SyncCursorCommon[RowT_co]:
        return self

    def __exit__(
        self,
        exc_type: Type[BaseException] | None,
        exc_val: Any,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()
    
    # =========================================================================
    # Query Execution Methods
    # =========================================================================
        
    @abstractmethod
    def execute(self, sql: str, data: Sequence[Any] | dict[str, Any] | None = None, buffered: bool | None = None) -> None:
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
    def executemany(self, sql: str, data: Sequence[Sequence[Any] | dict[str, Any]], buffered: bool | None = None) -> None:
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
    def __iter__(self) -> Iterator[RowT_co]:
        """Iterate over the remaining rows of the current result set"""
        ...

    @abstractmethod
    def fetchone(self) -> RowT_co | None:
        """Fetch the next row of a query result set
        
        Returns:
            The next row of the result set, or None if no more rows are available.
        
        Raises:
            ProgrammingError: If cursor is closed or no result set is available.
        """
        ...

    @abstractmethod
    def fetchmany(self, size: int | None = None) -> List[RowT_co]:
        """Fetch the next set of rows of a query result"""
        ...
        
    @abstractmethod
    def fetchall(self) -> List[RowT_co]:
        """Fetch all remaining rows of a query result"""
        ...
    
    @abstractmethod
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
        ...

    # =========================================================================
    # Stored Procedures
    # =========================================================================
    @abstractmethod
    def callproc(self, procname: str, args: Sequence[Any] = ()) -> None:
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
    

    # ------------------------------------------------------------------------
    # Result set state: the DB-API attributes every implementation exposes
    # ------------------------------------------------------------------------
    arraysize: int
    """Number of rows fetchmany() returns when called without a size"""

    @property
    @abstractmethod
    def rowcount(self) -> int:
        """Number of rows the last statement produced or affected (-1 when unknown)"""
        ...

    @property
    @abstractmethod
    def description(self) -> tuple[Any, ...] | None:
        """DB-API description of the result set columns, None without a result set"""
        ...

    @property
    @abstractmethod
    def rownumber(self) -> int | None:
        """Zero-based index of the next row within the result set, None without a result set"""
        ...

    @property
    @abstractmethod
    def lastrowid(self) -> int | None:
        """AUTO_INCREMENT value generated by the last statement, None when there is none"""
        ...

    @property
    @abstractmethod
    def closed(self) -> bool:
        """Whether the cursor has been closed"""
        ...

    @property
    @abstractmethod
    def buffered(self) -> bool:
        """Whether result sets are fetched entirely on execute (buffered) or streamed"""
        ...

    @property
    @abstractmethod
    def metadata(self) -> Any | None:
        """Column metadata of the result set, None without a result set"""
        ...

    @property
    @abstractmethod
    def warnings(self) -> int:
        """Number of warnings generated by the last statement"""
        ...

    @property
    @abstractmethod
    def sp_outparams(self) -> bool:
        """Whether the current result set carries the OUT parameters of a stored procedure"""
        ...

    @property
    @abstractmethod
    def field_count(self) -> int:
        """Number of columns of the current result set"""
        ...

    @property
    @abstractmethod
    def affected_rows(self) -> int:
        """Number of rows affected by the last statement"""
        ...

    @abstractmethod
    def nextset(self) -> bool | None:
        """Move to the next result set; None when there is none left"""
        ...

    @abstractmethod
    def setinputsizes(self, sizes: Any, /) -> None:
        """DB-API no-op: parameter sizes are not needed"""
        ...
