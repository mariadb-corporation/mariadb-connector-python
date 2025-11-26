# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

import array
import datetime
import decimal
import ipaddress
import uuid
from typing import TYPE_CHECKING, Any, List
import struct
import re
try:
    import numpy
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

from ...client.context import Context
from mariadb_shared.constants.STATUS import NO_BACKSLASH_ESCAPES
from mariadb_shared.constants.INDICATOR import MrdbIndicator
from ..client_message import ClientMessage
from ....exceptions import NotSupportedError

BINARY_PREFIX: bytes = bytearray(b"_binary'")
QUOTE_BYTE: int = b"'"[0]
COM_QUERY = 0x03

NULL_BYTES: bytes = b"NULL"

class QueryPacket(ClientMessage):
    """
    Simple query packet for SQL execution without parameters
    """

    def __init__(self, sql: str):
        """Initialize COM_QUERY packet with SQL"""
        self.sql = sql
        
    def payload(self, context: Context) -> bytes:
        return b'\0\0\0\0\x03' + self.sql.encode('utf-8')

    def is_binary(self) -> bool:
        return False

    def type(self) -> str:
        return "COM_QUERY"


class QueryWithParamPacket(ClientMessage):
    """
    Parameterized query packet for SQL execution with parameter binding
    """

    def __init__(self, sql_bytes: bytes, param_positions: List[int], parameters: List[Any]):
        """
        Initialize COM_QUERY packet with pre-parsed SQL bytes and parameters

        Args:
            sql_bytes: SQL encoded as UTF-8 bytes
            param_positions: Byte positions (start, end) pairs where placeholders are
            parameters: Parameter values to bind
        """
        self.sql_bytes = sql_bytes
        self.param_positions = param_positions
        self.parameters = parameters
        
    def payload(self, context: Context) -> bytes:
        """Generate COM_QUERY packet payload with SQL and bound parameters"""
        no_backslash_escapes = context.server_status & NO_BACKSLASH_ESCAPES > 0

        # Write SQL fragments interleaved with parameters
        last_pos = 0
        param_idx = 0
        params = self.parameters
        converter = PARAM_CONVERT_TBL
        parts = [b''] * (len(self.param_positions) + 2 + 1)
        
        parts[0] = b'\0\0\0\0\x03'
        count= 1
        # Iterate through placeholder positions (they come in pairs: start, end)
        for i in range(0, len(self.param_positions), 2):
            start_pos = self.param_positions[i]
            end_pos = self.param_positions[i + 1]

            # Write SQL fragment before this placeholder
            if start_pos > last_pos:
                parts[count]= self.sql_bytes[last_pos:start_pos]
                count += 1

            # Write parameter value
            if param_idx < len(self.parameters):
                parts[count] = converter.get(type(params[param_idx]), lambda v, ctx=None: str(v).encode('utf8'))(params[param_idx], no_backslash_escapes)
                param_idx += 1
                count += 1
            else:
                parts[count] = b'NULL'
                count += 1

            last_pos = end_pos

        # Write remaining SQL after last placeholder
        if last_pos < len(self.sql_bytes):
            parts[count] = self.sql_bytes[last_pos:]
        return b''.join(parts)

    def is_binary(self) -> bool:
        return False

    def type(self) -> str:
        return "COM_QUERY"


#### Conversion routines should be moved to a "central" place

def float2bytes(value: float) -> bytes:
    if repr(value) in ("nan", "inf", "-inf"):
        raise NotSupportedError(f"Float value '{repr(value)}' is not supported.")
    return str(value).encode('ascii')

def decimal2bytes(value: float) -> bytes:
    if value.__str__() in ("NaN", "sNaN", "Infinity", "-Infinity"):
        raise NotSupportedError(f"Decimal value '{value.__str__()}' is not supported.")
    return str(value).encode('ascii')

_ESCAPE_REGEX = re.compile(r'[\\\'"\0]')
_ESCAPE_MAP = {'\\': '\\\\', "'": "\\'", '"': '\\"', '\0': '\\0'}

def escape_str(string: str, no_backslash_escapes: bool = False) -> bytes:
    """
    Escape a string for SQL statements
    """
    if no_backslash_escapes:
        # When NO_BACKSLASH_ESCAPES is set, single quotes are escaped by doubling them
        escaped = string.replace("'", "''")
    else:
        # Standard escaping: backslash, quote, double quote, zero byte
        escaped = _ESCAPE_REGEX.sub(lambda m: _ESCAPE_MAP[m.group(0)], string)

    return b"'" + escaped.encode(encoding="utf8") + b"'"

