# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

import array
import datetime
import decimal
import struct
from typing import Any, List, Optional, Union as UnionType

# Pre-compiled struct formats for performance
_STRUCT_H = struct.Struct('<H')  # unsigned short (2 bytes) for year
_STRUCT_I = struct.Struct('<I')  # unsigned int (4 bytes) for microseconds/days
_STRUCT_b = struct.Struct('<b')  # signed byte for tiny int
_STRUCT_h = struct.Struct('<h')  # signed short for small int
_STRUCT_i = struct.Struct('<i')  # signed int for int
_STRUCT_q = struct.Struct('<q')  # signed long long for bigint
_STRUCT_d = struct.Struct('<d')  # double for float
_STRUCT_BB = struct.Struct('<BB')  # two unsigned bytes for type info

# Composite struct formats for datetime/date/time (pack multiple fields at once)
_STRUCT_DATETIME_WITH_MICRO = struct.Struct('<BBBBBBBI')  # length + year(H) + 5 bytes + microsecond(I)
_STRUCT_DATETIME_NO_MICRO = struct.Struct('<BHBBBBB')    # length + year(H) + 5 bytes
_STRUCT_DATE = struct.Struct('<BHBB')                     # length + year(H) + month + day
_STRUCT_TIME_WITH_MICRO = struct.Struct('<BBBIBBBI')     # length + negative + days(I) + 3 bytes + microsecond(I)
_STRUCT_TIME_NO_MICRO = struct.Struct('<BBIBBB')         # length + negative + days(I) + 3 bytes

try:
    import numpy
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
from typing import TYPE_CHECKING

from ...client.context import Context
from mariadb_shared.constants import FIELD_TYPE
from mariadb_shared.constants.INDICATOR import MrdbIndicator
from ..client_message import ClientMessage
from ..payload_writer import PayloadWriter
from ....exceptions import NotSupportedError

class ExecutePacket(ClientMessage):
    """
    Execute packet for prepared statement execution (COM_STMT_EXECUTE)
    
    See: https://mariadb.com/kb/en/com_stmt_execute/
    """
    __slots__ = ('statement_id', 'parameters', 'sql')
    
    COM_STMT_EXECUTE = 0x17
    
    def __init__(self, statement_id: int, parameters: Optional[List[Any]] = None, sql: str = ""):
        """Initialize COM_STMT_EXECUTE packet with statement ID and parameters"""
        self.statement_id = statement_id
        self.parameters = parameters or []
        self.sql = sql

    def payload(self, context: Context, writer: PayloadWriter) -> bytearray:
        writer.reset()
        stream = writer
        stream.write_byte(self.COM_STMT_EXECUTE)
        stream.write_bytes(_STRUCT_I.pack(self.statement_id) if self.statement_id is not None else b'\xFF\xFF\xFF\xFF')
        stream.write_byte(0x00) # Write flags  
        stream.write_uint32(1) # Write iteration count - always 1

        parameters = self.parameters
        if parameters:
            num_params = len(parameters)
            null_bitmap_length = (num_params + 7) >> 3
            
            # Combined buffer: null_bitmap + flag (1 byte) + type_buffer
            combined_length = null_bitmap_length + 1 + (num_params * 2)
            combined_buffer = bytearray(combined_length)
            
            # Set flag byte at position null_bitmap_length
            combined_buffer[null_bitmap_length] = 0x01
            
            # Cache lookups
            _type = type
            type_tbl = PARAM_TYPE_TBL
            write_tbl = PARAM_WRITE_TBL
            
            # Type buffer starts after null_bitmap + flag
            type_offset = null_bitmap_length + 1
            stream.write_bytes(combined_buffer)
            # Single loop: build null bitmap, types, and write parameter values
            for i in range(num_params):
                param = parameters[i]
                
                # Check null
                if (param is None or 
                          (isinstance(param, array.array) and param.typecode == 'f' and len(param) == 0) or
                          isinstance(param, MrdbIndicator)):
                    combined_buffer[i >> 3] |= (1 << (i & 7))
                else:
                    # Get type
                    param_type = _type(param)
                    type_func = type_tbl.get(param_type)
                    if type_func is not None:
                        field_type = type_func(param)
                    else:
                        field_type = self._get_parameter_type(param)
                    
                    # Write type to combined buffer (unsigned flag already 0 from bytearray init)
                    combined_buffer[type_offset + i * 2] = field_type
                    
                    # Write parameter value immediately
                    write_func = write_tbl.get(param_type)
                    if write_func is not None:
                        write_func(self, stream, param)
                    else:
                        stream.write_length_encoded_string(str(param))
            
            # Get payload and insert combined buffer at position 4
            payload = stream.get_payload()
            payload[14:14 + combined_length] = combined_buffer
        else:
            payload = stream.get_payload()
        
        return payload

    def _get_parameter_type(self, param: Any) -> int:
        """
        Get MySQL field type for parameter
        
        Args:
            param: Parameter value
            
        Returns:
            field_type (unsigned flag is always 0)
        """
        if param is None:
            return FIELD_TYPE.NULL
        elif isinstance(param, bool):
            return FIELD_TYPE.TINY
        elif isinstance(param, int):
            if -128 <= param <= 127:
                return FIELD_TYPE.TINY
            elif -32768 <= param <= 32767:
                return FIELD_TYPE.SHORT
            elif -2147483648 <= param <= 2147483647:
                return FIELD_TYPE.LONG
            else:
                return FIELD_TYPE.LONGLONG
        elif isinstance(param, float):
            return FIELD_TYPE.DOUBLE
        elif isinstance(param, decimal.Decimal):
            return FIELD_TYPE.NEWDECIMAL
        elif isinstance(param, str):
            return FIELD_TYPE.VAR_STRING
        elif isinstance(param, (bytes, bytearray)):
            return FIELD_TYPE.BLOB
        elif isinstance(param, datetime.datetime):
            return FIELD_TYPE.DATETIME
        elif isinstance(param, datetime.date):
            return FIELD_TYPE.DATE
        elif isinstance(param, datetime.time):
            return FIELD_TYPE.TIME
        elif isinstance(param, datetime.timedelta):
            return FIELD_TYPE.TIME
        elif isinstance(param, array.array) and param.typecode == 'f':
            # Float array for VECTOR columns
            return FIELD_TYPE.BLOB
        elif isinstance(param, MrdbIndicator):
            # Handle MariaDB indicator values
            return FIELD_TYPE.NULL
        else:
            # Default to string
            return FIELD_TYPE.VAR_STRING
    

    def is_binary(self) -> bool:
        return True

    def type(self) -> str:
        return "COM_STMT_EXECUTE"


