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
from typing import Any, Callable, List, Mapping, Sequence, Tuple

from mariadb_shared.constants.INDICATOR import MrdbIndicator
from mariadb_shared.exceptions import NotSupportedError, ProgrammingError

_MISSING: object = object()  # sentinel: distinguishes missing key from explicit None

# numpy is an optional accelerator for float32 VECTOR encoding.
numpy: Any = None
try:
    import numpy  # pyright: ignore[reportMissingImports]
except ImportError:
    pass
HAS_NUMPY = numpy is not None

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

def float2bytes(value: float, no_backslash_escapes: bool = False) -> bytes:
    if repr(value) in ("nan", "inf", "-inf"):
        raise NotSupportedError(f"Float value '{repr(value)}' is not supported.")
    return str(value).encode('ascii')

def decimal2bytes(value: decimal.Decimal, no_backslash_escapes: bool = False) -> bytes:
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

def split_timedelta(val: datetime.timedelta) -> Tuple[bool, int, int, int, int, int]:
    """Break a timedelta into (negative, days, hours, minutes, seconds, microseconds)
    with every component non-negative, hours below 24 and the sign separate:
    the shape the TIME literal and the binary TIME parameter both need.

    timedelta normalises to days that may be negative with seconds and
    microseconds always >= 0, so ``-1 microsecond`` is stored as
    ``(-1 day, 86399 s, 999999 us)`` and the magnitude has to be rebuilt from
    all three fields (int(total_seconds()) truncates the fraction and loses
    precision on large values).
    """
    days = val.days
    seconds = val.seconds
    microseconds = val.microseconds
    negative = days < 0
    if negative:
        total = -(days * 86400 + seconds)
        if microseconds:
            total -= 1
            microseconds = 1000000 - microseconds
    else:
        total = days * 86400 + seconds
    days, remainder = divmod(total, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    return negative, days, hours, minutes, seconds, microseconds


def timedelta_to_bytes(val: datetime.timedelta, no_backslash_escapes: bool = False) -> bytes:
    negative, days, hours, minutes, seconds, microseconds = split_timedelta(val)
    sign = '-' if negative else ''
    return (f"'{sign}{days * 24 + hours}:{minutes:02d}:{seconds:02d}.{microseconds:06d}'"
            .encode('ascii'))

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

def float_array_to_bytes(arr: array.array[float], no_backslash_escapes: bool = False) -> bytes | bytearray:
    """Convert float array to binary representation for VECTOR columns"""
    if len(arr) == 0:
        return b'NULL'
    if HAS_NUMPY:
        float_bytes = numpy.array(arr, numpy.float32).tobytes()
    else:
        float_bytes = arr.tobytes()
    return escape_bytes(float_bytes, no_backslash_escapes)

def tuple_to_bytes(t: tuple, no_backslash_escapes: bool = False) -> bytes: # pyright: ignore[reportUnknownParameterType, reportMissingTypeArgument]
    """Convert tuple to bytes - raises error as tuples are not directly supported"""
    raise NotSupportedError("Tuple parameters are not supported. Use individual values or convert to a supported type.")

def indicator_val(v: MrdbIndicator, no_backslash_escapes: bool = False) -> bytes:
   indicator = v.indicator
   if indicator == 1:
       return NULL_BYTES
   elif indicator == 2:
       return b'DEFAULT'
   else:
       return NULL_BYTES


# Optimized converter functions (avoid lambda overhead)
def _int_to_bytes(v: Any, no_backslash_escapes: bool = False) -> bytes:
    return b'%d' % v

def _bool_to_bytes(v: Any, no_backslash_escapes: bool = False) -> bytes:
    return TRUE_BYTES if v else FALSE_BYTES

def _none_to_bytes(v: Any, no_backslash_escapes: bool = False) -> bytes:
    return NULL_BYTES

def _date_to_bytes(v: Any, no_backslash_escapes: bool = False) -> bytes:
    # Use SQL temporal literal so the server preserves DATE type on `SELECT ?`
    return b"DATE'" + str(v).encode('ascii') + QUOTE_BYTES

def _datetime_to_bytes(v: Any, no_backslash_escapes: bool = False) -> bytes:
    # Use SQL TIMESTAMP literal so the server preserves DATETIME type on `SELECT ?`
    if v.tzinfo is not None:
        v = v.replace(tzinfo=None)
    return b"TIMESTAMP'" + str(v).encode('ascii') + QUOTE_BYTES

def _time_to_bytes(v: Any, no_backslash_escapes: bool = False) -> bytes:
    # Use SQL TIME literal so the server preserves TIME type on `SELECT ?`
    if v.tzinfo is not None:
        v = v.replace(tzinfo=None)
    return b"TIME'" + str(v).encode('ascii') + QUOTE_BYTES

def _ipv4_to_bytes(v: Any, no_backslash_escapes: bool = False) -> bytes:
    return QUOTE_BYTES + str(v).encode('ascii') + QUOTE_BYTES

def _ipv6_to_bytes(v: Any, no_backslash_escapes: bool = False) -> bytes:
    return QUOTE_BYTES + str(v).encode('ascii') + QUOTE_BYTES

def _uuid_to_bytes(v: Any, no_backslash_escapes: bool = False) -> bytes:
    return QUOTE_BYTES + str(v).encode('ascii') + QUOTE_BYTES

# A parameter converter: (value, no_backslash_escapes) -> SQL-safe bytes.
ParamConverter = Callable[[Any, bool], bytes | bytearray]

PARAM_CONVERT_TBL: dict[type[Any], ParamConverter] = {
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

_type_cache: dict[type[Any], ParamConverter | None] = {cls: func for cls, func in PARAM_CONVERT_TBL.items()}

# get cached conversion function
def get_converter(val: Any) -> ParamConverter | None:
    tbl = PARAM_CONVERT_TBL
    t: type[Any] = type(val) # pyright: ignore[reportUnknownVariableType]
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
# SQL tokenizer
# ============================================================================

# One compiled pattern finds, in C, the next thing that matters in a statement:
# either a region to step over (string literal, quoted identifier, comment) or a
# placeholder, reported through the group that matched. Everything else is
# skipped without running Python code per byte. Every alternative starts with a
# literal byte (hence the look-behinds placed after it): that lets the regex
# engine search for that set of bytes instead of trying each alternative at
# each position.
#   group 1: ?            (qmark)
#   group 2: %s / %d      (format)
#   group 3: %(name)s     (pyformat), the name
#   group 4: :name        (named), the name
_TOKEN_RE = re.compile(
    # 'string' / "string": a backslash escapes the next byte; an unterminated
    # literal runs to the end of the statement
    rb"""'[^'\\]*(?:\\.[^'\\]*)*(?:'|\\?\Z)"""
    rb"""|"[^"\\]*(?:\\.[^"\\]*)*(?:"|\\?\Z)"""
    rb"|`[^`]*`?"                         # `identifier`
    rb"|\#[^\n]*"                         # comment to end of line
    # '--' only starts a comment when followed by whitespace or a control
    # character (not in expressions like '2--1'), or at the end of the statement
    rb"|--(?=[\x00-\x20]|\Z)[^\n]*"
    # /* comment */, but not the executable /*! ... */ and /*M ... */ forms,
    # whose content is parsed as SQL. The opening '/*' is consumed before the
    # closing '*/' is searched for, so '/*/' opens a comment (as on the server)
    # instead of closing it on its own '*'
    rb"|/\*(?![!M]).*?(?:\*/|\Z)"
    rb"|\?()"
    # '%' and ':' preceded by a backslash are not placeholders
    rb"|%(?<!\\%)(?:([sd])|\(([^)]*)\)s)"
    rb"|:(?<!\\:)([A-Za-z_][A-Za-z0-9_]*)",
    re.DOTALL)
_tokens = _TOKEN_RE.finditer


# ============================================================================
# substitute_params — shared single-pass SQL parser + parameter substitution
# ============================================================================

def substitute_params(
    sql: str,
    parameters: Mapping[str, Any] | Sequence[Any],
    no_backslash_escapes: bool = False,
) -> list[bytes | bytearray]:
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
                p_type: type[Any] = type(param)  # pyright: ignore[reportUnknownVariableType]
                if p_type is not last_param_type:
                    cached_conv_func = _converter(param)
                    last_param_type = p_type
                if cached_conv_func is not None:
                    converted[i] = cached_conv_func(param, no_backslash_escapes)
                else:
                    converted[i] = escape_str(str(param), no_backslash_escapes)
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

    # Use list for fragments (Faster than bytearray.extend in Python)
    result_list: list[bytes | bytearray] = []
    _append = result_list.append

    # Homogeneous Type Cache - This targets the get_converter bottleneck
    cached_conv_func = None
    last_param_type = None

    last_copy = 0
    param_idx = 0

    for token in _tokens(_sql):
        kind = token.lastindex
        if kind is None:
            continue  # string literal, quoted identifier or comment

        if kind == 1:  # ?
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
            param = params_list[param_idx]
            param_idx += 1
        elif kind == 2:  # %s or %d
            if params_list is None:
                raise ProgrammingError(
                    "Positional placeholder '%s' or '%d' used but parameters provided as dict. "
                    "Use named placeholders like :name or %(name)s instead."
                )
            param = params_list[param_idx]
            param_idx += 1
        else:  # %(name)s or :name
            param_name = token.group(kind).decode('utf-8')
            if kind == 3 and params_dict is None:
                raise ProgrammingError(
                    f"Named placeholder '%({param_name})s' used but parameters provided as tuple/list. "
                    "Use positional placeholders like ? or %s instead."
                )
            param = params_dict.get(param_name)  # type: ignore[union-attr]
            if param is None and params_dict.get(param_name, _MISSING) is _MISSING:  # type: ignore[union-attr]
                raise ProgrammingError(
                    f"Dictionary doesn't contain key '{param_name}'"
                )

        start = token.start()
        if start > last_copy:
            _append(_sql[last_copy:start])
        last_copy = token.end()

        p_type = type(param)  # pyright: ignore[reportUnknownVariableType]
        if p_type is not last_param_type:
            cached_conv_func = _converter(param)
            last_param_type = p_type

        if cached_conv_func is not None:
            _append(cached_conv_func(param, no_backslash_escapes))
        else:
            _append(escape_str(str(param), no_backslash_escapes))

    if last_copy < length:
        _append(_sql[last_copy:])

    return result_list


def normalize_to_qmark(sql: str) -> Tuple[str, List[str] | None]:
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

    result_list: List[bytes] = []
    _append = result_list.append
    param_names: List[str] = []
    last_copy = 0

    for token in _tokens(_sql):
        kind = token.lastindex
        if kind is None or kind == 1:
            continue  # string literal, quoted identifier, comment, or already qmark

        start = token.start()
        if start > last_copy:
            _append(_sql[last_copy:start])
        _append(b'?')
        last_copy = token.end()
        if kind > 2:  # %(name)s or :name
            param_names.append(token.group(kind).decode('utf-8'))

    if not result_list:
        return sql, None  # nothing to convert

    _append(_sql[last_copy:])
    normalized = b''.join(result_list).decode('utf-8')
    return normalized, (param_names or None)
