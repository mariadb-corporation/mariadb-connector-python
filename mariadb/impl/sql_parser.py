#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
SQL parser for handling placeholders in SQL statements.

This module provides proper parsing of SQL statements to identify placeholders
while correctly handling:
- String literals (single and double quotes)
- Comments (/* */, --, #, //)
- Backtick identifiers
- Escape sequences

Based on mariadb-connector-nodejs implementation.
"""

import array
import datetime
import decimal
import ipaddress
import uuid
import re
from typing import List, Tuple, Optional, Any

try:
    import numpy
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

from mariadb_shared.constants.INDICATOR import MrdbIndicator
from ..exceptions import NotSupportedError

# Constants
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
# SQL Parser and Parameter Substitution
# ============================================================================

def substitute(sql: str, parameters: Any, no_backslash_escapes: bool = False) -> Tuple[bytearray, List[int]]:
    """
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
        Tuple of (payload_bytes, param_positions) where:
        - payload_bytes: Complete COM_QUERY payload (4-byte length + COM_QUERY + formatted SQL)
        - param_positions: Empty list (always empty since parameters are substituted)
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
    
    # Cache frequently used functions
    _type = type
    converter = PARAM_CONVERT_TBL
    
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
        
        if state == 2:  # ESCAPE
            state = 1
            last_char = c
            i += 1
            continue

        if state == 0:  # NORMAL
            # Check for parameter placeholders
            placeholder_start = -1
            placeholder_end = -1
            param_name = None
            
            if c == 63:  # '?' - qmark style
                placeholder_start = i
                placeholder_end = i + 1
                
            elif c == 37 and last_char != 92:  # '%' not escaped - format/pyformat style
                if i + 1 < length:
                    next_c = sql_encoded[i + 1]
                    if next_c in (115, 100):  # 's' or 'd' - format style %s or %d
                        placeholder_start = i
                        placeholder_end = i + 2
                    elif next_c == 40:  # '(' - pyformat style %(name)s
                        # Find closing )s
                        j = i + 2
                        while j < length and sql_encoded[j] != 41:  # ')'
                            j += 1
                        if j + 1 < length and sql_encoded[j + 1] == 115:  # 's'
                            placeholder_start = i
                            placeholder_end = j + 2
                            param_name = sql_encoded[i+2:j].decode('utf-8')
                            
            elif c == 58 and last_char != 92:  # ':' not escaped - named style :name
                if i + 1 < length:
                    next_c = sql_encoded[i + 1]
                    # Identifier starts with letter or underscore
                    if (65 <= next_c <= 90) or (97 <= next_c <= 122) or next_c == 95:  # A-Z, a-z, _
                        j = i + 1
                        # Continue while alphanumeric or underscore
                        while j < length:
                            ch = sql_encoded[j]
                            if not ((48 <= ch <= 57) or (65 <= ch <= 90) or (97 <= ch <= 122) or ch == 95):
                                break
                            j += 1
                        placeholder_start = i
                        placeholder_end = j
                        param_name = sql_encoded[i+1:j].decode('utf-8')
            
            # If we found a placeholder, substitute it
            if placeholder_start >= 0:
                placeholder_count += 1
                
                # Copy SQL before placeholder
                if placeholder_start > last_copy:
                    result.extend(sql_encoded[last_copy:placeholder_start])
                
                # Get parameter value and convert
                if params_dict is not None:
                    # Named parameters
                    if param_name and param_name in params_dict:
                        param = params_dict[param_name]
                        param_type = _type(param)
                        conv_func = converter.get(param_type)
                        if conv_func is not None:
                            result.extend(conv_func(param, no_backslash_escapes))
                        else:
                            result.extend(str(param).encode('utf8'))
                    else:
                        result.extend(NULL_BYTES)
                else:
                    # Positional parameters - validate count
                    if param_idx >= len(params_list):
                        from ..exceptions import ProgrammingError
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
                
                # Update position
                last_copy = placeholder_end
                i = placeholder_end - 1  # Will be incremented at end of loop
                
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
    
    return result, []  # Empty param_positions since parameters are substituted


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
    
    state = 0  # 0=NORMAL, 1=STRING, 2=ESCAPE, 3=BACKTICK, 4=EOL, 5=COMMENT
    single_quotes = False
    last_char = 0
    i = 0

    while i < length:
        c = sql_encoded[i]
        
        if state == 2:  # ESCAPE
            state = 1
            result.append(c)
            last_char = c
            i += 1
            continue

        if state == 0:  # NORMAL
            # Check for parameter placeholders
            placeholder_found = False
            param_name = None
            skip_chars = 0
            
            if c == 63:  # '?' - qmark style (already normalized)
                result.append(c)
                i += 1
                continue
                
            elif c == 37 and last_char != 92:  # '%' not escaped - format/pyformat style
                if i + 1 < length:
                    next_c = sql_encoded[i + 1]
                    if next_c in (115, 100):  # 's' or 'd' - format style %s or %d
                        placeholder_found = True
                        skip_chars = 2
                    elif next_c == 40:  # '(' - pyformat style %(name)s
                        # Find closing )s
                        j = i + 2
                        while j < length and sql_encoded[j] != 41:  # ')'
                            j += 1
                        if j + 1 < length and sql_encoded[j + 1] == 115:  # 's'
                            placeholder_found = True
                            has_named_params = True
                            param_name = sql_encoded[i+2:j].decode('utf-8')
                            skip_chars = j + 2 - i
                            
            elif c == 58 and last_char != 92:  # ':' not escaped - named style :name
                if i + 1 < length:
                    next_c = sql_encoded[i + 1]
                    # Identifier starts with letter or underscore
                    if (65 <= next_c <= 90) or (97 <= next_c <= 122) or next_c == 95:  # A-Z, a-z, _
                        j = i + 1
                        # Continue while alphanumeric or underscore
                        while j < length:
                            ch = sql_encoded[j]
                            if not ((48 <= ch <= 57) or (65 <= ch <= 90) or (97 <= ch <= 122) or ch == 95):
                                break
                            j += 1
                        placeholder_found = True
                        has_named_params = True
                        param_name = sql_encoded[i+1:j].decode('utf-8')
                        skip_chars = j - i
            
            # If we found a placeholder, replace with ?
            if placeholder_found:
                result.append(63)  # '?'
                if param_name:
                    param_names.append(param_name)
                i += skip_chars
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