# Optimized type detection functions
def _get_type_bool(param):
    return FIELD_TYPE.TINY

def _get_type_int(param):
    # Use bit_length for faster type detection (avoids 4 comparisons)
    if param == 0:
        return FIELD_TYPE.TINY
    bits = param.bit_length() + (1 if param < 0 else 0)
    if bits <= 7:
        return FIELD_TYPE.TINY
    elif bits <= 15:
        return FIELD_TYPE.SHORT
    elif bits <= 31:
        return FIELD_TYPE.LONG
    else:
        return FIELD_TYPE.LONGLONG

def _get_type_float(param):
    return FIELD_TYPE.DOUBLE

def _get_type_decimal(param):
    return FIELD_TYPE.NEWDECIMAL

def _get_type_str(param):
    return FIELD_TYPE.VAR_STRING

def _get_type_bytes(param):
    return FIELD_TYPE.BLOB

def _get_type_datetime(param):
    return FIELD_TYPE.DATETIME

def _get_type_date(param):
    return FIELD_TYPE.DATE

def _get_type_time(param):
    return FIELD_TYPE.TIME

def _get_type_timedelta(param):
    return FIELD_TYPE.TIME

def _get_type_none(param):
    return FIELD_TYPE.NULL

# Optimized write functions
def _write_bool(self, stream, param):
    stream.write_byte(1 if param else 0)

def _write_int(self, stream, param):
    # Use bit_length for faster size detection
    if param == 0:
        stream.write_bytes(_STRUCT_b.pack(0))
        return
    bits = param.bit_length() + (1 if param < 0 else 0)
    if bits <= 7:
        stream.write_bytes(_STRUCT_b.pack(param))
    elif bits <= 15:
        stream.write_bytes(_STRUCT_h.pack(param))
    elif bits <= 31:
        stream.write_bytes(_STRUCT_i.pack(param))
    else:
        stream.write_bytes(_STRUCT_q.pack(param))

def _write_float(self, stream, param):
    if repr(param) in ("nan", "inf", "-inf"):
        raise NotSupportedError(f"Float value '{repr(param)}' is not supported.")
    stream.write_bytes(_STRUCT_d.pack(param))

def _write_decimal(self, stream, param):
    if param.__str__() in ("NaN", "sNaN", "Infinity", "-Infinity"):
        raise NotSupportedError(f"Decimal value '{param.__str__()}' is not supported.")
    stream.write_length_encoded_string(str(param))

def _write_str(self, stream, param):
    stream.write_length_encoded_string(param)

