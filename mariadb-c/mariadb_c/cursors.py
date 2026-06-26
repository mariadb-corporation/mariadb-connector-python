# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from __future__ import annotations

from types import TracebackType
from typing import Any, List, Iterator, Type

# Import shared constants and exceptions to avoid circular dependencies
from mariadb_shared.constants import STATUS, CAPABILITY
from mariadb_shared.constants.STATUS import NO_BACKSLASH_ESCAPES as _NO_BACKSLASH_ESCAPES
from mariadb_shared.exceptions import (
    ProgrammingError,
    NotSupportedError
)
from mariadb_shared.text_protocol import substitute_params, normalize_to_qmark
from typing import Sequence
import decimal

_Decimal = decimal.Decimal

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


# Import the C cursor base class
from mariadb_c._mariadb import cursor as CCursor
from .stmt_reuse_mixin import StmtReuseMixin


class Cursor(StmtReuseMixin, CCursor):
    """
    MariaDB Connector/Python Cursor Object
    """
    def __init__(self, connection: Any, **kwargs: Any) -> None:
        """
        initialization
        """
        if not connection:
            raise ProgrammingError("Invalid or no connection provided")

        self._bulk: int = False
        self._connection = connection
        self._description: Any = None
        self._cache_entry: Any = None
        self._rowcount = 0
        self._data: Any = None
        self._closed: bool | None = None
        self._local_stmt_cache: Any = None
        self._resolved_stmt_cache: Any = None  # memoised _resolve_stmt_cache() result

        if kwargs:
            named_tuple_val = kwargs.pop("named_tuple", False)
            dictionary_val = kwargs.pop("dictionary", False)
            buffered_val = kwargs.pop("buffered", True)
            binary_val = kwargs.pop("binary", connection._binary)
            cursor_type_val = kwargs.pop("cursor_type", 0)
            if named_tuple_val:
                self._resulttype = RESULT_NAMEDTUPLE
            elif dictionary_val:
                self._resulttype = RESULT_DICTIONARY
            else:
                self._resulttype = RESULT_TUPLE
        else:
            named_tuple_val = False
            dictionary_val = False
            buffered_val = True
            binary_val = connection._binary
            cursor_type_val = 0
            self._resulttype = RESULT_TUPLE

        self.buffered = buffered_val
        self._use_binary = binary_val
        self._cursor_type = cursor_type_val

        super().__init__(connection,
                        named_tuple=named_tuple_val,
                        dictionary=dictionary_val,
                        buffered=buffered_val,
                        binary=binary_val,
                        **kwargs)

    def check_closed(self) -> None:
        if self._closed:
            raise ProgrammingError("Cursor cannot be used anymore (it was already closed before).")
        self._connection._check_closed()


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


    def callproc(self, sp: str, data: Sequence = ()) -> None:
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
        self.execute("CALL %s(%s)" % (sp, params), data, _force_binary=True)

    def nextset(self) -> bool | None:
        """
        Will make the cursor skip to the next available result set,
        discarding any remaining rows from the current set.
        """

        self.check_closed()
        return super()._nextset()

    def execute(self, statement: str, data: Sequence = (), buffered: bool | None = None, _force_binary: bool = False) -> None:
        """
        Prepare and execute a SQL statement.

        Parameters may be provided as sequence or mapping and will be bound
        to variables in the operation. Variables are specified as question
        marks (paramstyle ='qmark'), however for compatibility reasons MariaDB
        Connector/Python also supports the 'format' and 'pyformat' paramstyles
        with the restriction, that different paramstyles can't be mixed within
        a statement.

        A reference to the operation will be retained by the cursor.
        """
        if self._closed:
            raise ProgrammingError("Cursor cannot be used anymore (it was already closed before).")
        self._connection._check_closed()

        if buffered is not None:
            self.buffered = buffered

        if not self._text:
            self._save_stmt_to_cache(self.statement)
        self._reset()

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
                self._execute_binary()
            else:
                # Text protocol: shared parser handles placeholder discovery,
                # validation, and value conversion in a single pass.
                no_backslash = bool(self.connection.server_status & _NO_BACKSLASH_ESCAPES)
                self._transformed_statement = b"".join(substitute_params(statement, self._data, no_backslash))
                self._sync_execute_text(self._transformed_statement, statement)
                self._sync_readresponse()
        else:
            # No parameters — always text protocol
            self._sync_execute_text(statement)
            self._sync_readresponse()

        self._initresult()
        self._bulk = 0

    def executemany(self, statement: str, parameters: Sequence[Sequence[Any] | dict[str, Any]]) -> None:
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

        # Check if parameters is None or not an array-like type
        if parameters is None or not hasattr(parameters, '__iter__') or isinstance(parameters, (str, bytes)):
            raise ProgrammingError("No data provided")

        self.connection._last_executed_statement = statement

        # clear pending results
        if self.field_count:
            self._clear_result()

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
            # Named/pyformat parameters — reorder each row dict into a list
            reordered: list = []
            for row in parameters:
                if not isinstance(row, dict):
                    raise ProgrammingError("Named placeholders require dict parameters")
                reordered.append([row.get(name) for name in param_names])
            parameters = reordered

        first_row = parameters[0] if hasattr(parameters, '__getitem__') else next(iter(parameters))

        if not (self.connection.extended_server_capabilities &
                (CAPABILITY.BULK_OPERATIONS >> 32)) or isinstance(first_row, dict):
            # PYFORMAT/FORMAT or server without bulk support: row-by-row loop
            count = 0
            for row in parameters:
                self.execute(normalized_sql, row)
                count += self.rowcount
            self._rowcount = count
        else:
            # Bulk execute: QMARK rows only.
            # paramcount from first row — no SQL parse needed.
            if self.statement != normalized_sql or not self._bulk:
                super()._set_statement(normalized_sql, len(first_row))
                self._reprepare = True
            else:
                self._reprepare = False
            self._data = parameters
            self._text = False
            self._rowcount = 0
            self._execute_bulk()
            self._bulk = 1


    def close(self) -> None:
        """
        Closes the cursor.

        If the cursor has pending or unread results, .close() will cancel them
        so that further operations using the same connection can be executed.

        After calling .close() the cursor object becomes unusable. Any operation
        with the cursor will raise a ProgrammingError exception.
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
        super().close()

        self._closed = True

    def fetchone(self) -> Any | None:
        """
        Fetch the next row of a query result set, returning a single sequence,
        or None if no more data is available.

        An exception will be raised if the previous call to execute() didn't
        produce a result set or execute() wasn't called before.
        """
        if not self.buffered:
            self.check_closed()
        elif self._closed:
            raise ProgrammingError("Cursor cannot be used anymore (it was already closed before).")

        # if there is no result set, PEP-249 requires to raise an exception
        if not self.field_count:
            raise ProgrammingError("Cursor doesn't have a result set")
        
        return super().fetchone()

    def fetchmany(self, size: int = 0) -> List[Any]:
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

        if size == 0:
            size = self.arraysize

        rows: List[Any] = super().fetchrows(size)
        return rows

    def fetchall(self) -> List[Any]:
        """
        Fetch all remaining rows of a query result, returning them as a
        sequence of sequences (e.g. a list of tuples).

        An exception will be raised if the previous call to execute() didn't
        produce a result set or execute() wasn't called before.
        """

        if not (self.buffered and self._text):
            self.check_closed()
        rows: List[Any] = super().fetchrows(ROWS_EOF)
        return rows

    def __iter__(self) -> Iterator[Any]:
        return iter(self.fetchone, None)

    def scroll(self, value: int, mode: str = "relative") -> None:
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

        if not self.buffered:
            raise ProgrammingError("This method is available only "
                                           "for cursors with a buffered "
                                           "result set.")

        if mode != "absolute" and mode != "relative":
            raise ProgrammingError("Invalid or unknown scroll "
                                           "mode specified.")

        if value == 0 and mode == "relative":
            return

        if mode == "relative":
            rownumber = self.rownumber
            assert rownumber is not None  # field_count != 0 guarantees a result set
            if rownumber + value < 0 or \
               rownumber + value > self.rowcount:
                raise ProgrammingError("Position value "
                                               "is out of range.")
            new_pos = rownumber + value
        else:
            if value < 0 or value >= self.rowcount:
                raise ProgrammingError("Position value "
                                               "is out of range.")
            new_pos = value

        self._seek(new_pos)
        self._rownumber = new_pos

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

    def __enter__(self) -> "Cursor":
        """Returns a copy of the cursor."""

        return self

    def __exit__(
        self,
        exc_type: Type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Closes cursor."""
        self.close()

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
        if not self.buffered:
            try:
                self.check_closed()
            except ProgrammingError:
                return -1

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
    def lastrowid(self) -> int | None:
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

        id: int | None = self.insert_id
        if id is not None and id > 0:
            return id
        return None

    @property
    def connection(self) -> Any:
        """
        Read-Only attribute which returns the reference to the connection
        object on which the cursor was created.
        """

        return self._connection
