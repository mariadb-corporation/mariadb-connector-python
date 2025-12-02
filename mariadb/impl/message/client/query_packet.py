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
TRUE_BYTES: bytes = b"1"
FALSE_BYTES: bytes = b"0"
QUOTE_BYTES: bytes = b"'"
BINARY_QUOTE_PREFIX: bytes = b"_binary'"

class QueryPacket(ClientMessage):
    """
    Query packet for SQL execution
    Use static factory methods to create instances:
    - QueryPacket.from_sql(sql_string) for plain SQL
    - QueryPacket.from_payload(payload_bytes) for pre-formatted payload with parameters
    """

    def __init__(self, payload_bytes: bytearray):
        """
        Initialize COM_QUERY packet with pre-formatted payload
        
        Args:
            payload_bytes: Complete packet payload including header + COM_QUERY + SQL
        """
        self._payload_bytes = payload_bytes
    
    @staticmethod
    def from_sql(sql: str) -> 'QueryPacket':
        """
        Create QueryPacket from SQL string
        
        Args:
            sql: SQL statement as string
            
        Returns:
            QueryPacket instance
        """
        sql_bytes = sql.encode('utf-8')
        payload = bytearray(5 + len(sql_bytes))
        payload[0:4] = b'\x00\x00\x00\x00'  # Length placeholder
        payload[4] = 0x03  # COM_QUERY
        payload[5:] = sql_bytes
        return QueryPacket(payload)
    
    @staticmethod
    def from_payload(payload_bytes: bytes) -> 'QueryPacket':
        """
        Create QueryPacket from pre-formatted payload bytes
        
        Args:
            payload_bytes: Complete packet payload (header + COM_QUERY + formatted SQL)
            
        Returns:
            QueryPacket instance
        """
        return QueryPacket(payload_bytes)
        
    def payload(self, context: Context) -> bytearray:
        return self._payload_bytes

    def is_binary(self) -> bool:
        return False

    def type(self) -> str:
        return "COM_QUERY"


# ============================================================================
# Parameter Conversion Functions
# Used by sql_parser.py for parameter substitution
# ============================================================================

def float2bytes(value: float, ctx=None) -> bytes:
    if repr(value) in ("nan", "inf", "-inf"):
        raise NotSupportedError(f"Float value '{repr(value)}' is not supported.")
    return str(value).encode('ascii')

def decimal2bytes(value: float, ctx=None) -> bytes:
    if value.__str__() in ("NaN", "sNaN", "Infinity", "-Infinity"):
        raise NotSupportedError(f"Decimal value '{value.__str__()}' is not supported.")
    return str(value).encode('ascii')

_ESCAPE_REGEX = re.compile(r'[\\\'"\0]')
_ESCAPE_MAP = {'\\': '\\\\', "'": "\\'", '"': '\\"', '\0': '\\0'}

def escape_str(string: str, no_backslash_escapes: bool = False) -> bytearray:
    """
    Escape a string for SQL statements
    """
    if no_backslash_escapes:
        # When NO_BACKSLASH_ESCAPES is set, single quotes are escaped by doubling them
        if "'" in string:
            escaped = string.replace("'", "''")
        else:
            escaped = string
    else:
        # Fast path: check if escaping is needed at all
        if not any(c in string for c in '\\\'"\0'):
            # No special characters, skip regex
            escaped = string
        else:
            # Standard escaping: backslash, quote, double quote, zero byte
            escaped = _ESCAPE_REGEX.sub(lambda m: _ESCAPE_MAP[m.group(0)], string)

    # Avoid multiple allocations with concatenation
    encoded = escaped.encode(encoding="utf8")
    result = bytearray(len(encoded) + 2)
    result[0] = 39  # Single quote '
    result[1:-1] = encoded
    result[-1] = 39  # Single quote '
    return result

def timedelta(val: datetime.timedelta, ctx=None) -> bytes:
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

def escape_bytes(b : bytes, no_backslash_escapes: bool = False) -> bytearray:
    """
    Escape a string for SQL statements
    """
    if no_backslash_escapes:
        # When NO_BACKSLASH_ESCAPES is set, single quotes are escaped by doubling them
        if b"'" in b:
            escaped = b.replace(b"'", b"''")
        else:
            escaped = b
    else:
        # Fast path: check if escaping is needed
        if not any(c in b for c in b'\\\'"\0'):
            escaped = b
        else:
            # Standard escaping: backslash, quote, double quote, zero byte
            escaped = _ESCAPE_BYTES_REGEX.sub(lambda m: _ESCAPE_BYTES_MAP[m.group(0)], b)

    # Avoid multiple allocations with concatenation
    result = bytearray(len(BINARY_QUOTE_PREFIX) + len(escaped) + 9) # BINARY_QUOTE_PREFIX + escaped + QUOTE_BYTES
    result[0:8] = BINARY_QUOTE_PREFIX
    result[8:-1] = escaped
    result[-1:] = QUOTE_BYTES
    return result

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

def indicator_val(v, ctx=None):
   indicator = v.indicator
   if indicator == 1:
       return NULL_BYTES
   elif indicator == 2:
       return b'DEFAULT'
   else:
       return NULL_BYTES


# Optimized converter functions (avoid lambda overhead)
def _int_to_bytes(v, ctx=None):
    return str(v).encode('ascii')

def _bool_to_bytes(v, ctx=None):
    return TRUE_BYTES if v else FALSE_BYTES

def _none_to_bytes(v, ctx=None):
    return NULL_BYTES

def _date_to_bytes(v, ctx=None):
    return QUOTE_BYTES + str(v).encode('ascii') + QUOTE_BYTES

def _ipv4_to_bytes(v, ctx=None):
    return QUOTE_BYTES + str(v).encode('ascii') + QUOTE_BYTES

def _ipv6_to_bytes(v, ctx=None):
    return QUOTE_BYTES + str(v).encode('ascii') + QUOTE_BYTES

def _uuid_to_bytes(v, ctx=None):
    return QUOTE_BYTES + str(v).encode('ascii') + QUOTE_BYTES

PARAM_CONVERT_TBL = {
  int: _int_to_bytes,
  float: float2bytes,
  str: escape_str,
  bytes: escape_bytes,
  bytearray: escape_bytes,
  decimal.Decimal: decimal2bytes,
  datetime.date: _date_to_bytes,
  datetime.datetime: _date_to_bytes,
  datetime.time: _date_to_bytes,
  datetime.timedelta: timedelta,
  type(None): _none_to_bytes,
  bool: _bool_to_bytes,
  MrdbIndicator: indicator_val,
  ipaddress.IPv4Address: _ipv4_to_bytes,
  ipaddress.IPv6Address: _ipv6_to_bytes,
  uuid.UUID: _uuid_to_bytes,
  array.array: float_array_to_bytes,
  tuple: tuple_to_bytes,
}
