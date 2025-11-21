# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Field decoder registry for MariaDB protocol

Provides optimized decoder functions for text and binary protocol formats.
"""

import datetime
import decimal
import ipaddress
import uuid
from typing import Any, Optional, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from .socket.payload_parser import PayloadParser
    from ..message.server.column_definition_packet import ColumnDefinitionPacket
    from ..configuration import Configuration

from mariadb_shared.constants import FIELD_TYPE, FIELD_FLAG


# ============================================================================
# Text Protocol Decoders
# ============================================================================

def decode_text_integer(parser: 'PayloadParser', column: 'ColumnDefinitionPacket', config: 'Configuration') -> Optional[int]:
    """Decode integer types from text protocol"""
    val = parser.read_length_encoded_string(encoding='ascii')
    return int(val) if val is not None else None


def decode_text_float(parser: 'PayloadParser', column: 'ColumnDefinitionPacket', config: 'Configuration') -> Optional[float]:
    """Decode float/double from text protocol"""
    val = parser.read_length_encoded_string()
    return float(val) if val is not None else None


def decode_text_decimal(parser: 'PayloadParser', column: 'ColumnDefinitionPacket', config: 'Configuration') -> Optional[decimal.Decimal]:
    """Decode decimal from text protocol"""
    val = parser.read_length_encoded_string(encoding='ascii')
    return decimal.Decimal(val) if val is not None else None


def decode_text_date(parser: 'PayloadParser', column: 'ColumnDefinitionPacket', config: 'Configuration') -> Optional[datetime.date]:
    """Decode DATE from text protocol"""
    val = parser.read_length_encoded_string(encoding='ascii')
    if val is None:
        return None
    try:
        year, month, day = map(int, val.split('-'))
        return datetime.date(year, month, day)
    except (ValueError, AttributeError):
        return None


def decode_text_time(parser: 'PayloadParser', column: 'ColumnDefinitionPacket', config: 'Configuration') -> Optional[datetime.timedelta]:
    """Decode TIME from text protocol"""
    val = parser.read_length_encoded_string(encoding='ascii')
    if val is None:
        return None
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
        return -td if is_negative else td
    except (ValueError, AttributeError):
        return val  # Fallback to string if parsing fails


def decode_text_datetime(parser: 'PayloadParser', column: 'ColumnDefinitionPacket', config: 'Configuration') -> Optional[datetime.datetime]:
    """Decode DATETIME/TIMESTAMP from text protocol"""
    val = parser.read_length_encoded_string(encoding='ascii')
    if val is None:
        return None
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
        
        return datetime.datetime(year, month, day, hours, minutes, seconds, microseconds)
    except (ValueError, AttributeError):
        return val  # Fallback to string if parsing fails


def decode_text_string(parser: 'PayloadParser', column: 'ColumnDefinitionPacket', config: 'Configuration') -> Optional[Any]:
    """Decode string/varchar/text from text protocol"""
    # Check for special types
    if column.ext_type_format == 'json':
        return parser.read_length_encoded_string()
    
    if column.ext_type_name == 'inet6' or column.ext_type_name == 'inet4':
        value = parser.read_length_encoded_string(encoding='ascii')
        if config.native_object and value is not None:
            return ipaddress.ip_address(value)
        return value
    
    if column.ext_type_name == 'uuid':
        value = parser.read_length_encoded_string(encoding='ascii')
        if config.native_object and value is not None:
            return uuid.UUID(value)
        return value
    
    # Check if BINARY (charset 63)
    if column.character_set == 63:
        # Binary data - read as bytes
        return parser.read_length_encoded_bytes()
    else:
        # Text data - read as string
        return parser.read_length_encoded_string()


def decode_text_null(parser: 'PayloadParser', column: 'ColumnDefinitionPacket', config: 'Configuration') -> None:
    """Decode NULL from text protocol"""
    parser.read_length_encoded_string()
    return None


# ============================================================================
# Binary Protocol Decoders
# ============================================================================

def decode_binary_tiny_signed(parser: 'PayloadParser', column: 'ColumnDefinitionPacket', config: 'Configuration') -> int:
    """Decode signed TINYINT from binary protocol"""
    value = parser.read_byte()
    if value > 127:
        value -= 256
    return value


def decode_binary_tiny_unsigned(parser: 'PayloadParser', column: 'ColumnDefinitionPacket', config: 'Configuration') -> int:
    """Decode unsigned TINYINT from binary protocol"""
    return parser.read_byte()


def decode_binary_short_signed(parser: 'PayloadParser', column: 'ColumnDefinitionPacket', config: 'Configuration') -> int:
    """Decode signed SMALLINT/YEAR from binary protocol"""
    return parser.read_int16()


def decode_binary_short_unsigned(parser: 'PayloadParser', column: 'ColumnDefinitionPacket', config: 'Configuration') -> int:
    """Decode unsigned SMALLINT/YEAR from binary protocol"""
    return parser.read_uint16()


def decode_binary_long_signed(parser: 'PayloadParser', column: 'ColumnDefinitionPacket', config: 'Configuration') -> int:
    """Decode signed INT/MEDIUMINT from binary protocol"""
    return parser.read_int32()


def decode_binary_long_unsigned(parser: 'PayloadParser', column: 'ColumnDefinitionPacket', config: 'Configuration') -> int:
    """Decode unsigned INT/MEDIUMINT from binary protocol"""
    return parser.read_uint32()


def decode_binary_longlong_signed(parser: 'PayloadParser', column: 'ColumnDefinitionPacket', config: 'Configuration') -> int:
    """Decode signed BIGINT from binary protocol"""
    return parser.read_int64()


def decode_binary_longlong_unsigned(parser: 'PayloadParser', column: 'ColumnDefinitionPacket', config: 'Configuration') -> int:
    """Decode unsigned BIGINT from binary protocol"""
    return parser.read_uint64()


def decode_binary_float(parser: 'PayloadParser', column: 'ColumnDefinitionPacket', config: 'Configuration') -> float:
    """Decode FLOAT from binary protocol"""
    return parser.read_float()


def decode_binary_double(parser: 'PayloadParser', column: 'ColumnDefinitionPacket', config: 'Configuration') -> float:
    """Decode DOUBLE from binary protocol"""
    return parser.read_double()


def decode_binary_decimal(parser: 'PayloadParser', column: 'ColumnDefinitionPacket', config: 'Configuration') -> Optional[decimal.Decimal]:
    """Decode DECIMAL from binary protocol"""
    val = parser.read_length_encoded_string()
    return decimal.Decimal(val) if val is not None else None


def decode_binary_date(parser: 'PayloadParser', column: 'ColumnDefinitionPacket', config: 'Configuration') -> Optional[datetime.date]:
    """Decode DATE from binary protocol"""
    length_byte = parser.read_byte()
    if length_byte < 4:
        return None
    
    year = parser.read_uint16()
    month = parser.read_byte()
    day = parser.read_byte()
    
    try:
        return datetime.date(year, month, day)
    except ValueError:
        return None


def decode_binary_time(parser: 'PayloadParser', column: 'ColumnDefinitionPacket', config: 'Configuration') -> Optional[datetime.timedelta]:
    """Decode TIME from binary protocol"""
    length_byte = parser.read_byte()
    if length_byte < 8:
        return None
    
    negative = parser.read_byte()
    days = parser.read_uint32()
    hours = parser.read_byte()
    minutes = parser.read_byte()
    seconds = parser.read_byte()
    microseconds = 0
    
    if length_byte == 12:
        microseconds = parser.read_uint32()
    
    # Calculate total hours
    total_hours = days * 24 + hours
    
    try:
        # Use timedelta for TIME values >= 24 hours
        value = datetime.timedelta(hours=total_hours, minutes=minutes, seconds=seconds, microseconds=microseconds)
        return -value if negative else value
    except ValueError:
        return None


def decode_binary_datetime(parser: 'PayloadParser', column: 'ColumnDefinitionPacket', config: 'Configuration') -> Optional[datetime.datetime]:
    """Decode DATETIME/TIMESTAMP from binary protocol"""
    length_byte = parser.read_byte()
    
    if length_byte < 4:
        return None
    
    year = parser.read_uint16()
    month = parser.read_byte()
    day = parser.read_byte()
    
    hours = minutes = seconds = microseconds = 0
    
    if length_byte >= 7:
        hours = parser.read_byte()
        minutes = parser.read_byte()
        seconds = parser.read_byte()
    
    if length_byte == 11:
        microseconds = parser.read_uint32()
    
    try:
        return datetime.datetime(year, month, day, hours, minutes, seconds, microseconds)
    except ValueError:
        return None


def decode_binary_string(parser: 'PayloadParser', column: 'ColumnDefinitionPacket', config: 'Configuration') -> Optional[Any]:
    """Decode string/varchar/text from binary protocol"""
    # Check for special types
    if column.ext_type_name == 'inet6' or column.ext_type_name == 'inet4':
        value = parser.read_length_encoded_string()
        if config.native_object and value is not None:
            return ipaddress.ip_address(value)
        return value
    
    if column.ext_type_name == 'uuid':
        value = parser.read_length_encoded_string()
        if config.native_object and value is not None:
            return uuid.UUID(value)
        return value
    
    # Check if BINARY (charset 63)
    if column.character_set == 63:
        # Binary string - return bytes
        return parser.read_length_encoded_bytes()
    else:
        # Text string - return string
        return parser.read_length_encoded_string()


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
