# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from __future__ import annotations

import array
import datetime
import decimal
import math
import struct
from itertools import chain, repeat
from typing import Any, Callable, Iterable, List, Sequence

# Pre-compiled struct formats for performance
_STRUCT_I = struct.Struct('<I')  # unsigned int (4 bytes)
_STRUCT_b = struct.Struct('<b')  # signed byte
_STRUCT_h = struct.Struct('<h')  # signed short
_STRUCT_i = struct.Struct('<i')  # signed int
_STRUCT_q = struct.Struct('<q')  # signed long long
_STRUCT_Q = struct.Struct('<Q')  # unsigned long long for bigint > 2**63-1
_STRUCT_d = struct.Struct('<d')  # double
_STRUCT_BB = struct.Struct('<BB')  # two unsigned bytes

_INT64_MAX = 0x7FFFFFFFFFFFFFFF
_UNSIGNED_FLAG = 0x80

# Composite struct formats for datetime/date/time
_STRUCT_DATETIME_WITH_MICRO = struct.Struct('<BHBBBBBI')  # length(B) + year(H) + month(B) + day(B) + hour(B) + minute(B) + second(B) + microsecond(I)
_STRUCT_DATETIME_NO_MICRO = struct.Struct('<BHBBBBB')     # length(B) + year(H) + month(B) + day(B) + hour(B) + minute(B) + second(B)

_STRUCT_DATE = struct.Struct('<BHBB')                     # length(B) + year(H) + month(B) + day(B)
_STRUCT_TIME_WITH_MICRO = struct.Struct('<BBIBBBI')       # length(B) + negative(B) + days(I) + hour(B) + minute(B) + second(B) + microsecond(I)
_STRUCT_TIME_NO_MICRO = struct.Struct('<BBIBBB')          # length(B) + negative(B) + days(I) + hour(B) + minute(B) + second(B)

# Column-wise encoders: the same formats with the leading NONE indicator byte
# (0, "value follows") folded into the pack call, so a whole column is packed
# by one C-level map() instead of two Python calls per value.
_PACK_IND_b = struct.Struct('<Bb').pack
_PACK_IND_h = struct.Struct('<Bh').pack
_PACK_IND_i = struct.Struct('<Bi').pack
_PACK_IND_q = struct.Struct('<Bq').pack
_PACK_IND_Q = struct.Struct('<BQ').pack
_PACK_IND_d = struct.Struct('<Bd').pack
_PACK_IND_DATETIME_WITH_MICRO = struct.Struct('<BBHBBBBBI').pack
_PACK_IND_DATETIME_NO_MICRO = struct.Struct('<BBHBBBBB').pack
_PACK_IND_DATE = struct.Struct('<BBHBB').pack
_PACK_IND_TIME_WITH_MICRO = struct.Struct('<BBBIBBBI').pack
_PACK_IND_TIME_NO_MICRO = struct.Struct('<BBBIBBB').pack

_NULL_INDICATOR = b'\x01'
_TINY_TRUE = b'\x00\x01'
_TINY_FALSE = b'\x00\x00'
# NONE indicator + one-byte length prefix, for every length below 251.
_SHORT_LENENC: List[bytes] = [bytes((0, n)) for n in range(251)]
_NONE_TYPE = type(None)
_DECIMAL_SPECIALS = frozenset(("NaN", "sNaN", "Infinity", "-Infinity"))
# Rows encoded per column-wise batch; bounds the number of live bytes objects.
_ENCODE_CHUNK_ROWS = 8192

# numpy is an optional accelerator for float32 VECTOR encoding.
numpy: Any = None
try:
    import numpy  # pyright: ignore[reportMissingImports]
except ImportError:
    pass
HAS_NUMPY = numpy is not None

