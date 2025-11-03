#
# Copyright (C) 2020-2021 Georg Richter and MariaDB Corporation AB

# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Library General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.

# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Library General Public License for more details.

# You should have received a copy of the GNU Library General Public
# License along with this library; if not see <http://www.gnu.org/licenses>
# or write to the Free Software Foundation, Inc.,
# 51 Franklin St., Fifth Floor, Boston, MA 02110, USA
#

"""
Execute packet for MariaDB prepared statement execution

Equivalent to the Java ExecutePacket class.
"""

import array
import datetime
import decimal
import struct
from typing import TYPE_CHECKING, Any, List, Optional

try:
    import numpy
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

if TYPE_CHECKING:
    from ...client.socket.stream import Stream

from ...client.context import Context
from ...client.socket.payload_writer import PayloadWriter
from ...string_utils import StringEscaper
from mariadb_shared.constants import FIELD_TYPE
from mariadb_shared.constants.INDICATOR import MrdbIndicator
from ..client_message import ClientMessage
from ....exceptions import NotSupportedError

class ExecutePacket(ClientMessage):
    """
    Execute packet for prepared statement execution (COM_STMT_EXECUTE)
    
    See: https://mariadb.com/kb/en/com_stmt_execute/
    """
    
    COM_STMT_EXECUTE = 0x17
    
    def __init__(self, statement_id: int, parameters: Optional[List[Any]] = None, sql: str = ""):
        """
        Initialize execute packet
        
        Args:
            statement_id: Prepared statement ID
            parameters: Optional list of parameters to bind
            sql: Original SQL for debugging
        """
        self.statement_id = statement_id
        self.parameters = parameters or []
        self.sql = sql
        
    def encode(self, stream: 'Stream', context: Context) -> None:
        """
        Encode execute packet
        
        Args:
            stream: Stream to send payload through
            context: Connection context
        """
        # Build payload
        writer = PayloadWriter()
        
        # Write COM_STMT_EXECUTE command
        writer.write_byte(self.COM_STMT_EXECUTE)
        
        # Write statement ID (4 bytes, little endian)
        writer.write_bytes(struct.pack('<I', self.statement_id))
        
        # Write flags (1 byte) - 0 = no flags
        writer.write_byte(0x00)
        
        # Write iteration count (4 bytes, little endian) - always 1
        writer.write_bytes(struct.pack('<I', 1))
        
        if self.parameters:
            # Write NULL bitmap
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
            
            writer.write_bytes(null_bitmap)
            
            # Write new params bound flag (1 byte) - 1 = new params
            writer.write_byte(0x01)
            
            # Write parameter types (2 bytes per parameter)
            for param in self.parameters:
                param_type, unsigned = self._get_parameter_type(param)
                writer.write_bytes(struct.pack('<BB', param_type, unsigned))
            
            # Write parameter values
            for param in self.parameters:
                if param is not None:
                    self._write_parameter_value(writer, param)
        
        # Send payload through stream
        stream.send_payload(writer.get_payload(), "COM_STMT_EXECUTE")
    
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
    
    def _write_parameter_value(self, writer: PayloadWriter, param: Any) -> None:
        """
        Write parameter value in binary format
        
        Args:
            writer: Packet writer
            param: Parameter value
        """
        if isinstance(param, bool):
            writer.write_byte(1 if param else 0)
        elif isinstance(param, int):
            if -128 <= param <= 127:
                writer.write_bytes(struct.pack('<b', param))
            elif -32768 <= param <= 32767:
                writer.write_bytes(struct.pack('<h', param))
            elif -2147483648 <= param <= 2147483647:
                writer.write_bytes(struct.pack('<i', param))
            else:
                writer.write_bytes(struct.pack('<q', param))
        elif isinstance(param, float):
            if repr(param) in ("nan", "inf", "-inf"):
                raise NotSupportedError(f"Float value '{repr(param)}' is not supported.")
            writer.write_bytes(struct.pack('<d', param))
        elif isinstance(param, decimal.Decimal):
            if param.__str__() in ("NaN", "sNaN", "Infinity", "-Infinity"):
                raise NotSupportedError(f"Decimal value '{param.__str__()}' is not supported.")
            # Write as string
            decimal_str = str(param)
            writer.write_length_encoded_string(decimal_str)
        elif isinstance(param, str):
            writer.write_length_encoded_string(param)
        elif isinstance(param, (bytes, bytearray)):
            writer.write_length_encoded_bytes(param)
        elif isinstance(param, datetime.datetime):
            self._write_datetime(writer, param)
        elif isinstance(param, datetime.date):
            self._write_date(writer, param)
        elif isinstance(param, datetime.time):
            self._write_time(writer, param)
        elif isinstance(param, datetime.timedelta):
            self._write_time_from_timedelta(writer, param)
        elif isinstance(param, array.array) and param.typecode == 'f':
            if len(param) == 0:
                return
            # Float array for VECTOR columns - encode as numpy float32 bytes
            if HAS_NUMPY:
                float_bytes = numpy.array(param, numpy.float32).tobytes()
            else:
                # Fallback: use array.tobytes() directly
                float_bytes = param.tobytes()
            writer.write_length_encoded_bytes(float_bytes)
        elif isinstance(param, MrdbIndicator):
            # Handle MariaDB indicator values
            if param.indicator == 1:  # NULL - already handled in NULL bitmap
                return
            elif param.indicator == 2:  # DEFAULT
                writer.write_length_encoded_string('DEFAULT')
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
            writer.write_length_encoded_string(str(param))
    
    def _write_datetime(self, writer: PayloadWriter, dt: datetime.datetime) -> None:
        """Write datetime in MySQL binary format"""
        if dt.microsecond:
            # 11 bytes: year(2) + month(1) + day(1) + hour(1) + minute(1) + second(1) + microsecond(4)
            writer.write_byte(11)
            writer.write_bytes(struct.pack('<H', dt.year))
            writer.write_byte(dt.month)
            writer.write_byte(dt.day)
            writer.write_byte(dt.hour)
            writer.write_byte(dt.minute)
            writer.write_byte(dt.second)
            writer.write_bytes(struct.pack('<I', dt.microsecond))
        else:
            # 7 bytes: year(2) + month(1) + day(1) + hour(1) + minute(1) + second(1)
            writer.write_byte(7)
            writer.write_bytes(struct.pack('<H', dt.year))
            writer.write_byte(dt.month)
            writer.write_byte(dt.day)
            writer.write_byte(dt.hour)
            writer.write_byte(dt.minute)
            writer.write_byte(dt.second)
    
    def _write_date(self, writer: PayloadWriter, date: datetime.date) -> None:
        """Write date in MySQL binary format"""
        # 4 bytes: year(2) + month(1) + day(1)
        writer.write_byte(4)
        writer.write_bytes(struct.pack('<H', date.year))
        writer.write_byte(date.month)
        writer.write_byte(date.day)
    
    def _write_time(self, writer: PayloadWriter, time: datetime.time) -> None:
        """Write time in MySQL binary format"""
        if time.microsecond:
            # 12 bytes: negative(1) + days(4) + hour(1) + minute(1) + second(1) + microsecond(4)
            writer.write_byte(12)
            writer.write_byte(0)  # positive
            writer.write_bytes(struct.pack('<I', 0))  # days
            writer.write_byte(time.hour)
            writer.write_byte(time.minute)
            writer.write_byte(time.second)
            writer.write_bytes(struct.pack('<I', time.microsecond))
        else:
            # 8 bytes: negative(1) + days(4) + hour(1) + minute(1) + second(1)
            writer.write_byte(8)
            writer.write_byte(0)  # positive
            writer.write_bytes(struct.pack('<I', 0))  # days
            writer.write_byte(time.hour)
            writer.write_byte(time.minute)
            writer.write_byte(time.second)
    
    def _write_time_from_timedelta(self, writer: PayloadWriter, td: datetime.timedelta) -> None:
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
            writer.write_byte(12)
            writer.write_byte(1 if negative else 0)
            writer.write_bytes(struct.pack('<I', days))
            writer.write_byte(hours)
            writer.write_byte(minutes)
            writer.write_byte(seconds)
            writer.write_bytes(struct.pack('<I', microseconds))
        else:
            # 8 bytes: negative(1) + days(4) + hour(1) + minute(1) + second(1)
            writer.write_byte(8)
            writer.write_byte(1 if negative else 0)
            writer.write_bytes(struct.pack('<I', days))
            writer.write_byte(hours)
            writer.write_byte(minutes)
            writer.write_byte(seconds)

    def is_binary(self) -> bool:
        return True