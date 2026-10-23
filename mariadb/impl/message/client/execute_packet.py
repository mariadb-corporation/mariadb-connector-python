# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from __future__ import annotations

import array
import datetime
import decimal
import struct
from typing import Any, Callable, Dict, List

# Pre-compiled struct formats for performance
_STRUCT_I = struct.Struct('<I')  # unsigned int (4 bytes) for microseconds/days
_PACK_i = struct.Struct('<i').pack  # signed int for int
_PACK_q = struct.Struct('<q').pack  # signed long long for bigint
_PACK_Q = struct.Struct('<Q').pack  # unsigned long long for bigint > 2**63-1
_PACK_d = struct.Struct('<d').pack  # double for float
_PACK_HEADER = struct.Struct('<BIBI').pack  # command, statement id, flags, iteration count

_INT64_MAX = 0x7FFFFFFFFFFFFFFF
_UNSIGNED_FLAG = 0x80

# Composite struct formats for datetime/date/time (pack multiple fields at once)
_PACK_DATETIME_WITH_MICRO = struct.Struct('<BHBBBBBI').pack  # length(B) + year(H) + month(B) + day(B) + hour(B) + minute(B) + second(B) + microsecond(I)
_PACK_DATETIME_NO_MICRO = struct.Struct('<BHBBBBB').pack    # length(B) + year(H) + month(B) + day(B) + hour(B) + minute(B) + second(B)
_PACK_DATE = struct.Struct('<BHBB').pack                     # length(B) + year(H) + month(B) + day(B)
_PACK_TIME_WITH_MICRO = struct.Struct('<BBIBBBI').pack      # length(B) + negative(B) + days(I) + hour(B) + minute(B) + second(B) + microsecond(I)
_PACK_TIME_NO_MICRO = struct.Struct('<BBIBBB').pack         # length(B) + negative(B) + days(I) + hour(B) + minute(B) + second(B)

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

_FT_NULL = FIELD_TYPE.NULL
_FT_LONG = FIELD_TYPE.LONG
_FT_LONGLONG = FIELD_TYPE.LONGLONG
_FT_VAR_STRING = FIELD_TYPE.VAR_STRING


class ExecutePacket(ClientMessage):
    """
    Execute packet for prepared statement execution (COM_STMT_EXECUTE)

    See: https://mariadb.com/kb/en/com_stmt_execute/
    """
    __slots__ = ('statement_id', 'parameters', 'sql')

    COM_STMT_EXECUTE = 0x17

    def __init__(self, statement_id: int | None, parameters: List[Any] | None = None, sql: str = ""):
        """Initialize COM_STMT_EXECUTE packet with statement ID and parameters"""
        self.statement_id = statement_id
        self.parameters = parameters or []
        self.sql = sql

    def payload(self, context: Context, writer: PayloadWriter) -> bytearray:
        writer.reset()
        header = _PACK_HEADER(
            self.COM_STMT_EXECUTE,
            self.statement_id if self.statement_id is not None else 0xFFFFFFFF,
            0,  # flags
            1)  # iteration count - always 1

        parameters = self.parameters
        if not parameters:
            writer.write_bytes(header)
            return writer.get_payload()

        num_params = len(parameters)

        # The null bitmap and the type block are filled while the values are
        # collected, then everything is joined once. An int is sent as LONG
        # when it fits in 32 bits and as LONGLONG otherwise: the server does
        # not need the smallest fitting type, and choosing it costs more than
        # the bytes it saves.
        null_bitmap = bytearray((num_params + 7) >> 3)
        types = bytearray(num_params * 2)
        fragments: List[bytes | bytearray] = [header, null_bitmap, b'\x01', types]
        append = fragments.append
        _type = type
        encoders = PARAM_ENCODERS
        i = 0
        for param in parameters:
            param_type = _type(param)  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
            if param_type is int:
                # Inline: ints are the most frequent parameter type
                if -2147483648 <= param <= 2147483647:
                    types[i * 2] = _FT_LONG
                    append(_PACK_i(param))
                elif param > _INT64_MAX:
                    types[i * 2] = _FT_LONGLONG
                    types[i * 2 + 1] = _UNSIGNED_FLAG
                    append(_PACK_Q(param))
                else:
                    types[i * 2] = _FT_LONGLONG
                    append(_PACK_q(param))
            elif param is None:
                null_bitmap[i >> 3] |= 1 << (i & 7)
            else:
                encoder = encoders.get(param_type)  # pyright: ignore[reportUnknownArgumentType]
                if encoder is None:
                    encoder = _resolve_encoder(param_type)  # pyright: ignore[reportUnknownArgumentType]
                field_type, flags, fragment = encoder(param)
                if fragment is None:
                    null_bitmap[i >> 3] |= 1 << (i & 7)
                else:
                    types[i * 2] = field_type
                    types[i * 2 + 1] = flags
                    append(fragment)
            i += 1

        writer.write_bytes(b''.join(fragments))
        return writer.get_payload()

    def is_binary(self) -> bool:
        return True

    def type(self) -> str:
        return "COM_STMT_EXECUTE"


