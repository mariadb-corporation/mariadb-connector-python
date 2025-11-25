# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

import array
import datetime
import decimal
import struct
from typing import Any, List, Optional, Union as UnionType

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
from ..payload_stream import PayloadStream
from ....exceptions import NotSupportedError
if TYPE_CHECKING:
    from ...client.socket.write_stream import BaseWriteStream
class ExecutePacket(ClientMessage):
    """
    Execute packet for prepared statement execution (COM_STMT_EXECUTE)
    
    See: https://mariadb.com/kb/en/com_stmt_execute/
    """
    
    COM_STMT_EXECUTE = 0x17
    
    def __init__(self, statement_id: int, parameters: Optional[List[Any]] = None, sql: str = ""):
        """Initialize COM_STMT_EXECUTE packet with statement ID and parameters"""
        self.statement_id = statement_id
        self.parameters = parameters or []
        self.sql = sql

    def payload(self, context: Context) -> bytes:
        stream = PayloadStream()
        stream.write_byte(self.COM_STMT_EXECUTE)
        stream.write_bytes(struct.pack('<I', self.statement_id))
        stream.write_byte(0x00) # Write flags  
        stream.write_uint32(1) # Write iteration count - always 1

        if self.parameters:
            null_bitmap_length = (len(self.parameters) + 7) // 8
            null_bitmap = bytearray(null_bitmap_length)
            
            for i, param in enumerate(self.parameters):
                is_null = (param is None or 
                          (isinstance(param, array.array) and param.typecode == 'f' and len(param) == 0) or
                          (isinstance(param, MrdbIndicator) and param.indicator == 1))  # INDICATOR.NULL
                if is_null:
                    byte_pos = i // 8
                    bit_pos = i % 8
                    null_bitmap[byte_pos] |= (1 << bit_pos)
            
            stream.write_bytes(null_bitmap) # Write NULL bitmap
            stream.write_byte(0x01) # new params bound flag
            
            # Write parameter types (2 bytes per parameter)
            for param in self.parameters:
                param_type, unsigned = self._get_parameter_type(param)
                stream.write_bytes(struct.pack('<BB', param_type, unsigned))
            
            # Write parameter values
            for param in self.parameters:
                if param is not None:
                    self._write_parameter_value(stream, param)
        
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
                return FIELD_TYPE.VAR_STRING, 0
            else:
                return FIELD_TYPE.NULL, 0
        else:
            # Default to string
            return FIELD_TYPE.VAR_STRING, 0
    
    def _write_parameter_value(self, stream: UnionType['BaseWriteStream', PayloadStream], param: Any) -> None:
        """
        Write parameter value in binary format
        
        Args:
            writer: Packet writer
            param: Parameter value
        """
        if isinstance(param, bool):
            stream.write_byte(1 if param else 0)
        elif isinstance(param, int):
            if -128 <= param <= 127:
                stream.write_bytes(struct.pack('<b', param))
            elif -32768 <= param <= 32767:
                stream.write_bytes(struct.pack('<h', param))
            elif -2147483648 <= param <= 2147483647:
                stream.write_bytes(struct.pack('<i', param))
            else:
                stream.write_bytes(struct.pack('<q', param))
        elif isinstance(param, float):
            if repr(param) in ("nan", "inf", "-inf"):
                raise NotSupportedError(f"Float value '{repr(param)}' is not supported.")
            stream.write_bytes(struct.pack('<d', param))
        elif isinstance(param, decimal.Decimal):
            if param.__str__() in ("NaN", "sNaN", "Infinity", "-Infinity"):
                raise NotSupportedError(f"Decimal value '{param.__str__()}' is not supported.")
            # Write as string
            decimal_str = str(param)
            stream.write_length_encoded_string(decimal_str)
        elif isinstance(param, str):
            stream.write_length_encoded_string(param)
        elif isinstance(param, (bytes, bytearray)):
            stream.write_length_encoded_bytes(param)
        elif isinstance(param, datetime.datetime):
            self._write_datetime(stream, param)
        elif isinstance(param, datetime.date):
            self._write_date(stream, param)
        elif isinstance(param, datetime.time):
            self._write_time(stream, param)
        elif isinstance(param, datetime.timedelta):
            self._write_time_from_timedelta(stream, param)
        elif isinstance(param, array.array) and param.typecode == 'f':
            if len(param) == 0:
                return
            # Float array for VECTOR columns - encode as numpy float32 bytes
            if HAS_NUMPY:
                float_bytes = numpy.array(param, numpy.float32).tobytes()
            else:
                # Fallback: use array.tobytes() directly
                float_bytes = param.tobytes()
            stream.write_length_encoded_bytes(float_bytes)
        elif isinstance(param, MrdbIndicator):
            # Handle MariaDB indicator values
            if param.indicator == 1:  # NULL - already handled in NULL bitmap
                return
            elif param.indicator == 2:  # DEFAULT
                stream.write_length_encoded_string('DEFAULT')
            elif param.indicator == 3:  # IGNORE
                # Skip this parameter - should be handled at a higher level
                return
            elif param.indicator == 4:  # IGNORE_ROW
                # Skip entire row - should be handled at a higher level
                return
            else:
                # Unknown indicator, treat as NULL
                return
        else:
            # Convert to string
            stream.write_length_encoded_string(str(param))
    
    def _write_datetime(self, stream: UnionType['BaseWriteStream', PayloadStream], dt: datetime.datetime) -> None:
        """Write datetime in MySQL binary format"""
        if dt.microsecond:
            # 11 bytes: year(2) + month(1) + day(1) + hour(1) + minute(1) + second(1) + microsecond(4)
            stream.write_byte(11)
            stream.write_bytes(struct.pack('<H', dt.year))
            stream.write_byte(dt.month)
            stream.write_byte(dt.day)
            stream.write_byte(dt.hour)
            stream.write_byte(dt.minute)
            stream.write_byte(dt.second)
            stream.write_bytes(struct.pack('<I', dt.microsecond))
        else:
            # 7 bytes: year(2) + month(1) + day(1) + hour(1) + minute(1) + second(1)
            stream.write_byte(7)
            stream.write_bytes(struct.pack('<H', dt.year))
            stream.write_byte(dt.month)
            stream.write_byte(dt.day)
            stream.write_byte(dt.hour)
            stream.write_byte(dt.minute)
            stream.write_byte(dt.second)
    
    def _write_date(self, stream: UnionType['BaseWriteStream', PayloadStream], date: datetime.date) -> None:
        """Write date in MySQL binary format"""
        # 4 bytes: year(2) + month(1) + day(1)
        stream.write_byte(4)
        stream.write_bytes(struct.pack('<H', date.year))
        stream.write_byte(date.month)
        stream.write_byte(date.day)
    
    def _write_time(self, stream: UnionType['BaseWriteStream', PayloadStream], time: datetime.time) -> None:
        """Write time in MySQL binary format"""
        if time.microsecond:
            # 12 bytes: negative(1) + days(4) + hour(1) + minute(1) + second(1) + microsecond(4)
            stream.write_byte(12)
            stream.write_byte(0)  # positive
            stream.write_bytes(struct.pack('<I', 0))  # days
            stream.write_byte(time.hour)
            stream.write_byte(time.minute)
            stream.write_byte(time.second)
            stream.write_bytes(struct.pack('<I', time.microsecond))
        else:
            # 8 bytes: negative(1) + days(4) + hour(1) + minute(1) + second(1)
            stream.write_byte(8)
            stream.write_byte(0)  # positive
            stream.write_bytes(struct.pack('<I', 0))  # days
            stream.write_byte(time.hour)
            stream.write_byte(time.minute)
            stream.write_byte(time.second)
    
    def _write_time_from_timedelta(self, stream: UnionType['BaseWriteStream', PayloadStream], td: datetime.timedelta) -> None:
        """Write timedelta as time in MySQL binary format"""
        total_seconds = int(td.total_seconds())
        negative = total_seconds < 0
        total_seconds = abs(total_seconds)
        
        days = total_seconds // 86400
        remaining_seconds = total_seconds % 86400
        hours = remaining_seconds // 3600
        minutes = (remaining_seconds % 3600) // 60
        seconds = remaining_seconds % 60
        microseconds = td.microseconds
        
        if microseconds:
            # 12 bytes: negative(1) + days(4) + hour(1) + minute(1) + second(1) + microsecond(4)
            stream.write_byte(12)
            stream.write_byte(1 if negative else 0)
            stream.write_bytes(struct.pack('<I', days))
            stream.write_byte(hours)
            stream.write_byte(minutes)
            stream.write_byte(seconds)
            stream.write_bytes(struct.pack('<I', microseconds))
        else:
            # 8 bytes: negative(1) + days(4) + hour(1) + minute(1) + second(1)
            stream.write_byte(8)
            stream.write_byte(1 if negative else 0)
            stream.write_bytes(struct.pack('<I', days))
            stream.write_byte(hours)
            stream.write_byte(minutes)
            stream.write_byte(seconds)

    def is_binary(self) -> bool:
        return True

    def type(self) -> str:
        return "COM_STMT_EXECUTE"           