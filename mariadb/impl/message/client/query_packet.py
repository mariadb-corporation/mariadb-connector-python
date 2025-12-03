# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Query packet for SQL execution with parameter substitution.

This module provides proper parsing of SQL statements to identify placeholders
while correctly handling:
- String literals (single and double quotes)
- Comments (/* */, --, #, //)
- Backtick identifiers
- Escape sequences
"""

import array
import datetime
import decimal
import ipaddress
import uuid
from typing import TYPE_CHECKING, Any, List, Tuple, Optional
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
from ....exceptions import NotSupportedError, ProgrammingError

# Constants
BINARY_PREFIX: bytes = bytearray(b"_binary'")
QUOTE_BYTE: int = b"'"[0]
COM_QUERY = 0x03

NULL_BYTES: bytes = b"NULL"
TRUE_BYTES: bytes = b"1"
FALSE_BYTES: bytes = b"0"
QUOTE_BYTES: bytes = b"'"
BINARY_QUOTE_PREFIX: bytes = b"_binary'"


# ============================================================================
# Parameter Conversion Functions
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
    Escape bytes for SQL statements
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
    result = bytearray(len(BINARY_QUOTE_PREFIX) + len(escaped) + 9)
    result[0:8] = BINARY_QUOTE_PREFIX
    result[8:-1] = escaped
    result[-1:] = QUOTE_BYTES
    return result

def float_array_to_bytes(arr: array.array, no_backslash_escapes: bool = False) -> bytes:
    """Convert float array to binary representation for VECTOR columns"""
    if len(arr) == 0:
        return b'NULL'
    if HAS_NUMPY:
        float_bytes = numpy.array(arr, numpy.float32).tobytes()
    else:
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

# ============================================================================
# Pre-computed lookup tables for SQL parsing optimization
# ============================================================================

# Character classification lookup tables (256 entries for all byte values)
_IS_ALPHA = bytearray(256)
_IS_DIGIT = bytearray(256)
_IS_IDENTIFIER_START = bytearray(256)
_IS_IDENTIFIER_CHAR = bytearray(256)
_IS_SPECIAL_CHAR = bytearray(256)  # Characters that need special handling in NORMAL state

# Initialize lookup tables
for i in range(256):
    # A-Z (65-90), a-z (97-122)
    if (65 <= i <= 90) or (97 <= i <= 122):
        _IS_ALPHA[i] = 1
        _IS_IDENTIFIER_START[i] = 1
        _IS_IDENTIFIER_CHAR[i] = 1
    # 0-9 (48-57)
    if 48 <= i <= 57:
        _IS_DIGIT[i] = 1
        _IS_IDENTIFIER_CHAR[i] = 1
    # _ (95)
    if i == 95:
        _IS_IDENTIFIER_START[i] = 1
        _IS_IDENTIFIER_CHAR[i] = 1

# Mark special characters that need handling in NORMAL state
# These are characters that can trigger state changes or are placeholders
_SPECIAL_CHARS = [
    39,  # ' (single quote)
    34,  # " (double quote)
    96,  # ` (backtick)
    63,  # ? (qmark placeholder)
    37,  # % (format placeholder)
    58,  # : (named placeholder)
    47,  # / (comment start)
    42,  # * (comment)
    35,  # # (comment)
    45,  # - (comment)
]
for char_code in _SPECIAL_CHARS:
    _IS_SPECIAL_CHAR[char_code] = 1


def normalize_to_qmark(sql: str) -> Tuple[str, Optional[List[str]]]:
    """
    Convert SQL with any placeholder style to qmark (?) style.
    
    Supports:
    - ? (qmark) - no conversion needed
    - %s, %d (format) - convert to ?
    - %(name)s (pyformat) - convert to ? and return parameter name list
    - :name (named) - convert to ? and return parameter name list
    
    Args:
        sql: SQL statement with any placeholder style
    
    Returns:
        Tuple of (normalized_sql, param_names) where:
        - normalized_sql: SQL with all placeholders converted to ?
        - param_names: List of parameter names in order (for named/pyformat), or None for positional
    """
    sql_encoded = sql.encode('utf-8')
    length = len(sql_encoded)
    result = bytearray()
    param_names: List[str] = []
    has_named_params = False
    
    # Cache lookup tables
    is_identifier_start = _IS_IDENTIFIER_START
    is_identifier_char = _IS_IDENTIFIER_CHAR
    is_special = _IS_SPECIAL_CHAR
    
    state = 0  # 0=NORMAL, 1=STRING, 2=ESCAPE, 3=BACKTICK, 4=EOL, 5=COMMENT
    single_quotes = False
    last_char = 0
    i = 0

    while i < length:
        c = sql_encoded[i]
        
        if state == 0:  # NORMAL - most common case, check first
            # Fast path: skip regular characters
            if not is_special[c]:
                result.append(c)
                last_char = c
                i += 1
                continue
            
            # Check for parameter placeholders - inline code for each case
            if c == 63:  # '?' - qmark style (already normalized)
                result.append(c)
                i += 1
                continue
                
            elif c == 37 and last_char != 92:  # '%' not escaped - format/pyformat style
                if i + 1 < length:
                    next_c = sql_encoded[i + 1]
                    if next_c == 115 or next_c == 100:  # 's' or 'd' - format style %s or %d
                        # Inline: replace with ?
                        result.append(63)
                        i += 2
                        last_char = 63
                        continue
                    elif next_c == 40:  # '(' - pyformat style %(name)s
                        # Find closing )s
                        j = i + 2
                        while j < length and sql_encoded[j] != 41:  # ')'
                            j += 1
                        if j + 1 < length and sql_encoded[j + 1] == 115:  # 's'
                            # Inline: replace with ? and track param name
                            result.append(63)
                            param_names.append(sql_encoded[i+2:j].decode('utf-8'))
                            has_named_params = True
                            i += j + 2 - i
                            last_char = 63
                            continue
                            
            elif c == 58 and last_char != 92:  # ':' not escaped - named style :name
                if i + 1 < length:
                    next_c = sql_encoded[i + 1]
                    # Use lookup table for identifier start
                    if is_identifier_start[next_c]:
                        j = i + 1
                        # Use lookup table for identifier continuation
                        while j < length and is_identifier_char[sql_encoded[j]]:
                            j += 1
                        # Inline: replace with ? and track param name
                        result.append(63)
                        param_names.append(sql_encoded[i+1:j].decode('utf-8'))
                        has_named_params = True
                        i += j - i
                        last_char = 63
                        continue
                
            # Not a placeholder, copy character as-is
            result.append(c)
            
            # Check for state transitions
            if c == 39:  # "'"
                state = 1
                single_quotes = True
            elif c == 34:  # '"'
                state = 1
                single_quotes = False
            elif c == 96:  # '`'
                state = 3
            elif c == 42 and last_char == 47:  # '/*'
                if i + 1 < length:
                    next_c = sql_encoded[i + 1]
                    if next_c not in (33, 77):  # not '!' or 'M'
                        state = 5
                else:
                    state = 5
            elif c == 47:  # '/'
                if last_char == 42:  # '*/'
                    state = 0
                elif last_char == 47:  # '//'
                    state = 4
            elif c == 35:  # '#'
                state = 4
            elif c == 45 and last_char == 45:  # '--'
                state = 4

        elif state == 1:  # STRING
            result.append(c)
            if c == 92:  # '\'
                state = 2
            elif (c == 39 and single_quotes) or (c == 34 and not single_quotes):
                state = 0
        
        elif state == 2:  # ESCAPE - rare case, check after common states
            state = 1
            result.append(c)
            last_char = c
            i += 1
            continue

        elif state == 3:  # BACKTICK
            result.append(c)
            if c == 96:
                state = 0

        elif state == 4:  # EOL
            result.append(c)
            if c == 10:  # '\n'
                state = 0

        elif state == 5:  # COMMENT
            result.append(c)
            if last_char == 42 and c == 47:  # '*/'
                state = 0

        last_char = c
        i += 1

    normalized_sql = result.decode('utf-8')
    return normalized_sql, (param_names if has_named_params else None)


class QueryPacket(ClientMessage):
    """
    Query packet for SQL execution
    Use static factory methods to create instances:
    - QueryPacket.from_sql(sql_string) for plain SQL
    - QueryPacket.from_payload(payload_bytes) for pre-formatted payload with parameters
    """
    __slots__ = ('_payload_bytes', '_sql')

    def __init__(self, payload_bytes: bytearray, sql: str = None):
        """
        Initialize COM_QUERY packet with pre-formatted payload
        
        Args:
            payload_bytes: Complete packet payload including header + COM_QUERY + SQL
            sql: Original SQL string (for LOAD LOCAL INFILE validation)
        """
        self._payload_bytes = payload_bytes
        self._sql = sql
    
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
        return QueryPacket(payload, sql)

    
    @staticmethod
    def from_substitute(sql: str, parameters: Any, no_backslash_escapes: bool = False) -> 'QueryPacket':
        """
        Create QueryPacket with parameter substitution.
        
        Parse SQL and substitute parameters in one pass.
        Supports all paramstyles (qmark_compat behavior):
        - ? (qmark)
        - %s, %d (format)
        - %(name)s (pyformat)
        - :name (named)
        
        Args:
            sql: SQL statement string
            parameters: Parameters to substitute (list, tuple, or dict)
            no_backslash_escapes: Whether NO_BACKSLASH_ESCAPES mode is enabled
        
        Returns:
            QueryPacket instance with substituted parameters
        """
        sql_encoded = sql.encode('utf-8')
        length = len(sql_encoded)
        
        # Convert parameters to appropriate format
        if isinstance(parameters, dict):
            params_dict = parameters
            params_list = None
        else:
            params_dict = None
            params_list = list(parameters) if not isinstance(parameters, list) else parameters
        
        # Cache frequently used functions and lookup tables
        _type = type
        converter = PARAM_CONVERT_TBL
        is_identifier_start = _IS_IDENTIFIER_START
        is_identifier_char = _IS_IDENTIFIER_CHAR
        is_special = _IS_SPECIAL_CHAR
        
        # Build result directly - start with header
        result = bytearray(b'\x00\x00\x00\x00\x03')
        
        state = 0  # 0=NORMAL, 1=STRING, 2=ESCAPE, 3=BACKTICK, 4=EOL, 5=COMMENT
        single_quotes = False
        last_char = 0
        last_copy = 0  # Last position we copied to result
        param_idx = 0
        placeholder_count = 0  # Count placeholders for validation
        i = 0
        
        while i < length:
            c = sql_encoded[i]
            
            if state == 0:  # NORMAL - most common case, check first
                # Fast path: skip regular characters (95% of cases)
                if not is_special[c]:
                    last_char = c
                    i += 1
                    continue
                
                # Check for parameter placeholders - inline substitution for each case
                if c == 63:  # '?' - qmark style
                    placeholder_count += 1
                    # Copy SQL before placeholder
                    if i > last_copy:
                        result.extend(sql_encoded[last_copy:i])
                    # Substitute parameter (positional only for ?)
                    if params_list is None:
                        raise ProgrammingError(
                            "Positional placeholder '?' used but parameters provided as dict. "
                            "Use named placeholders like :name or %(name)s instead."
                        )
                    if param_idx >= len(params_list):
                        raise ProgrammingError(
                            f"Parameter count mismatch: SQL has at least {placeholder_count} placeholders, "
                            f"but only {len(params_list)} parameters provided"
                        )
                    param = params_list[param_idx]
                    conv_func = converter.get(_type(param))
                    if conv_func is not None:
                        result.extend(conv_func(param, no_backslash_escapes))
                    else:
                        result.extend(str(param).encode('utf8'))
                    param_idx += 1
                    last_copy = i + 1
                    i += 1
                    continue
                    
                elif c == 37 and last_char != 92:  # '%' not escaped - format/pyformat style
                    if i + 1 < length:
                        next_c = sql_encoded[i + 1]
                        if next_c == 115 or next_c == 100:  # 's' or 'd' - format style %s or %d
                            placeholder_count += 1
                            # Copy SQL before placeholder
                            if i > last_copy:
                                result.extend(sql_encoded[last_copy:i])
                            # Substitute parameter (positional)
                            if params_list is None:
                                raise ProgrammingError(
                                    "Positional placeholder '%s' or '%d' used but parameters provided as dict. "
                                    "Use named placeholders like :name or %(name)s instead."
                                )
                            if param_idx >= len(params_list):
                                raise ProgrammingError(
                                    f"Parameter count mismatch: SQL has at least {placeholder_count} placeholders, "
                                    f"but only {len(params_list)} parameters provided"
                                )
                            param = params_list[param_idx]
                            param_type = _type(param)
                            conv_func = converter.get(param_type)
                            if conv_func is not None:
                                result.extend(conv_func(param, no_backslash_escapes))
                            else:
                                result.extend(str(param).encode('utf8'))
                            param_idx += 1
                            last_copy = i + 2
                            i += 2
                            continue
                        elif next_c == 40:  # '(' - pyformat style %(name)s
                            # Find closing )s
                            j = i + 2
                            while j < length and sql_encoded[j] != 41:  # ')'
                                j += 1
                            if j + 1 < length and sql_encoded[j + 1] == 115:  # 's'
                                placeholder_count += 1
                                param_name = sql_encoded[i+2:j].decode('utf-8')
                                # Copy SQL before placeholder
                                if i > last_copy:
                                    result.extend(sql_encoded[last_copy:i])
                                # Substitute parameter (named)
                                if params_dict is None:
                                    raise ProgrammingError(
                                        f"Named placeholder '%({param_name})s' used but parameters provided as tuple/list. "
                                        "Use positional placeholders like ? or %s instead."
                                    )
                                if param_name in params_dict:
                                    param = params_dict[param_name]
                                    param_type = _type(param)
                                    conv_func = converter.get(param_type)
                                    if conv_func is not None:
                                        result.extend(conv_func(param, no_backslash_escapes))
                                    else:
                                        result.extend(str(param).encode('utf8'))
                                else:
                                    result.extend(NULL_BYTES)
                                last_copy = j + 2
                                i = j + 2
                                continue
                                
                elif c == 58 and last_char != 92:  # ':' not escaped - named style :name
                    if i + 1 < length:
                        next_c = sql_encoded[i + 1]
                        # Use lookup table for identifier start
                        if is_identifier_start[next_c]:
                            j = i + 1
                            # Use lookup table for identifier continuation
                            while j < length and is_identifier_char[sql_encoded[j]]:
                                j += 1
                            placeholder_count += 1
                            param_name = sql_encoded[i+1:j].decode('utf-8')
                            # Copy SQL before placeholder
                            if i > last_copy:
                                result.extend(sql_encoded[last_copy:i])
                            # Substitute parameter (named)
                            if params_dict is None:
                                raise ProgrammingError(
                                    f"Named placeholder ':{param_name}' used but parameters provided as tuple/list. "
                                    "Use positional placeholders like ? or %s instead."
                                )
                            if param_name in params_dict:
                                param = params_dict[param_name]
                                param_type = _type(param)
                                conv_func = converter.get(param_type)
                                if conv_func is not None:
                                    result.extend(conv_func(param, no_backslash_escapes))
                                else:
                                    result.extend(str(param).encode('utf8'))
                            else:
                                result.extend(NULL_BYTES)
                            last_copy = j
                            i = j
                            continue
                    
                elif c == 39:  # "'"
                    state = 1
                    single_quotes = True
                elif c == 34:  # '"'
                    state = 1
                    single_quotes = False
                elif c == 96:  # '`'
                    state = 3
                elif c == 42 and last_char == 47:  # '/*'
                    if i + 1 < length:
                        next_c = sql_encoded[i + 1]
                        if next_c not in (33, 77):  # not '!' or 'M'
                            state = 5
                    else:
                        state = 5
                elif c == 47:  # '/'
                    if last_char == 42:  # '*/'
                        state = 0
                    elif last_char == 47:  # '//'
                        state = 4
                elif c == 35:  # '#'
                    state = 4
                elif c == 45 and last_char == 45:  # '--'
                    state = 4

            elif state == 1:  # STRING
                if c == 92:  # '\'
                    state = 2
                elif (c == 39 and single_quotes) or (c == 34 and not single_quotes):
                    state = 0
            
            elif state == 2:  # ESCAPE - rare case, check after common states
                state = 1
                last_char = c
                i += 1
                continue

            elif state == 3:  # BACKTICK
                if c == 96:
                    state = 0

            elif state == 4:  # EOL
                if c == 10:  # '\n'
                    state = 0

            elif state == 5:  # COMMENT
                if last_char == 42 and c == 47:  # '*/'
                    state = 0

            last_char = c
            i += 1
        
        # Copy remaining SQL
        if last_copy < length:
            result.extend(sql_encoded[last_copy:])
        
        return QueryPacket(result, sql)
        
    def payload(self, context: Context) -> bytearray:
        return self._payload_bytes

    def is_binary(self) -> bool:
        return False

    def type(self) -> str:
        return "COM_QUERY"
    
    def get_sql(self) -> str:
        """Get SQL string for LOAD LOCAL INFILE validation"""
        return self._sql