# An encoder returns (field type, type flags, encoded value); a None value
# means the parameter is sent as NULL (null-bitmap bit, no value).
_Encoded = tuple[int, int, bytes | None]


def _length_encoded(data: bytes) -> bytes:
    """Prefix *data* with its length-encoded size"""
    length = len(data)
    if length < 251:
        return bytes((length,)) + data
    if length < 65536:
        return b'\xfc' + length.to_bytes(2, 'little') + data
    if length < 16777216:
        return b'\xfd' + length.to_bytes(3, 'little') + data
    return b'\xfe' + length.to_bytes(8, 'little') + data


def _encode_int(param: int) -> _Encoded:
    """int subclasses (IntEnum, ...); exact ints are encoded inline in payload()"""
    if -2147483648 <= param <= 2147483647:
        return (_FT_LONG, 0, _PACK_i(param))
    if param > _INT64_MAX:
        return (_FT_LONGLONG, _UNSIGNED_FLAG, _PACK_Q(param))
    return (_FT_LONGLONG, 0, _PACK_q(param))


def _encode_bool(param: bool) -> _Encoded:
    return (FIELD_TYPE.TINY, 0, b'\x01' if param else b'\x00')


def _encode_float(param: float) -> _Encoded:
    if repr(param) in ("nan", "inf", "-inf"):
        raise NotSupportedError(f"Float value '{repr(param)}' is not supported.")
    return (FIELD_TYPE.DOUBLE, 0, _PACK_d(param))


def _encode_decimal(param: decimal.Decimal) -> _Encoded:
    text = param.__str__()
    if text in ("NaN", "sNaN", "Infinity", "-Infinity"):
        raise NotSupportedError(f"Decimal value '{text}' is not supported.")
    return (FIELD_TYPE.NEWDECIMAL, 0, _length_encoded(text.encode('utf-8')))


def _encode_str(param: str) -> _Encoded:
    return (_FT_VAR_STRING, 0, _length_encoded(param.encode('utf-8')))


def _encode_bytes(param: bytes | bytearray) -> _Encoded:
    return (FIELD_TYPE.BLOB, 0, _length_encoded(bytes(param)))


def _encode_datetime(param: datetime.datetime) -> _Encoded:
    """datetime in MySQL binary format"""
    if param.microsecond:
        # 11 bytes: length(1) + year(2) + month(1) + day(1) + hour(1) + minute(1) + second(1) + microsecond(4)
        return (FIELD_TYPE.DATETIME, 0, _PACK_DATETIME_WITH_MICRO(
            11, param.year, param.month, param.day,
            param.hour, param.minute, param.second, param.microsecond))
    # 7 bytes: length(1) + year(2) + month(1) + day(1) + hour(1) + minute(1) + second(1)
    return (FIELD_TYPE.DATETIME, 0, _PACK_DATETIME_NO_MICRO(
        7, param.year, param.month, param.day,
        param.hour, param.minute, param.second))