def _write_bytes(self, stream, param):
    stream.write_length_encoded_bytes(param)

def _write_datetime(self, stream, param):
    """Write datetime in MySQL binary format"""
    if param.microsecond:
        # 11 bytes: length(1) + year(2) + month(1) + day(1) + hour(1) + minute(1) + second(1) + microsecond(4)
        stream.write_bytes(_STRUCT_DATETIME_WITH_MICRO.pack(
            11, param.year, param.month, param.day, 
            param.hour, param.minute, param.second, param.microsecond
        ))
    else:
        # 7 bytes: length(1) + year(2) + month(1) + day(1) + hour(1) + minute(1) + second(1)
        stream.write_bytes(_STRUCT_DATETIME_NO_MICRO.pack(
            7, param.year, param.month, param.day,
            param.hour, param.minute, param.second
        ))

def _write_date(self, stream, param):
    """Write date in MySQL binary format"""
    # 4 bytes: length(1) + year(2) + month(1) + day(1)
    stream.write_bytes(_STRUCT_DATE.pack(4, param.year, param.month, param.day))

def _write_time(self, stream, param):
    """Write time in MySQL binary format"""
    if param.microsecond:
        # 12 bytes: length(1) + negative(1) + days(4) + hour(1) + minute(1) + second(1) + microsecond(4)
        stream.write_bytes(_STRUCT_TIME_WITH_MICRO.pack(
            12, 0, 0, param.hour, param.minute, param.second, param.microsecond
        ))
    else:
        # 8 bytes: length(1) + negative(1) + days(4) + hour(1) + minute(1) + second(1)
        stream.write_bytes(_STRUCT_TIME_NO_MICRO.pack(
            8, 0, 0, param.hour, param.minute, param.second
        ))

def _write_timedelta(self, stream, param):
    """Write timedelta as time in MySQL binary format"""
    total_seconds = int(param.total_seconds())
    negative = total_seconds < 0
    total_seconds = abs(total_seconds)
    
    days = total_seconds // 86400
    remaining_seconds = total_seconds % 86400
    hours = remaining_seconds // 3600
    minutes = (remaining_seconds % 3600) // 60
    seconds = remaining_seconds % 60
    microseconds = param.microseconds
    
    if microseconds:
        # 12 bytes: length(1) + negative(1) + days(4) + hour(1) + minute(1) + second(1) + microsecond(4)
        stream.write_bytes(_STRUCT_TIME_WITH_MICRO.pack(
            12, 1 if negative else 0, days, hours, minutes, seconds, microseconds
        ))
    else:
        # 8 bytes: length(1) + negative(1) + days(4) + hour(1) + minute(1) + second(1)
        stream.write_bytes(_STRUCT_TIME_NO_MICRO.pack(
            8, 1 if negative else 0, days, hours, minutes, seconds
        ))

def _write_array(self, stream, param):
    if len(param) == 0:
        return
    if HAS_NUMPY:
        float_bytes = numpy.array(param, numpy.float32).tobytes()
    else:
        float_bytes = param.tobytes()
    stream.write_length_encoded_bytes(float_bytes)

def _write_indicator(self, stream, param):
    """Handle MariaDB indicator values"""
    # Indicators 1 (NULL), 2 (DEFAULT), 3 (IGNORE), 4 (IGNORE_ROW) are handled at higher level
    # NULL is already in the null bitmap, others are skipped
    return

def _get_type_indicator(param):
    """Get type for MrdbIndicator"""
    return FIELD_TYPE.NULL

# Populate lookup tables
PARAM_TYPE_TBL = {
    bool: _get_type_bool,
    int: _get_type_int,
    float: _get_type_float,
    decimal.Decimal: _get_type_decimal,
    str: _get_type_str,
    bytes: _get_type_bytes,
    bytearray: _get_type_bytes,
    datetime.datetime: _get_type_datetime,
    datetime.date: _get_type_date,
    datetime.time: _get_type_time,
    datetime.timedelta: _get_type_timedelta,
    type(None): _get_type_none,
    MrdbIndicator: _get_type_indicator,
}

PARAM_WRITE_TBL = {
    bool: _write_bool,
    int: _write_int,
    float: _write_float,
    decimal.Decimal: _write_decimal,
    str: _write_str,
    bytes: _write_bytes,
    bytearray: _write_bytes,
    datetime.datetime: _write_datetime,
    datetime.date: _write_date,
    datetime.time: _write_time,
    datetime.timedelta: _write_timedelta,
    array.array: _write_array,
    MrdbIndicator: _write_indicator,
}