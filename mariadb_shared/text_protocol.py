# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Shared text-protocol parameter substitution for both mariadb and mariadb_c.

This module provides:
- Parameter conversion functions (Python values -> SQL-safe bytes)
- Pre-computed lookup tables for SQL parsing
- substitute_params(): single-pass SQL parser that discovers placeholder style,
  validates parameters, and substitutes values inline.
"""

from __future__ import annotations

import array
import datetime
import decimal
import ipaddress
import re
import uuid
from typing import Any, List, Optional, Tuple

from mariadb_shared.constants.INDICATOR import MrdbIndicator
from mariadb_shared.exceptions import NotSupportedError, ProgrammingError

_MISSING: object = object()  # sentinel: distinguishes missing key from explicit None

try:
    import numpy
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

# ============================================================================
# Constants
# ============================================================================

NULL_BYTES: bytes = b"NULL"
TRUE_BYTES: bytes = b"1"
FALSE_BYTES: bytes = b"0"
QUOTE_BYTES: bytes = b"'"
BINARY_QUOTE_PREFIX: bytes = b"_binary'"


# ============================================================================
# Parameter Conversion Functions
# ============================================================================

def float2bytes(value: float, ctx: Any = None) -> bytes:
    if repr(value) in ("nan", "inf", "-inf"):
        raise NotSupportedError(f"Float value '{repr(value)}' is not supported.")
    return str(value).encode('ascii')

def decimal2bytes(value: decimal.Decimal, ctx: Any = None) -> bytes:
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

def timedelta_to_bytes(val: datetime.timedelta, ctx: Any = None) -> bytes:
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

def escape_bytes(b: bytes, no_backslash_escapes: bool = False) -> bytearray:
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
    result = bytearray(len(escaped) + 9)
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

def indicator_val(v: Any, ctx: Any = None) -> bytes:
   indicator = v.indicator
   if indicator == 1:
       return NULL_BYTES
   elif indicator == 2:
       return b'DEFAULT'
   else:
       return NULL_BYTES


# Optimized converter functions (avoid lambda overhead)
def _int_to_bytes(v: Any, ctx: Any = None) -> bytes:
    return b'%d' % v

def _bool_to_bytes(v: Any, ctx: Any = None) -> bytes:
    return TRUE_BYTES if v else FALSE_BYTES

def _none_to_bytes(v: Any, ctx: Any = None) -> bytes:
    return NULL_BYTES

def _date_to_bytes(v: Any, ctx: Any = None) -> bytes:
    # Use SQL temporal literal so the server preserves DATE type on `SELECT ?`
    return b"DATE'" + str(v).encode('ascii') + QUOTE_BYTES

def _datetime_to_bytes(v: Any, ctx: Any = None) -> bytes:
    # Use SQL TIMESTAMP literal so the server preserves DATETIME type on `SELECT ?`
    return b"TIMESTAMP'" + str(v).encode('ascii') + QUOTE_BYTES

def _time_to_bytes(v: Any, ctx: Any = None) -> bytes:
    # Use SQL TIME literal so the server preserves TIME type on `SELECT ?`
    return b"TIME'" + str(v).encode('ascii') + QUOTE_BYTES

def _ipv4_to_bytes(v: Any, ctx: Any = None) -> bytes:
    return QUOTE_BYTES + str(v).encode('ascii') + QUOTE_BYTES

def _ipv6_to_bytes(v: Any, ctx: Any = None) -> bytes:
    return QUOTE_BYTES + str(v).encode('ascii') + QUOTE_BYTES

def _uuid_to_bytes(v: Any, ctx: Any = None) -> bytes:
    return QUOTE_BYTES + str(v).encode('ascii') + QUOTE_BYTES

PARAM_CONVERT_TBL = {
  int: _int_to_bytes,
  float: float2bytes,
  str: escape_str,
  bytes: escape_bytes,
  bytearray: escape_bytes,
  decimal.Decimal: decimal2bytes,
  datetime.date: _date_to_bytes,
  datetime.datetime: _datetime_to_bytes,
  datetime.time: _time_to_bytes,
  datetime.timedelta: timedelta_to_bytes,
  type(None): _none_to_bytes,
  bool: _bool_to_bytes,
  MrdbIndicator: indicator_val,
  ipaddress.IPv4Address: _ipv4_to_bytes,
  ipaddress.IPv6Address: _ipv6_to_bytes,
  uuid.UUID: _uuid_to_bytes,
  array.array: float_array_to_bytes,
  tuple: tuple_to_bytes,
}

_type_cache: dict[type, Any] = {cls: func for cls, func in PARAM_CONVERT_TBL.items()}

# get cached conversion function
def get_converter(val: Any) -> Any:
    tbl = PARAM_CONVERT_TBL  # local reference
    t = type(val)
    if t in _type_cache:
        return _type_cache[t]

    for base in t.__mro__:
        if base in tbl:
            conv_func = tbl[base]
            _type_cache[t] = conv_func
            return conv_func

    _type_cache[t] = None
    return None


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
for _i in range(256):
    # A-Z (65-90), a-z (97-122)
    if (65 <= _i <= 90) or (97 <= _i <= 122):
        _IS_ALPHA[_i] = 1
        _IS_IDENTIFIER_START[_i] = 1
        _IS_IDENTIFIER_CHAR[_i] = 1
    # 0-9 (48-57)
    if 48 <= _i <= 57:
        _IS_DIGIT[_i] = 1
        _IS_IDENTIFIER_CHAR[_i] = 1
    # _ (95)
    if _i == 95:
        _IS_IDENTIFIER_START[_i] = 1
        _IS_IDENTIFIER_CHAR[_i] = 1

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
for _char_code in _SPECIAL_CHARS:
    _IS_SPECIAL_CHAR[_char_code] = 1

# Cleanup module-level loop variables
del _i, _char_code


# ============================================================================
# substitute_params — shared single-pass SQL parser + parameter substitution
# ============================================================================

def substitute_params(sql: str, parameters: Any, no_backslash_escapes: bool = False) -> list[bytes]:
    """
    Parse SQL, discover placeholders, and substitute parameters in a single pass.

    Supports: ? (qmark), %s/%d (format), %(name)s (pyformat), :name (named).
    Handles string literals, comments, backtick identifiers, and escape sequences.

    Args:
        sql: SQL statement with placeholders
        parameters: dict for named/pyformat, or list/tuple for positional
        no_backslash_escapes: True when server has NO_BACKSLASH_ESCAPES

    Returns:
        List of bytes fragments.  Caller joins them (and may prepend a
        protocol header before joining).
    """
    _sql = sql.encode('utf-8')
    length = len(_sql)

    if isinstance(parameters, dict):
        params_dict = parameters
        params_list = None
        params_len = 0
    else:
        params_dict = None
        params_list = list(parameters) if not isinstance(parameters, list) else parameters
        params_len = len(params_list)

    # Fast path: positional params with no quotes/comments in SQL
    # bytes.split(b'?') is safe when there are no string literals or comments
    # that could contain literal '?' characters
    if params_list is not None and params_len >= 2 and 63 in _sql:
        # Check if SQL is "simple" - no quotes, backticks, or comment markers
        if not (39 in _sql or 34 in _sql or 96 in _sql or 35 in _sql
                or b'--' in _sql or b'/*' in _sql):
            parts = _sql.split(b'?')
            n_placeholders = len(parts) - 1
            if n_placeholders != params_len:
                raise ProgrammingError(
                    f"Parameter count mismatch: SQL has {n_placeholders} placeholders, "
                    f"but {params_len} parameters provided"
                )
            # Batch-convert parameters
            _converter = get_converter
            cached_conv_func = None
            last_param_type = None
            converted: list[Any] = [None] * n_placeholders
            for i in range(n_placeholders):
                param = params_list[i]
                p_type = type(param)
                if p_type is not last_param_type:
                    cached_conv_func = _converter(param)
                    last_param_type = p_type
                if cached_conv_func is not None:
                    converted[i] = cached_conv_func(param, no_backslash_escapes)
                else:
                    converted[i] = str(param).encode('utf8')
            # Interleave SQL parts and converted params (pre-allocated)
            interleaved: list[Any] = [None] * (2 * n_placeholders + 1)
            j = 0
            for i in range(n_placeholders):
                interleaved[j] = parts[i]
                interleaved[j + 1] = converted[i]
                j += 2
            interleaved[j] = parts[n_placeholders]
            return interleaved

    # Localize for speed
    _converter = get_converter
    is_identifier_start = _IS_IDENTIFIER_START
    is_identifier_char = _IS_IDENTIFIER_CHAR
    is_special = _IS_SPECIAL_CHAR

    # Use list for fragments (Faster than bytearray.extend in Python)
    result_list: list[bytes] = []
    _append = result_list.append

    # Homogeneous Type Cache - This targets the get_converter bottleneck
    cached_conv_func = None
    last_param_type = None

    state = 0  # 0=NORMAL, 1=STRING, 2=ESCAPE, 3=BACKTICK, 4=EOL, 5=COMMENT
    single_quotes = False
    last_char = 0
    last_copy = 0
    param_idx = 0
    i = 0

    while i < length:
        c = _sql[i]

        if state == 0:  # NORMAL
            if not is_special[c]:
                last_char = c
                i += 1
                continue

            # Check '?'
            if c == 63:
                if params_list is None:
                    raise ProgrammingError(
                        "Positional placeholder '?' used but parameters provided as dict. "
                        "Use named placeholders like :name or %(name)s instead."
                    )
                if param_idx >= params_len:
                    raise ProgrammingError(
                        f"Parameter count mismatch: SQL has at least {param_idx + 1} placeholders, "
                        f"but only {params_len} parameters provided"
                    )
                if i > last_copy:
                    _append(_sql[last_copy:i])
                param = params_list[param_idx]
                p_type = type(param)
                if p_type is not last_param_type:
                    cached_conv_func = _converter(param)
                    last_param_type = p_type

                if cached_conv_func is not None:
                    _append(cached_conv_func(param, no_backslash_escapes))
                else:
                    _append(str(param).encode('utf8'))

                param_idx += 1
                last_copy = i + 1
                last_char = c
                i += 1
                continue

            # Check '%'
            elif c == 37 and last_char != 92:
                if i + 1 < length:
                    next_c = _sql[i + 1]
                    if next_c == 115 or next_c == 100:  # %s or %d
                        if i > last_copy:
                            _append(_sql[last_copy:i])

                        param = params_list[param_idx]  # type: ignore[index]
                        p_type = type(param)
                        if p_type is not last_param_type:
                            cached_conv_func = _converter(param)
                            last_param_type = p_type

                        if cached_conv_func is not None:
                            _append(cached_conv_func(param, no_backslash_escapes))
                        else:
                            _append(str(param).encode('utf8'))

                        param_idx += 1
                        last_copy = i + 2
                        i += 2
                        last_char = next_c
                        continue
                    elif next_c == 40:  # %(name)s
                        j = i + 2
                        while j < length and _sql[j] != 41:
                            j += 1
                        if j + 1 < length and _sql[j + 1] == 115:
                            param_name = _sql[i+2:j].decode('utf-8')
                            if i > last_copy:
                                _append(_sql[last_copy:i])
                            if params_dict is None:
                                raise ProgrammingError(
                                    f"Named placeholder '%({param_name})s' used but parameters provided as tuple/list. "
                                    "Use positional placeholders like ? or %s instead."
                                )
                            param = params_dict.get(param_name)
                            if param is not None:
                                p_type = type(param)
                                if p_type is not last_param_type:
                                    cached_conv_func = _converter(param)
                                    last_param_type = p_type

                                if cached_conv_func is not None:
                                    _append(cached_conv_func(param, no_backslash_escapes))
                                else:
                                    _append(str(param).encode('utf8'))
                            else:
                                if params_dict.get(param_name, _MISSING) is _MISSING:
                                    raise ProgrammingError(
                                        f"Dictionary doesn't contain key '{param_name}'"
                                    )
                                _append(b'NULL')
                            last_copy = j + 2
                            i = j + 2
                            last_char = 115
                            continue

            # Check ':'
            elif c == 58 and last_char != 92:
                if i + 1 < length:
                    next_c = _sql[i + 1]
                    if is_identifier_start[next_c]:
                        j = i + 1
                        while j < length and is_identifier_char[_sql[j]]:
                            j += 1
                        param_name = _sql[i+1:j].decode('utf-8')
                        if i > last_copy:
                            _append(_sql[last_copy:i])

                        param = params_dict.get(param_name)  # type: ignore[union-attr]
                        if param is not None:
                            p_type = type(param)
                            if p_type is not last_param_type:
                                cached_conv_func = _converter(param)
                                last_param_type = p_type
                            if cached_conv_func is not None:
                                _append(cached_conv_func(param, no_backslash_escapes))
                            else:
                                _append(str(param).encode('utf8'))
                        else:
                            if params_dict.get(param_name, _MISSING) is _MISSING:  # type: ignore[union-attr]
                                raise ProgrammingError(
                                    f"Dictionary doesn't contain key '{param_name}'"
                                )
                            _append(b'NULL')
                        last_copy = j
                        i = j
                        last_char = _sql[j-1] if j > i else c
                        continue

            # Context Transitions
            elif c == 39:  # "'"
                state = 1
                single_quotes = True
            elif c == 34:  # '"'
                state = 1
                single_quotes = False
            elif c == 96:  # '`'
                state = 3
            elif c == 42 and last_char == 47:  # '/*'
                if i + 1 < length and _sql[i + 1] not in (33, 77):
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

        elif state == 2:  # ESCAPE
            state = 1

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

    if last_copy < length:
        _append(_sql[last_copy:])

    return result_list


def normalize_to_qmark(sql: str) -> Tuple[str, Optional[List[str]]]:
    """
    Convert SQL with any placeholder style to qmark (?) style.

    Supports:
    - ? (qmark) — no conversion needed
    - %s, %d (format) — convert to ?
    - %(name)s (pyformat) — convert to ? and return parameter name list
    - :name (named) — convert to ? and return parameter name list

    Returns:
        (normalized_sql, param_names) where param_names is a list of names
        for named/pyformat styles, or None for positional styles.
    """
    _sql = sql.encode('utf-8')
    length = len(_sql)

    result_list: List[bytes] = []
    _append = result_list.append
    param_names: List[str] = []
    has_named_params = False

    is_identifier_start = _IS_IDENTIFIER_START
    is_identifier_char = _IS_IDENTIFIER_CHAR
    is_special = _IS_SPECIAL_CHAR

    state = 0  # 0=NORMAL, 1=STRING, 2=ESCAPE, 3=BACKTICK, 4=EOL, 5=COMMENT
    single_quotes = False
    last_char = 0
    last_copy = 0
    i = 0

    while i < length:
        c = _sql[i]

        if state == 0:
            if not is_special[c]:
                last_char = c
                i += 1
                continue

            if c == 63:  # '?' — already qmark
                last_char = c
                i += 1
                continue

            elif c == 37 and last_char != 92:  # '%' not escaped
                if i + 1 < length:
                    next_c = _sql[i + 1]
                    if next_c == 115 or next_c == 100:  # %s or %d
                        if i > last_copy:
                            _append(_sql[last_copy:i])
                        _append(b'?')
                        i += 2
                        last_copy = i
                        last_char = 63
                        continue
                    elif next_c == 40:  # %(name)s
                        j = i + 2
                        while j < length and _sql[j] != 41:
                            j += 1
                        if j + 1 < length and _sql[j + 1] == 115:
                            if i > last_copy:
                                _append(_sql[last_copy:i])
                            _append(b'?')
                            param_names.append(_sql[i + 2:j].decode('utf-8'))
                            has_named_params = True
                            i = j + 2
                            last_copy = i
                            last_char = 63
                            continue

            elif c == 58 and last_char != 92:  # ':' not escaped — :name
                if i + 1 < length and is_identifier_start[_sql[i + 1]]:
                    j = i + 1
                    while j < length and is_identifier_char[_sql[j]]:
                        j += 1
                    if i > last_copy:
                        _append(_sql[last_copy:i])
                    _append(b'?')
                    param_names.append(_sql[i + 1:j].decode('utf-8'))
                    has_named_params = True
                    i = j
                    last_copy = i
                    last_char = 63
                    continue

            if c == 39:
                state = 1
                single_quotes = True
            elif c == 34:
                state = 1
                single_quotes = False
            elif c == 96:
                state = 3
            elif c == 42 and last_char == 47:
                if i + 1 < length and _sql[i + 1] not in (33, 77):
                    state = 5
                elif i + 1 >= length:
                    state = 5
            elif c == 47:
                if last_char == 42:
                    state = 0
                elif last_char == 47:
                    state = 4
            elif c == 35:
                state = 4
            elif c == 45 and last_char == 45:
                state = 4

        elif state == 1:
            if c == 92:
                state = 2
            elif (c == 39 and single_quotes) or (c == 34 and not single_quotes):
                state = 0

        elif state == 2:
            state = 1
            last_char = c
            i += 1
            continue

        elif state == 3:
            if c == 96:
                state = 0

        elif state == 4:
            if c == 10:
                state = 0

        elif state == 5:
            if last_char == 42 and c == 47:
                state = 0

        last_char = c
        i += 1

    if last_copy < length:
        _append(_sql[last_copy:])

    normalized = b''.join(result_list).decode('utf-8')
    return normalized, (param_names if has_named_params else None)