def _encode_date(param: datetime.date) -> _Encoded:
    """date in MySQL binary format: length(1) + year(2) + month(1) + day(1)"""
    return (FIELD_TYPE.DATE, 0, _PACK_DATE(4, param.year, param.month, param.day))


def _encode_time(param: datetime.time) -> _Encoded:
    """time in MySQL binary format"""
    if param.microsecond:
        # 12 bytes: length(1) + negative(1) + days(4) + hour(1) + minute(1) + second(1) + microsecond(4)
        return (FIELD_TYPE.TIME, 0, _PACK_TIME_WITH_MICRO(
            12, 0, 0, param.hour, param.minute, param.second, param.microsecond))
    # 8 bytes: length(1) + negative(1) + days(4) + hour(1) + minute(1) + second(1)
    return (FIELD_TYPE.TIME, 0, _PACK_TIME_NO_MICRO(
        8, 0, 0, param.hour, param.minute, param.second))


def _encode_timedelta(param: datetime.timedelta) -> _Encoded:
    """timedelta as time in MySQL binary format"""
    negative, days, hours, minutes, seconds, microseconds = split_timedelta(param)
    if microseconds:
        return (FIELD_TYPE.TIME, 0, _PACK_TIME_WITH_MICRO(
            12, 1 if negative else 0, days, hours, minutes, seconds, microseconds))
    return (FIELD_TYPE.TIME, 0, _PACK_TIME_NO_MICRO(
        8, 1 if negative else 0, days, hours, minutes, seconds))


def _encode_array(param: "array.array[float]") -> _Encoded:
    """Float array for VECTOR columns; an empty array is sent as NULL"""
    if len(param) == 0:
        return (_FT_NULL, 0, None)
    if HAS_NUMPY:
        float_bytes: bytes = numpy.array(param, numpy.float32).tobytes()
    else:
        float_bytes = param.tobytes()
    return (FIELD_TYPE.BLOB, 0, _length_encoded(float_bytes))


def _encode_null(param: Any) -> _Encoded:
    """None and indicator values: indicators 1 (NULL), 2 (DEFAULT), 3 (IGNORE),
    4 (IGNORE_ROW) are handled at a higher level, here they are NULL"""
    return (_FT_NULL, 0, None)


def _encode_as_str(param: Any) -> _Encoded:
    """Any other object: its string representation"""
    return (_FT_VAR_STRING, 0, _length_encoded(str(param).encode('utf-8')))


# Dispatch on the exact runtime type; each encoder receives a value of its key
# type, so the value annotation stays deliberately permissive (the call site
# passes a dynamic user value).
PARAM_ENCODERS: Dict[type, Callable[..., _Encoded]] = {
    int: _encode_int,
    bool: _encode_bool,
    float: _encode_float,
    decimal.Decimal: _encode_decimal,
    str: _encode_str,
    bytes: _encode_bytes,
    bytearray: _encode_bytes,
    datetime.datetime: _encode_datetime,
    datetime.date: _encode_date,
    datetime.time: _encode_time,
    datetime.timedelta: _encode_timedelta,
    array.array: _encode_array,
    type(None): _encode_null,
    MrdbIndicator: _encode_null,
}
_PARAM_ENCODERS_MAX = 256


def _resolve_encoder(param_type: type) -> Callable[..., _Encoded]:
    """Encoder for a type not in PARAM_ENCODERS: the one of its nearest base
    class (an IntEnum encodes as int, a datetime subclass as datetime), else
    the string representation. The result is memoised in PARAM_ENCODERS."""
    encoder = _encode_as_str
    for base in param_type.__mro__[1:]:
        found = PARAM_ENCODERS.get(base)
        if found is not None:
            encoder = found
            break
    if len(PARAM_ENCODERS) >= _PARAM_ENCODERS_MAX:
        # Unbounded growth would need a stream of new dynamic classes; start over
        PARAM_ENCODERS.clear()
        PARAM_ENCODERS.update(_BUILTIN_ENCODERS)
    PARAM_ENCODERS[param_type] = encoder
    return encoder


_BUILTIN_ENCODERS = dict(PARAM_ENCODERS)