from ...client.context import Context
from mariadb_shared.constants import FIELD_TYPE
from mariadb_shared.constants.INDICATOR import MrdbIndicator
from mariadb_shared.text_protocol import split_timedelta
from ..client_message import ClientMessage
from ..payload_writer import PayloadWriter
from ....exceptions import NotSupportedError

# Integer type hierarchy: TINY < SHORT < LONG < LONGLONG
_INT_TYPE_ORDER = (FIELD_TYPE.TINY, FIELD_TYPE.SHORT, FIELD_TYPE.LONG, FIELD_TYPE.LONGLONG)

# Exact Python type -> field type, for columns whose non-NULL values all share
# one type. Mirrors _get_parameter_type; int is resolved separately from the
# column's value range and anything else goes through the per-value scan.
_EXACT_TYPE_FIELD: dict[type, int] = {
    bool: FIELD_TYPE.TINY,
    float: FIELD_TYPE.DOUBLE,
    decimal.Decimal: FIELD_TYPE.NEWDECIMAL,
    str: FIELD_TYPE.VAR_STRING,
    bytes: FIELD_TYPE.BLOB,
    bytearray: FIELD_TYPE.BLOB,
    datetime.datetime: FIELD_TYPE.DATETIME,
    datetime.date: FIELD_TYPE.DATE,
    datetime.time: FIELD_TYPE.TIME,
    datetime.timedelta: FIELD_TYPE.TIME,
}


def _int_rank(value: int) -> int:
    """Index into _INT_TYPE_ORDER of the smallest integer type holding *value*."""
    if -128 <= value <= 127:
        return 0
    if -32768 <= value <= 32767:
        return 1
    if -2147483648 <= value <= 2147483647:
        return 2
    return 3


def _lenenc_prefix(length: int) -> bytes:
    """NONE indicator followed by the length-encoded *length*."""
    if length < 251:
        return _SHORT_LENENC[length]
    if length < 65536:
        return b'\x00\xfc' + length.to_bytes(2, 'little')
    if length < 16777216:
        return b'\x00\xfd' + length.to_bytes(3, 'little')
    return b'\x00\xfe' + length.to_bytes(8, 'little')


def _encode_lenenc(chunks: Sequence[bytes | bytearray]) -> List[bytes]:
    """Length-encode every chunk, indicator byte included."""
    if not chunks:
        return []
    if max(map(len, chunks)) < 251:
        return [_SHORT_LENENC[len(c)] + c for c in chunks]
    return [_lenenc_prefix(len(c)) + c for c in chunks]


def _encode_datetime(value: datetime.datetime) -> bytes:
    if value.microsecond:
        return _PACK_IND_DATETIME_WITH_MICRO(
            0, 11, value.year, value.month, value.day,
            value.hour, value.minute, value.second, value.microsecond)
    return _PACK_IND_DATETIME_NO_MICRO(
        0, 7, value.year, value.month, value.day,
        value.hour, value.minute, value.second)


def _encode_date(value: datetime.date) -> bytes:
    return _PACK_IND_DATE(0, 4, value.year, value.month, value.day)


def _encode_time(value: datetime.time) -> bytes:
    if value.microsecond:
        return _PACK_IND_TIME_WITH_MICRO(
            0, 12, 0, 0, value.hour, value.minute, value.second, value.microsecond)
    return _PACK_IND_TIME_NO_MICRO(0, 8, 0, 0, value.hour, value.minute, value.second)


def _encode_timedelta(value: datetime.timedelta) -> bytes:
    negative, days, hours, minutes, seconds, microseconds = split_timedelta(value)
    if microseconds:
        return _PACK_IND_TIME_WITH_MICRO(
            0, 12, 1 if negative else 0, days, hours, minutes, seconds, microseconds)
    return _PACK_IND_TIME_NO_MICRO(0, 8, 1 if negative else 0, days, hours, minutes, seconds)