def timedelta(val: datetime.timedelta) -> bytes:
    total_seconds = int(val.total_seconds())
    is_negative = total_seconds < 0
    
    # Work with absolute values
    abs_seconds = abs(total_seconds)
    hours = abs_seconds // 3600
    minutes = (abs_seconds % 3600) // 60
    seconds = abs_seconds % 60
    microseconds = abs(val.microseconds)
    
    sign = '-' if is_negative else ''
    return f"'{sign}{hours}:{minutes:02d}:{seconds:02d}.{microseconds}'".encode('ascii')

_ESCAPE_BYTES_REGEX = re.compile(rb'[\\\'"\0]')
_ESCAPE_BYTES_MAP = {b'\\': b'\\\\', b"'": b"\\'", b'"': b'\\"', b'\0': b'\\0'}

def escape_bytes(b : bytes, no_backslash_escapes: bool = False) -> bytes:
    """
    Escape a string for SQL statements
    """
    if no_backslash_escapes:
        # When NO_BACKSLASH_ESCAPES is set, single quotes are escaped by doubling them
        escaped = b.replace(b"'", b"''")
    else:
        # Standard escaping: backslash, quote, double quote, zero byte
        escaped = _ESCAPE_BYTES_REGEX.sub(lambda m: _ESCAPE_BYTES_MAP[m.group(0)], b)

    return b"_binary'" + escaped + b"'"

def float_array_to_bytes(arr: array.array, no_backslash_escapes: bool = False) -> bytes:
    """Convert float array to binary representation for VECTOR columns"""
    if len(arr) == 0:
        return b'NULL'
    # Float array for VECTOR columns - encode as numpy float32 bytes
    if HAS_NUMPY:
        float_bytes = numpy.array(arr, numpy.float32).tobytes()
    else:
        # Fallback: use array.tobytes() directly
        float_bytes = arr.tobytes()
    return escape_bytes(float_bytes, no_backslash_escapes)

def tuple_to_bytes(t: tuple, no_backslash_escapes: bool = False) -> bytes:
    """Convert tuple to bytes - raises error as tuples are not directly supported"""
    raise NotSupportedError("Tuple parameters are not supported. Use individual values or convert to a supported type.")

def indicator_val(v):
   if v.indicator == 1:
       return b'NULL'
   elif v.indicator == 2:
       return b'DEFAULT'
   elif v.indicator == 3: # bulk only
       pass
   elif v.indicator == 4: # bulk only
       pass
   else:
       return b'NULL'


PARAM_CONVERT_TBL = {
  int: lambda v, ctx= None: str(v).encode('ascii'),
  float: lambda v, ctx= None: float2bytes(v),
  str: lambda v, ctx: escape_str(v, ctx),
  bytes: lambda v, ctx= None: escape_bytes(v, ctx),
  bytearray: lambda v, ctx= None: escape_bytes(v, ctx),
  decimal.Decimal: lambda v, ctx=None: decimal2bytes(v),
  datetime.date: lambda v, ctx=None: b"'" + str(v).encode('ascii') + b"'",
  datetime.datetime: lambda v, ctx=None: b"'" + str(v).encode('ascii') + b"'",
  datetime.time: lambda v, ctx=None: b"'" + str(v).encode('ascii') + b"'",
  datetime.timedelta: lambda v, ctx=None: timedelta(v),
  type(None): lambda v, ctx= None: b'NULL',
  bool: lambda v, ctx= None: b'1' if v else b'0',
  MrdbIndicator: lambda v, ctx=None: indicator_val(v),
  ipaddress.IPv4Address: lambda v, ctx=None: b"'" +str(v).encode('ascii') + b"'",
  ipaddress.IPv6Address: lambda v, ctx=None: b"'" +str(v).encode('ascii') + b"'",
  uuid.UUID: lambda v, ctx=None: b"'" +str(v).encode('ascii') + b"'",
  array.array: lambda v, ctx=None: float_array_to_bytes(v, ctx),
  tuple: lambda v, ctx=None: tuple_to_bytes(v, ctx),
}
