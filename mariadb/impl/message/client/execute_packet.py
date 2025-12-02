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

# Type dispatch tables for parameter handling
PARAM_TYPE_TBL = {}
PARAM_WRITE_TBL = {}

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

    def payload(self, context: Context) -> bytearray:
        stream = PayloadWriter()
        stream.write_byte(self.COM_STMT_EXECUTE)
        stream.write_bytes(_STRUCT_I.pack(self.statement_id) if self.statement_id is not None else b'\xFF\xFF\xFF\xFF')
        stream.write_byte(0x00) # Write flags  
        stream.write_uint32(1) # Write iteration count - always 1

        parameters = self.parameters
        if parameters:
            # Cache locals
            num_params = len(parameters)
            null_bitmap_length = (num_params + 7) >> 3  # Bit shift instead of division
            null_bitmap = bytearray(null_bitmap_length)
            
            # Cache type() to avoid global lookup
            _type = type
            type_tbl = PARAM_TYPE_TBL
            write_tbl = PARAM_WRITE_TBL
            
            # Build null bitmap
            for i in range(num_params):
                param = parameters[i]
                is_null = (param is None or 
                          (isinstance(param, array.array) and param.typecode == 'f' and len(param) == 0) or
                          isinstance(param, MrdbIndicator))
                if is_null:
                    null_bitmap[i >> 3] |= (1 << (i & 7))  # Bit operations instead of division/modulo
            
            stream.write_bytes(null_bitmap) # Write NULL bitmap
            stream.write_byte(0x01) # new params bound flag
            
            # Write parameter types (2 bytes per parameter)
            for param in parameters:
                param_type = _type(param)
                type_func = type_tbl.get(param_type)
                if type_func is not None:
                    field_type, unsigned = type_func(param)
                else:
                    field_type, unsigned = self._get_parameter_type(param)
                stream.write_bytes(_STRUCT_BB.pack(field_type, unsigned))
            
            # Write parameter values
            for param in parameters:
                if param is not None:
                    param_type = _type(param)
                    write_func = write_tbl.get(param_type)
                    if write_func is not None:
                        write_func(self, stream, param)
                    else:
                        # Fallback for unknown types - convert to string
                        stream.write_length_encoded_string(str(param))
        
        return stream.get_payload()

    def _get_parameter_type(self, param: Any) -> tuple[int, int]:
        """
        Get MySQL field type and unsigned flag for parameter
        
        Args:
            param: Parameter value
            
        Returns:
            Tuple of (field_type, unsigned_flag)
        """
        if param is None:
            return FIELD_TYPE.NULL, 0
        elif isinstance(param, bool):
            return FIELD_TYPE.TINY, 0
        elif isinstance(param, int):
            if -128 <= param <= 127:
                return FIELD_TYPE.TINY, 0
            elif -32768 <= param <= 32767:
                return FIELD_TYPE.SHORT, 0
            elif -2147483648 <= param <= 2147483647:
                return FIELD_TYPE.LONG, 0
            else:
                return FIELD_TYPE.LONGLONG, 0
        elif isinstance(param, float):
            return FIELD_TYPE.DOUBLE, 0
        elif isinstance(param, decimal.Decimal):
            return FIELD_TYPE.NEWDECIMAL, 0
        elif isinstance(param, str):
            return FIELD_TYPE.VAR_STRING, 0
        elif isinstance(param, (bytes, bytearray)):
            return FIELD_TYPE.BLOB, 0
        elif isinstance(param, datetime.datetime):
            return FIELD_TYPE.DATETIME, 0
        elif isinstance(param, datetime.date):
            return FIELD_TYPE.DATE, 0
        elif isinstance(param, datetime.time):
            return FIELD_TYPE.TIME, 0
        elif isinstance(param, datetime.timedelta):
            return FIELD_TYPE.TIME, 0
        elif isinstance(param, array.array) and param.typecode == 'f':
            # Float array for VECTOR columns
            return FIELD_TYPE.BLOB, 0
        elif isinstance(param, MrdbIndicator):
            # Handle MariaDB indicator values
            if param.indicator == 1:  # NULL
                return FIELD_TYPE.NULL, 0
            elif param.indicator == 2:  # DEFAULT - treat as string
                return FIELD_TYPE.NULL, 0
            else:
                return FIELD_TYPE.NULL, 0
        else:
            # Default to string
            return FIELD_TYPE.VAR_STRING, 0
    

    def is_binary(self) -> bool:
        return True

    def type(self) -> str:
        return "COM_STMT_EXECUTE"


# Optimized type detection functions
def _get_type_bool(param):
    return FIELD_TYPE.TINY, 0

def _get_type_int(param):
    if -128 <= param <= 127:
        return FIELD_TYPE.TINY, 0
    elif -32768 <= param <= 32767:
        return FIELD_TYPE.SHORT, 0
    elif -2147483648 <= param <= 2147483647:
        return FIELD_TYPE.LONG, 0
    else:
        return FIELD_TYPE.LONGLONG, 0

def _get_type_float(param):
    return FIELD_TYPE.DOUBLE, 0

def _get_type_decimal(param):
    return FIELD_TYPE.NEWDECIMAL, 0

def _get_type_str(param):
    return FIELD_TYPE.VAR_STRING, 0

def _get_type_bytes(param):
    return FIELD_TYPE.BLOB, 0

def _get_type_datetime(param):
    return FIELD_TYPE.DATETIME, 0

def _get_type_date(param):
    return FIELD_TYPE.DATE, 0

def _get_type_time(param):
    return FIELD_TYPE.TIME, 0

def _get_type_timedelta(param):
    return FIELD_TYPE.TIME, 0

def _get_type_none(param):
    return FIELD_TYPE.NULL, 0

# Optimized write functions
def _write_bool(self, stream, param):
    stream.write_byte(1 if param else 0)

def _write_int(self, stream, param):
    # Optimized integer writing with pre-compiled struct formats
    if -128 <= param <= 127:
        stream.write_bytes(_STRUCT_b.pack(param))
    elif -32768 <= param <= 32767:
        stream.write_bytes(_STRUCT_h.pack(param))
    elif -2147483648 <= param <= 2147483647:
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
    if param.indicator == 1:  # NULL
        return FIELD_TYPE.NULL, 0
    elif param.indicator == 2:  # DEFAULT
        return FIELD_TYPE.NULL, 0
    else:
        return FIELD_TYPE.NULL, 0

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