class BulkExecutePacket(ClientMessage):
    """
    Bulk Execute packet for prepared statement bulk execution (COM_STMT_BULK_EXECUTE)
    
    Allows sending multiple parameter sets in a single packet for efficient batch execution.
    See: https://mariadb.com/kb/en/com_stmt_bulk_execute/

    Rectangular parameter sets (every row has the same length) are analysed
    and encoded column by column, which keeps the per-value work inside C-level
    builtins (set/map/min/max, Struct.pack, bytes.join). A column whose values
    the column encoders cannot handle -- mixed Python types, indicator objects,
    non-finite floats, special decimals -- sends the whole packet through the
    original row-by-row writer instead, so both paths produce identical bytes.
    """
    __slots__ = ('statement_id', 'parameter_sets', 'sql', 'parameter_types', 'parameter_writers',
                 '_column_kinds')
    
    COM_STMT_BULK_EXECUTE = 0xFA
    
    # Bulk flags
    SEND_TYPES_TO_SERVER = 128  # Send parameter types
    SEND_UNIT_RESULTS = 64  # retrieve unit results

    # Static FIELD_TYPE -> writer-method-name dispatch table. Built once at class
    # creation; resolved to a bound method per column in _determine_parameter_types.
    # (Previously a dict literal that rebuilt all 11 bound methods on every packet.)
    _WRITER_NAMES = {
        FIELD_TYPE.TINY: '_write_tiny',
        FIELD_TYPE.SHORT: '_write_short',
        FIELD_TYPE.LONG: '_write_long',
        FIELD_TYPE.LONGLONG: '_write_longlong',
        FIELD_TYPE.DOUBLE: '_write_double',
        FIELD_TYPE.NEWDECIMAL: '_write_decimal',
        FIELD_TYPE.VAR_STRING: '_write_string',
        FIELD_TYPE.BLOB: '_write_blob',
        FIELD_TYPE.DATETIME: '_write_datetime',
        FIELD_TYPE.DATE: '_write_date',
        FIELD_TYPE.TIME: '_write_time',
    }


    def __init__(self, statement_id: int | None, parameter_sets: List[List[Any]], sql: str = ""):
        """
        Initialize COM_STMT_BULK_EXECUTE packet
        
        Args:
            statement_id: Prepared statement ID
            parameter_sets: List of parameter lists (one per execution)
            sql: Original SQL (for debugging)
        """
        self.statement_id = statement_id
        self.parameter_sets = parameter_sets or []
        self.sql = sql
        # Determine parameter types and write functions by analyzing all parameter sets
        self.parameter_types: List[tuple[int, int]] = []
        self.parameter_writers: List[Callable[[PayloadWriter, Any], None]] = []  # Write functions for each parameter
        # Per column: (exact Python type of the non-NULL values, column has NULLs).
        # The type is None for a mixed column, NoneType for an all-NULL one.
        # Empty when the parameter sets are not rectangular.
        self._column_kinds: List[tuple[type | None, bool]] = []
        self._determine_parameter_types()

    def payload(self, context: Context, writer: PayloadWriter) -> bytearray:
        writer.reset()
        stream = writer
        stream.write_byte(self.COM_STMT_BULK_EXECUTE)
        stream.write_bytes(_STRUCT_I.pack(self.statement_id) if self.statement_id is not None else b'\xFF\xFF\xFF\xFF')
        
        # Flags: SEND_TYPES_TO_SERVER (128)
        stream.write_uint16(self.SEND_TYPES_TO_SERVER)
        
        if not self.parameter_sets:
            return stream.get_payload()
        
        # Write parameter types (2 bytes per parameter) - determined from all parameter sets
        for field_type, unsigned in self.parameter_types:
            stream.write_bytes(_STRUCT_BB.pack(field_type, unsigned))
        
        # Write parameter data for each row
        # Protocol: Until end of packet, for each parameter:
        #   - byte<1>: indicator (0=NONE/value follows, 1=NULL, 2=DEFAULT, etc.)
        #   - If indicator == 0: binary parameter value
        if self._column_kinds:
            rows_start = len(stream.get_payload())
            if self._write_rows_by_column(stream):
                return stream.get_payload()
            # A column defeated the fast path part-way through: drop what was
            # written and redo everything with the per-value writers.
            stream.truncate(rows_start)
        self._write_rows_by_value(stream)
        return stream.get_payload()

    def _write_rows_by_value(self, stream: PayloadWriter) -> None:
        """Row-major reference encoder: one dispatch per value."""
        parameter_writers = self.parameter_writers
        for param_set in self.parameter_sets:
            for param_idx, param in enumerate(param_set):
                if param is None:
                    stream.write_byte(1)  # NULL indicator
                elif isinstance(param, MrdbIndicator):
                    if param.indicator == 0:
                        stream.write_byte(0)  # NONE indicator - value follows
                        parameter_writers[param_idx](stream, param)
                    else:
                        stream.write_byte(param.indicator)
                else:
                    stream.write_byte(0)  # NONE indicator - value follows
                    parameter_writers[param_idx](stream, param)

    def _write_rows_by_column(self, stream: PayloadWriter) -> bool:
        """Encode the rows column by column, a chunk of rows at a time.

        Returns False (possibly after writing some rows) when a column holds a
        value the column encoders do not handle; the caller then falls back.
        """
        rows = self.parameter_sets
        kinds = self._column_kinds
        types = self.parameter_types
        for start in range(0, len(rows), _ENCODE_CHUNK_ROWS):
            chunk = rows[start:start + _ENCODE_CHUNK_ROWS]
            encoded_columns: List[List[bytes]] = []
            for column, (field_type, unsigned), (pytype, has_none) in zip(zip(*chunk), types, kinds):
                if pytype is None:
                    return False
                if pytype is _NONE_TYPE:
                    encoded_columns.append([_NULL_INDICATOR] * len(column))
                    continue
                values = [v for v in column if v is not None] if has_none else column
                encoded = self._encode_column(values, pytype, field_type, unsigned)
                if encoded is None:
                    return False
                if has_none:
                    it = iter(encoded)
                    encoded = [_NULL_INDICATOR if v is None else next(it) for v in column]
                encoded_columns.append(encoded)
            stream.write_bytes(b''.join(chain.from_iterable(zip(*encoded_columns))))
        return True

    @staticmethod
    def _encode_column(values: Sequence[Any], pytype: type, field_type: int, unsigned: int) -> List[bytes] | None:
        """Encode non-NULL *values*, all of exact type *pytype*, indicator byte
        included. None when the per-value writer must handle the column."""
        if pytype is int:
            if field_type == FIELD_TYPE.TINY:
                return list(map(_PACK_IND_b, repeat(0), values))
            if field_type == FIELD_TYPE.SHORT:
                return list(map(_PACK_IND_h, repeat(0), values))
            if field_type == FIELD_TYPE.LONG:
                return list(map(_PACK_IND_i, repeat(0), values))
            if field_type == FIELD_TYPE.LONGLONG:
                return list(map(_PACK_IND_Q if unsigned else _PACK_IND_q, repeat(0), values))
            if field_type == FIELD_TYPE.NEWDECIMAL:
                # Column promoted to DECIMAL (unsigned-64 and negative values mixed): sent as text.
                return _encode_lenenc(list(map(str.encode, map(str, values))))
            return None
        if pytype is str:
            return _encode_lenenc(list(map(str.encode, values)))
        if pytype is float:
            if not all(map(math.isfinite, values)):
                return None  # _write_double raises NotSupportedError
            return list(map(_PACK_IND_d, repeat(0), values))
        if pytype is bool:
            return [_TINY_TRUE if v else _TINY_FALSE for v in values]
        if pytype is decimal.Decimal:
            texts = list(map(str, values))
            if not _DECIMAL_SPECIALS.isdisjoint(texts):
                return None  # _write_decimal raises NotSupportedError
            return _encode_lenenc(list(map(str.encode, texts)))
        if pytype is bytes or pytype is bytearray:
            return _encode_lenenc(values)
        if pytype is datetime.datetime:
            return list(map(_encode_datetime, values))
        if pytype is datetime.date:
            return list(map(_encode_date, values))
        if pytype is datetime.time:
            return list(map(_encode_time, values))
        if pytype is datetime.timedelta:
            return list(map(_encode_timedelta, values))
        return None

    def _determine_parameter_types(self) -> None:
        """
        Determine parameter types and write functions by analyzing all parameter sets.
        For each column position, find the minimum type that can hold all values
        and store the corresponding write function.
        """
        rows = self.parameter_sets
        if not rows:
            return

        num_params = len(rows[0])

        if num_params > 0 and all(len(row) == num_params for row in rows):
            for column in zip(*rows):
                types = set(map(type, column))
                has_none = _NONE_TYPE in types
                types.discard(_NONE_TYPE)
                pytype: type | None = None
                resolved: tuple[int, int] | None = None
                if not types:
                    pytype = _NONE_TYPE
                    resolved = (FIELD_TYPE.NULL, 0)
                elif len(types) == 1:
                    pytype = next(iter(types))
                    values = [v for v in column if v is not None] if has_none else column
                    resolved = self._exact_column_type(pytype, values)
                    if resolved is None:
                        pytype = None  # unknown exact type: per-value isinstance scan
                if resolved is None:
                    resolved = self._scan_column_type(column)
                self._column_kinds.append((pytype, has_none))
                self._add_parameter_type(*resolved)
            return

        # Ragged parameter sets: analyse whatever each row has at this position.
        for param_idx in range(num_params):
            values = [row[param_idx] for row in rows if param_idx < len(row)]
            self._add_parameter_type(*self._scan_column_type(values))

    def _add_parameter_type(self, field_type: int, unsigned: int) -> None:
        self.parameter_types.append((field_type, unsigned))
        # Store the write function for this parameter (resolve the static
        # name table to a bound method).
        writer = getattr(self, self._WRITER_NAMES.get(field_type, '_write_string'))
        self.parameter_writers.append(writer)

    @staticmethod
    def _exact_column_type(pytype: type, values: Sequence[Any]) -> tuple[int, int] | None:
        """Field type of a column whose non-NULL values are all exactly *pytype*.
        None when the type is not one the column encoders know."""
        if pytype is int:
            low = min(values)
            high = max(values)
            field_type = _INT_TYPE_ORDER[max(_int_rank(low), _int_rank(high))]
            return BulkExecutePacket._resolve_integer_flags(
                field_type, _UNSIGNED_FLAG if high > _INT64_MAX else 0, low < 0)
        known_type = _EXACT_TYPE_FIELD.get(pytype)
        if known_type is None:
            return None
        return known_type, 0

    def _scan_column_type(self, values: Iterable[Any]) -> tuple[int, int]:
        """Per-value analysis of one column (reference behaviour)."""
        max_type = FIELD_TYPE.NULL
        unsigned = 0
        has_negative = False

        for param in values:
            param_type, param_unsigned = self._get_parameter_type(param)

            # Determine the maximum type needed
            if param_type != FIELD_TYPE.NULL:
                if max_type == FIELD_TYPE.NULL:
                    max_type = param_type
                else:
                    # For integers, upgrade to larger type if needed
                    max_type = self._get_wider_integer_type(max_type, param_type)
            # A single unsigned-64 value makes the whole column unsigned.
            if param_unsigned:
                unsigned = _UNSIGNED_FLAG
            elif type(param) is int and param < 0:
                has_negative = True

        return self._resolve_integer_flags(max_type, unsigned, has_negative)

    @staticmethod
    def _resolve_integer_flags(max_type: int, unsigned: int, has_negative: bool) -> tuple[int, int]:
        # A binary column carries one type+flag for every row. An unsigned-64
        # value (flag 0x80) and a negative value cannot coexist in an integer
        # column -- the negative would be packed signed and read back as a huge
        # positive. No integer type holds both ranges, so promote the column to
        # DECIMAL (sent as text), which represents both losslessly.
        if unsigned and has_negative:
            return FIELD_TYPE.NEWDECIMAL, 0
        if unsigned and max_type != FIELD_TYPE.LONGLONG:
            # Widened to a non-integer type (e.g. mixed with str/Decimal); the
            # unsigned flag is only meaningful on a LONGLONG column.
            return max_type, 0
        return max_type, unsigned


    def _get_wider_integer_type(self, type1: int, type2: int) -> int:
        """
        Get the wider of two integer types.
        
        Args:
            type1: First field type
            type2: Second field type
            
        Returns:
            The wider field type that can hold both
        """
        # If both are integer types, return the wider one
        if type1 in _INT_TYPE_ORDER and type2 in _INT_TYPE_ORDER:
            return _INT_TYPE_ORDER[max(_INT_TYPE_ORDER.index(type1), _INT_TYPE_ORDER.index(type2))]
        
        # If types don't match or aren't integers, prefer type2 (current param type)
        if type1 != type2:
            return type2
        
        return type1
    
    def _get_parameter_type(self, param: Any) -> tuple[int, int]:
        """
        Get MySQL field type and unsigned flag for parameter
        
        Args:
            param: Parameter value
            
        Returns:
            Tuple of (field_type, unsigned_flag)
        """
        if param is None:
            return FIELD_TYPE.NULL, 0
        elif isinstance(param, bool):
            return FIELD_TYPE.TINY, 0
        elif isinstance(param, int):
            if -128 <= param <= 127:
                return FIELD_TYPE.TINY, 0
            elif -32768 <= param <= 32767:
                return FIELD_TYPE.SHORT, 0
            elif -2147483648 <= param <= 2147483647:
                return FIELD_TYPE.LONG, 0
            elif param > _INT64_MAX:
                return FIELD_TYPE.LONGLONG, _UNSIGNED_FLAG
            return FIELD_TYPE.LONGLONG, 0
        elif isinstance(param, float):
            return FIELD_TYPE.DOUBLE, 0
        elif isinstance(param, decimal.Decimal):
            return FIELD_TYPE.NEWDECIMAL, 0
        elif isinstance(param, str):
            return FIELD_TYPE.VAR_STRING, 0
        elif isinstance(param, (bytes, bytearray)):
            return FIELD_TYPE.BLOB, 0
        elif isinstance(param, datetime.datetime):
            return FIELD_TYPE.DATETIME, 0
        elif isinstance(param, datetime.date):
            return FIELD_TYPE.DATE, 0
        elif isinstance(param, datetime.time):
            return FIELD_TYPE.TIME, 0
        elif isinstance(param, datetime.timedelta):
            return FIELD_TYPE.TIME, 0
        elif isinstance(param, array.array) and param.typecode == 'f':
            return FIELD_TYPE.BLOB, 0
        elif isinstance(param, MrdbIndicator):
            return FIELD_TYPE.NULL, 0
        else:
            return FIELD_TYPE.VAR_STRING, 0

    # =========================================================================
    # Type-specific write methods
    # =========================================================================
    
    def _write_tiny(self, stream: PayloadWriter, param: Any) -> None:
        """Write TINY (1 byte signed integer)"""
        if isinstance(param, bool):
            stream.write_byte(1 if param else 0)
        else:
            stream.write_bytes(_STRUCT_b.pack(param))
    
    def _write_short(self, stream: PayloadWriter, param: Any) -> None:
        """Write SHORT (2 byte signed integer)"""
        stream.write_bytes(_STRUCT_h.pack(param))
    
    def _write_long(self, stream: PayloadWriter, param: Any) -> None:
        """Write LONG (4 byte signed integer)"""
        stream.write_bytes(_STRUCT_i.pack(param))
    
    def _write_longlong(self, stream: PayloadWriter, param: Any) -> None:
        """Write LONGLONG (8 byte integer, unsigned above the signed-64 range)"""
        if param > _INT64_MAX:
            stream.write_bytes(_STRUCT_Q.pack(param))
        else:
            stream.write_bytes(_STRUCT_q.pack(param))
    
    def _write_double(self, stream: PayloadWriter, param: Any) -> None:
        """Write DOUBLE (8 byte float)"""
        if repr(param) in ("nan", "inf", "-inf"):
            raise NotSupportedError(f"Float value '{repr(param)}' is not supported.")
        stream.write_bytes(_STRUCT_d.pack(param))
    
    def _write_decimal(self, stream: PayloadWriter, param: Any) -> None:
        """Write DECIMAL as length-encoded string"""
        if param.__str__() in ("NaN", "sNaN", "Infinity", "-Infinity"):
            raise NotSupportedError(f"Decimal value '{param.__str__()}' is not supported.")
        stream.write_length_encoded_string(str(param))
    
    def _write_string(self, stream: PayloadWriter, param: Any) -> None:
        """Write VAR_STRING as length-encoded string"""
        stream.write_length_encoded_string(param)
    
    def _write_blob(self, stream: PayloadWriter, param: bytes | bytearray | memoryview | array.array[float]) -> None:
        """Write BLOB as length-encoded bytes (or a float32 VECTOR array)."""
        if isinstance(param, array.array):
            # VECTOR: pack the float32 ('f') array as little-endian bytes.
            if param.typecode == 'f':
                if HAS_NUMPY:
                    float_bytes = numpy.array(param, numpy.float32).tobytes()
                else:
                    float_bytes = param.tobytes()
                stream.write_length_encoded_bytes(float_bytes)
        else:
            stream.write_length_encoded_bytes(param)
    
    def _write_datetime(self, stream: PayloadWriter, param: Any) -> None:
        """Write DATETIME in MySQL binary format"""
        if param.microsecond:
            stream.write_bytes(_STRUCT_DATETIME_WITH_MICRO.pack(
                11, param.year, param.month, param.day,
                param.hour, param.minute, param.second, param.microsecond
            ))
        else:
            stream.write_bytes(_STRUCT_DATETIME_NO_MICRO.pack(
                7, param.year, param.month, param.day,
                param.hour, param.minute, param.second
            ))
    
    def _write_date(self, stream: PayloadWriter, param: Any) -> None:
        """Write DATE in MySQL binary format"""
        stream.write_bytes(_STRUCT_DATE.pack(4, param.year, param.month, param.day))
    
    def _write_time(self, stream: PayloadWriter, param: Any) -> None:
        """Write TIME in MySQL binary format"""
        if isinstance(param, datetime.timedelta):
            negative, days, hours, minutes, seconds, microseconds = split_timedelta(param)

            if microseconds:
                stream.write_bytes(_STRUCT_TIME_WITH_MICRO.pack(
                    12, 1 if negative else 0, days, hours, minutes, seconds, microseconds
                ))
            else:
                stream.write_bytes(_STRUCT_TIME_NO_MICRO.pack(
                    8, 1 if negative else 0, days, hours, minutes, seconds
                ))
        else:  # datetime.time
            if param.microsecond:
                stream.write_bytes(_STRUCT_TIME_WITH_MICRO.pack(
                    12, 0, 0, param.hour, param.minute, param.second, param.microsecond
                ))
            else:
                stream.write_bytes(_STRUCT_TIME_NO_MICRO.pack(
                    8, 0, 0, param.hour, param.minute, param.second
                ))

    def is_binary(self) -> bool:
        return True

    def type(self) -> str:
        return "COM_STMT_BULK_EXECUTE"
