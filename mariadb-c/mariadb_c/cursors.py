# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

import datetime
from numbers import Number

# Import shared constants and exceptions to avoid circular dependencies
from mariadb_shared.constants import CURSOR, STATUS, CAPABILITY, INDICATOR
from mariadb_shared.exceptions import (
    ProgrammingError,
    NotSupportedError
)
from typing import Sequence
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


# Import the C cursor base class
from mariadb_c._mariadb import cursor as CCursor
class Cursor(CCursor):
    """
    MariaDB Connector/Python Cursor Object
    """
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
        self.buffered = True
        self._parseinfo = None
        self._data = None
        self._thread_id = connection.thread_id
        self._closed= None

        if not connection:
            raise ProgrammingError("Invalid or no connection provided")

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
        self.buffered = buffered_val
        self._prepared = prepared_val
        self._use_binary = binary_val
        self._cursor_type = cursor_type_val

        super().__init__(connection,
                        named_tuple=named_tuple_val,
                        dictionary=dictionary_val, 
                        buffered=buffered_val,
                        prepared=prepared_val,
                        binary=binary_val,
                        **kwargs)

    def check_closed(self):
        if self._thread_id != self.connection.thread_id:
            raise ProgrammingError(f"Cursor cannot be used anymore (the connection aborted and reconnected).")
        if self._closed:
            raise ProgrammingError("Cursor cannot be used anymore (it was already closed before).")
        self._connection._check_closed()

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


    def callproc(self, sp: str, data: Sequence = ()):
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
        self._execute(statement, data, use_binary=True)

    def nextset(self):
        """
        Will make the cursor skip to the next available result set,
        discarding any remaining rows from the current set.
        """

        self.check_closed()
        return super()._nextset()

    def execute(self, statement: str, data: Sequence = (), buffered=None):
        """
        Prepare and execute a SQL statement.

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
            self._thread_id = self.connection.thread_id

        self.check_closed()
        if not self._prepared:
            self._reset()

        if buffered is not None:
            self.buffered = buffered

        # clear pending result sets
        if self.field_count:
            self._clear_result()

        # Prepared cursor reuses previous statement
        if self._prepared and self.statement:
            statement = self.statement

        self._execute(statement, data, use_binary=self._use_binary)

    def _execute(self, statement: str, data: Sequence = (), use_binary=False):
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
                self._execute_binary()
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
                self._sync_execute_text(self._transformed_statement)
                self._sync_readresponse()
        else:
            # No parameters — always text protocol
            if self.statement != statement:
                super()._set_statement(statement, 0)
                self._reprepare = True
            else:
                self._reprepare = False
            self._text = True
            self._sync_execute_text(statement)
            self._sync_readresponse()

        self._initresult()
        self._bulk = 0

    def executemany(self, statement, parameters):
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

        if not (self.connection.extended_server_capabilities &
                (CAPABILITY.BULK_OPERATIONS >> 32)):
            count = 0
            for row in parameters:
                self.execute(statement, row)
                count += self.rowcount
            self._rowcount = count
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

    def close(self):
        """
        Closes the cursor.

        If the cursor has pending or unread results, .close() will cancel them
        so that further operations using the same connection can be executed.

        After calling .close() the cursor object becomes unusable. Any operation
        with the cursor will raise a ProgrammingError exception.
        """
        if self._closed:
            return

        # CONPY-231: fix memory leak
        if self._data:
            del self._data
        super().close()

        self._closed= True

    def fetchone(self):
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

    def fetchmany(self, size: int = 0):
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

        return super().fetchrows(size)

    def fetchall(self):
        """
        Fetch all remaining rows of a query result, returning them as a
        sequence of sequences (e.g. a list of tuples).

        An exception will be raised if the previous call to execute() didn't
        produce a result set or execute() wasn't called before.
        """

        if not (self.buffered and self._text):
            self.check_closed()
        return super().fetchrows(ROWS_EOF)

    def __iter__(self):
        return iter(self.fetchone, None)

    def scroll(self, value: int, mode="relative"):
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
            if self.rownumber + value < 0 or \
               self.rownumber + value > self.rowcount:
                raise ProgrammingError("Position value "
                                               "is out of range.")
            new_pos = self.rownumber + value
        else:
            if value < 0 or value >= self.rowcount:
                raise ProgrammingError("Position value "
                                               "is out of range.")
            new_pos = value

        self._seek(new_pos)
        self._rownumber = new_pos

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

    def __enter__(self):
        """Returns a copy of the cursor."""

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Closes cursor."""
        self.close()

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
        if not self.buffered:
            try:
                self.check_closed()
            except ProgrammingError:
                return -1

        if self._rowcount > 0:
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
