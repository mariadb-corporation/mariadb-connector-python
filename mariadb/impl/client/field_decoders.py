# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Field decoder registry for MariaDB protocol

Provides optimized decoder functions for text and binary protocol formats.
All decoders work directly with memoryview and return (value, new_position).
"""

import datetime
import decimal
import ipaddress
import uuid
import struct
from typing import Any, Optional, Callable, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from ..message.server.column_definition_packet import ColumnDefinitionPacket
    from ..configuration import Configuration

from mariadb_shared.constants import FIELD_TYPE, FIELD_FLAG


# ============================================================================
# Helper Functions for Reading from memoryview
# ============================================================================

def read_length_encoded_int(data: memoryview, pos: int) -> Tuple[Optional[int], int]:
    """Read length-encoded integer from memoryview"""
    if pos >= len(data):
        return None, pos
    
    first_byte = data[pos]
    
    if first_byte < 0xFB:
        return first_byte, pos + 1
    elif first_byte == 0xFB:
        # NULL
        return None, pos + 1
    elif first_byte == 0xFC:
        # 2-byte integer
        value = data[pos + 1] | (data[pos + 2] << 8)
        return value, pos + 3
    elif first_byte == 0xFD:
        # 3-byte integer
        value = data[pos + 1] | (data[pos + 2] << 8) | (data[pos + 3] << 16)
        return value, pos + 4
    elif first_byte == 0xFE:
        # 8-byte integer
        value = struct.unpack_from('<Q', data, pos + 1)[0]
        return value, pos + 9
    else:
        return None, pos + 1


def read_length_encoded_string(data: memoryview, pos: int, encoding: str = 'utf-8') -> Tuple[Optional[str], int]:
    """Read length-encoded string from memoryview"""
    length, pos = read_length_encoded_int(data, pos)
    if length is None:
        return None, pos
    
    if length == 0:
        return '', pos
    
    try:
        return data[pos:pos + length].tobytes().decode(encoding), pos + length
    except UnicodeDecodeError:
        return data[pos:pos + length].tobytes().decode(encoding, errors='replace'), pos + length


def read_length_encoded_bytes(data: memoryview, pos: int) -> Tuple[Optional[bytes], int]:
    """Read length-encoded bytes from memoryview"""
    length, pos = read_length_encoded_int(data, pos)
    if length is None:
        return None, pos
    
    if length == 0:
        return b'', pos
    
    return data[pos:pos + length].tobytes(), pos + length


# ============================================================================
# Text Protocol Decoders
# ============================================================================

def decode_text_integer(data: memoryview, pos: int, column: 'ColumnDefinitionPacket', config: 'Configuration') -> Tuple[Optional[int], int]:
    """Decode integer types from text protocol"""
    length, pos = read_length_encoded_int(data, pos)
    if length is None:
        return None, pos

    return int(data[pos:pos + length].tobytes().decode('ascii')), pos + length


def decode_text_float(data: memoryview, pos: int, column: 'ColumnDefinitionPacket', config: 'Configuration') -> Tuple[Optional[float], int]:
    """Decode float/double from text protocol"""
    val, pos = read_length_encoded_string(data, pos)
    return (float(val) if val is not None else None, pos)


def decode_text_decimal(data: memoryview, pos: int, column: 'ColumnDefinitionPacket', config: 'Configuration') -> Tuple[Optional[decimal.Decimal], int]:
    """Decode decimal from text protocol"""
    val, pos = read_length_encoded_string(data, pos, encoding='ascii')
    return (decimal.Decimal(val) if val is not None else None, pos)


def decode_text_date(data: memoryview, pos: int, column: 'ColumnDefinitionPacket', config: 'Configuration') -> Tuple[Optional[datetime.date], int]:
    """Decode DATE from text protocol"""
    val, pos = read_length_encoded_string(data, pos, encoding='ascii')
    if val is None:
        return None, pos
    try:
        year, month, day = map(int, val.split('-'))
        return datetime.date(year, month, day), pos
    except (ValueError, AttributeError):
        return None, pos


def decode_text_time(data: memoryview, pos: int, column: 'ColumnDefinitionPacket', config: 'Configuration') -> Tuple[Optional[datetime.timedelta], int]:
    """Decode TIME from text protocol"""
    val, pos = read_length_encoded_string(data, pos, encoding='ascii')
    if val is None:
        return None, pos
    try:
        # Handle TIME format: HH:MM:SS[.ffffff] or HHH:MM:SS[.ffffff] (can be > 24 hours)
        # Can also be negative: -HH:MM:SS[.ffffff]
        is_negative = val.startswith('-')
        if is_negative:
            val = val[1:]
        
        parts = val.split(':')
        hours = int(parts[0])
        minutes = int(parts[1])
        
        # Handle fractional seconds
        seconds_parts = parts[2].split('.')
        seconds = int(seconds_parts[0])
        microseconds = 0
        
        if len(seconds_parts) > 1:
            # Pad or truncate to 6 digits for microseconds
            frac_str = seconds_parts[1].ljust(6, '0')[:6]
            microseconds = int(frac_str)
        
        td = datetime.timedelta(hours=hours, minutes=minutes, seconds=seconds, microseconds=microseconds)
        return (-td if is_negative else td, pos)
    except (ValueError, AttributeError):
        return val, pos  # Fallback to string if parsing fails


def decode_text_datetime(data: memoryview, pos: int, column: 'ColumnDefinitionPacket', config: 'Configuration') -> Tuple[Optional[datetime.datetime], int]:
    """Decode DATETIME/TIMESTAMP from text protocol"""
    val, pos = read_length_encoded_string(data, pos, encoding='ascii')
    if val is None:
        return None, pos
    try:
        # Handle DATETIME format: YYYY-MM-DD HH:MM:SS[.ffffff]
        date_part, time_part = val.split(' ', 1)
        year, month, day = map(int, date_part.split('-'))
        
        time_parts = time_part.split(':')
        hours = int(time_parts[0])
        minutes = int(time_parts[1])
        
        # Handle fractional seconds
        seconds_parts = time_parts[2].split('.')
        seconds = int(seconds_parts[0])
        microseconds = 0
        
        if len(seconds_parts) > 1:
            # Pad or truncate to 6 digits for microseconds
            frac_str = seconds_parts[1].ljust(6, '0')[:6]
            microseconds = int(frac_str)
        
        return datetime.datetime(year, month, day, hours, minutes, seconds, microseconds), pos
    except (ValueError, AttributeError):
        return val, pos  # Fallback to string if parsing fails


def decode_text_string(data: memoryview, pos: int, column: 'ColumnDefinitionPacket', config: 'Configuration') -> Tuple[Optional[Any], int]:
    """Decode string/varchar/text from text protocol"""
    # Check for special types
    if column.ext_type_format == 'json':
        return read_length_encoded_string(data, pos)
    
    if column.ext_type_name == 'inet6' or column.ext_type_name == 'inet4':
        value, pos = read_length_encoded_string(data, pos, encoding='ascii')
        if config.native_object and value is not None:
            return ipaddress.ip_address(value), pos
        return value, pos
    
    if column.ext_type_name == 'uuid':
        value, pos = read_length_encoded_string(data, pos, encoding='ascii')
        if config.native_object and value is not None:
            return uuid.UUID(value), pos
        return value, pos
    
    # Check if BINARY (charset 63)
    if column.character_set == 63:
        # Binary data - read as bytes
        return read_length_encoded_bytes(data, pos)
    else:
        # Text data - read as string
        return read_length_encoded_string(data, pos)


def decode_text_null(data: memoryview, pos: int, column: 'ColumnDefinitionPacket', config: 'Configuration') -> Tuple[None, int]:
    """Decode NULL from text protocol"""
    _, pos = read_length_encoded_string(data, pos)
    return None, pos


# ============================================================================
# Binary Protocol Decoders
# ============================================================================

def decode_binary_tiny_signed(data: memoryview, pos: int, column: 'ColumnDefinitionPacket', config: 'Configuration') -> Tuple[int, int]:
    """Decode signed TINYINT from binary protocol"""
    value = data[pos]
    if value > 127:
        value -= 256
    return value, pos + 1


def decode_binary_tiny_unsigned(data: memoryview, pos: int, column: 'ColumnDefinitionPacket', config: 'Configuration') -> Tuple[int, int]:
    """Decode unsigned TINYINT from binary protocol"""
    return data[pos], pos + 1


def decode_binary_short_signed(data: memoryview, pos: int, column: 'ColumnDefinitionPacket', config: 'Configuration') -> Tuple[int, int]:
    """Decode signed SMALLINT/YEAR from binary protocol"""
    value = struct.unpack_from('<h', data, pos)[0]
    return value, pos + 2


def decode_binary_short_unsigned(data: memoryview, pos: int, column: 'ColumnDefinitionPacket', config: 'Configuration') -> Tuple[int, int]:
    """Decode unsigned SMALLINT/YEAR from binary protocol"""
    value = struct.unpack_from('<H', data, pos)[0]
    return value, pos + 2


def decode_binary_long_signed(data: memoryview, pos: int, column: 'ColumnDefinitionPacket', config: 'Configuration') -> Tuple[int, int]:
    """Decode signed INT/MEDIUMINT from binary protocol"""
    value = struct.unpack_from('<i', data, pos)[0]
    return value, pos + 4


def decode_binary_long_unsigned(data: memoryview, pos: int, column: 'ColumnDefinitionPacket', config: 'Configuration') -> Tuple[int, int]:
    """Decode unsigned INT/MEDIUMINT from binary protocol"""
    value = struct.unpack_from('<I', data, pos)[0]
    return value, pos + 4


def decode_binary_longlong_signed(data: memoryview, pos: int, column: 'ColumnDefinitionPacket', config: 'Configuration') -> Tuple[int, int]:
    """Decode signed BIGINT from binary protocol"""
    value = struct.unpack_from('<q', data, pos)[0]
    return value, pos + 8


def decode_binary_longlong_unsigned(data: memoryview, pos: int, column: 'ColumnDefinitionPacket', config: 'Configuration') -> Tuple[int, int]:
    """Decode unsigned BIGINT from binary protocol"""
    value = struct.unpack_from('<Q', data, pos)[0]
    return value, pos + 8


def decode_binary_float(data: memoryview, pos: int, column: 'ColumnDefinitionPacket', config: 'Configuration') -> Tuple[float, int]:
    """Decode FLOAT from binary protocol"""
    value = struct.unpack_from('<f', data, pos)[0]
    return value, pos + 4


def decode_binary_double(data: memoryview, pos: int, column: 'ColumnDefinitionPacket', config: 'Configuration') -> Tuple[float, int]:
    """Decode DOUBLE from binary protocol"""
    value = struct.unpack_from('<d', data, pos)[0]
    return value, pos + 8


def decode_binary_decimal(data: memoryview, pos: int, column: 'ColumnDefinitionPacket', config: 'Configuration') -> Tuple[Optional[decimal.Decimal], int]:
    """Decode DECIMAL from binary protocol"""
    val, pos = read_length_encoded_string(data, pos)
    return (decimal.Decimal(val) if val is not None else None, pos)


def decode_binary_date(data: memoryview, pos: int, column: 'ColumnDefinitionPacket', config: 'Configuration') -> Tuple[Optional[datetime.date], int]:
    """Decode DATE from binary protocol"""
    length_byte = data[pos]
    pos += 1
    
    if length_byte < 4:
        return None, pos
    
    # Unpack year (2 bytes) + month (1 byte) + day (1 byte) in one call
    year, month, day = struct.unpack_from('<HBB', data, pos)
    pos += 4
    
    try:
        return datetime.date(year, month, day), pos
    except ValueError:
        return None, pos


def decode_binary_time(data: memoryview, pos: int, column: 'ColumnDefinitionPacket', config: 'Configuration') -> Tuple[Optional[datetime.timedelta], int]:
    """Decode TIME from binary protocol"""
    length_byte = data[pos]
    pos += 1
    
    if length_byte < 8:
        return None, pos
    
    if length_byte == 12:
        # Unpack all fields at once: negative (1) + days (4) + hours (1) + minutes (1) + seconds (1) + microseconds (4)
        negative, days, hours, minutes, seconds, microseconds = struct.unpack_from('<BIBBBI', data, pos)
        pos += 12
    else:
        # Unpack without microseconds: negative (1) + days (4) + hours (1) + minutes (1) + seconds (1)
        negative, days, hours, minutes, seconds = struct.unpack_from('<BIBBB', data, pos)
        microseconds = 0
        pos += 8
    
    # Calculate total hours
    total_hours = days * 24 + hours
    
    try:
        # Use timedelta for TIME values >= 24 hours
        value = datetime.timedelta(hours=total_hours, minutes=minutes, seconds=seconds, microseconds=microseconds)
        return (-value if negative else value, pos)
    except ValueError:
        return None, pos


def decode_binary_datetime(data: memoryview, pos: int, column: 'ColumnDefinitionPacket', config: 'Configuration') -> Tuple[Optional[datetime.datetime], int]:
    """Decode DATETIME/TIMESTAMP from binary protocol"""
    length_byte = data[pos]
    pos += 1
    
    if length_byte < 4:
        return None, pos
    
    if length_byte == 11:
        # Unpack all fields: year (2) + month (1) + day (1) + hours (1) + minutes (1) + seconds (1) + microseconds (4)
        year, month, day, hours, minutes, seconds, microseconds = struct.unpack_from('<HBBBBBI', data, pos)
        pos += 11
    elif length_byte >= 7:
        # Unpack date + time without microseconds: year (2) + month (1) + day (1) + hours (1) + minutes (1) + seconds (1)
        year, month, day, hours, minutes, seconds = struct.unpack_from('<HBBBBB', data, pos)
        microseconds = 0
        pos += 7
    else:
        # Only date: year (2) + month (1) + day (1)
        year, month, day = struct.unpack_from('<HBB', data, pos)
        hours = minutes = seconds = microseconds = 0
        pos += 4
    
    try:
        return datetime.datetime(year, month, day, hours, minutes, seconds, microseconds), pos
    except ValueError:
        return None, pos


def decode_binary_string(data: memoryview, pos: int, column: 'ColumnDefinitionPacket', config: 'Configuration') -> Tuple[Optional[Any], int]:
    """Decode string/varchar/text from binary protocol"""
    # Check for special types
    if column.ext_type_name == 'inet6' or column.ext_type_name == 'inet4':
        value, pos = read_length_encoded_string(data, pos)
        if config.native_object and value is not None:
            return ipaddress.ip_address(value), pos
        return value, pos
    
    if column.ext_type_name == 'uuid':
        value, pos = read_length_encoded_string(data, pos)
        if config.native_object and value is not None:
            return uuid.UUID(value), pos
        return value, pos
    
    # Check if BINARY (charset 63)
    if column.character_set == 63:
        # Binary string - return bytes
        return read_length_encoded_bytes(data, pos)
    else:
        # Text string - return string
        return read_length_encoded_string(data, pos)


# ============================================================================
# Decoder Registry
# ============================================================================

# Text protocol decoders (signed/unsigned doesn't matter for text protocol)
TEXT_DECODERS: dict[int, Callable] = {
    FIELD_TYPE.TINY: decode_text_integer,
    FIELD_TYPE.SHORT: decode_text_integer,
    FIELD_TYPE.LONG: decode_text_integer,
    FIELD_TYPE.LONGLONG: decode_text_integer,
    FIELD_TYPE.INT24: decode_text_integer,
    FIELD_TYPE.YEAR: decode_text_integer,
    FIELD_TYPE.FLOAT: decode_text_float,
    FIELD_TYPE.DOUBLE: decode_text_float,
    FIELD_TYPE.DECIMAL: decode_text_decimal,
    FIELD_TYPE.NEWDECIMAL: decode_text_decimal,
    FIELD_TYPE.DATE: decode_text_date,
    FIELD_TYPE.NEWDATE: decode_text_date,
    FIELD_TYPE.TIME: decode_text_time,
    FIELD_TYPE.DATETIME: decode_text_datetime,
    FIELD_TYPE.TIMESTAMP: decode_text_datetime,
    FIELD_TYPE.JSON: decode_text_string,
    FIELD_TYPE.NULL: decode_text_null,
}

# Binary protocol decoders - SIGNED integers
BINARY_SIGNED_DECODERS: dict[int, Callable] = {
    FIELD_TYPE.TINY: decode_binary_tiny_signed,
    FIELD_TYPE.SHORT: decode_binary_short_signed,
    FIELD_TYPE.LONG: decode_binary_long_signed,
    FIELD_TYPE.LONGLONG: decode_binary_longlong_signed,
    FIELD_TYPE.INT24: decode_binary_long_signed,
    FIELD_TYPE.YEAR: decode_binary_short_signed,
    FIELD_TYPE.FLOAT: decode_binary_float,
    FIELD_TYPE.DOUBLE: decode_binary_double,
    FIELD_TYPE.DECIMAL: decode_binary_decimal,
    FIELD_TYPE.NEWDECIMAL: decode_binary_decimal,
    FIELD_TYPE.DATE: decode_binary_date,
    FIELD_TYPE.NEWDATE: decode_binary_date,
    FIELD_TYPE.TIME: decode_binary_time,
    FIELD_TYPE.DATETIME: decode_binary_datetime,
    FIELD_TYPE.TIMESTAMP: decode_binary_datetime,
    FIELD_TYPE.JSON: decode_binary_string,
}

# Binary protocol decoders - UNSIGNED integers
BINARY_UNSIGNED_DECODERS: dict[int, Callable] = {
    FIELD_TYPE.TINY: decode_binary_tiny_unsigned,
    FIELD_TYPE.SHORT: decode_binary_short_unsigned,
    FIELD_TYPE.LONG: decode_binary_long_unsigned,
    FIELD_TYPE.LONGLONG: decode_binary_longlong_unsigned,
    FIELD_TYPE.INT24: decode_binary_long_unsigned,
    FIELD_TYPE.YEAR: decode_binary_short_unsigned,
    FIELD_TYPE.FLOAT: decode_binary_float,
    FIELD_TYPE.DOUBLE: decode_binary_double,
    FIELD_TYPE.DECIMAL: decode_binary_decimal,
    FIELD_TYPE.NEWDECIMAL: decode_binary_decimal,
    FIELD_TYPE.DATE: decode_binary_date,
    FIELD_TYPE.NEWDATE: decode_binary_date,
    FIELD_TYPE.TIME: decode_binary_time,
    FIELD_TYPE.DATETIME: decode_binary_datetime,
    FIELD_TYPE.TIMESTAMP: decode_binary_datetime,
    FIELD_TYPE.JSON: decode_binary_string,
}


def get_decoder(column_type: int, is_binary: bool, is_unsigned: bool = False) -> Callable:
    """
    Get decoder function for a given column type, protocol, and signedness
    
    Args:
        column_type: FIELD_TYPE constant
        is_binary: True for binary protocol, False for text protocol
        is_unsigned: True for unsigned integers (only relevant for binary protocol)
    
    Returns:
        Decoder function
    """
    if is_binary:
        registry = BINARY_UNSIGNED_DECODERS if is_unsigned else BINARY_SIGNED_DECODERS
        return registry.get(column_type, decode_binary_string)
    else:
        return TEXT_DECODERS.get(column_type, decode_text_string)
