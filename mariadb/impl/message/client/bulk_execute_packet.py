# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

import array
import datetime
import decimal
import struct
from typing import Any, List, Optional

# Pre-compiled struct formats for performance
_STRUCT_H = struct.Struct('<H')  # unsigned short (2 bytes)
_STRUCT_I = struct.Struct('<I')  # unsigned int (4 bytes)
_STRUCT_b = struct.Struct('<b')  # signed byte
_STRUCT_h = struct.Struct('<h')  # signed short
_STRUCT_i = struct.Struct('<i')  # signed int
_STRUCT_q = struct.Struct('<q')  # signed long long
_STRUCT_d = struct.Struct('<d')  # double
_STRUCT_BB = struct.Struct('<BB')  # two unsigned bytes

# Composite struct formats for datetime/date/time
_STRUCT_DATETIME_WITH_MICRO = struct.Struct('<BHHBBBBBI')  # length + year(H) + 5 bytes + microsecond(I)
_STRUCT_DATETIME_NO_MICRO = struct.Struct('<BHBBBBB')     # length + year(H) + 5 bytes
_STRUCT_DATE = struct.Struct('<BHBB')                      # length + year(H) + month + day
_STRUCT_TIME_WITH_MICRO = struct.Struct('<BBBIBBBI')      # length + negative + days(I) + 3 bytes + microsecond(I)
_STRUCT_TIME_NO_MICRO = struct.Struct('<BBIBBB')          # length + negative + days(I) + 3 bytes

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


class BulkExecutePacket(ClientMessage):
    """
    Bulk Execute packet for prepared statement bulk execution (COM_STMT_BULK_EXECUTE)
    
    Allows sending multiple parameter sets in a single packet for efficient batch execution.
    See: https://mariadb.com/kb/en/com_stmt_bulk_execute/
    """
    
    COM_STMT_BULK_EXECUTE = 0xFA
    
    # Bulk flags
    SEND_TYPES_TO_SERVER = 128  # Send parameter types
    SEND_UNIT_RESULTS = 64  # retrieve unit results
    
    def __init__(self, statement_id: int, parameter_sets: List[List[Any]], sql: str = ""):
        """
        Initialize COM_STMT_BULK_EXECUTE packet
        
        Args:
            statement_id: Prepared statement ID
            parameter_sets: List of parameter lists (one per execution)
            sql: Original SQL (for debugging)
        """
        self.statement_id = statement_id
        self.parameter_sets = parameter_sets or []
        self.sql = sql

    def payload(self, context: Context) -> bytearray:
        stream = PayloadWriter()
        stream.write_byte(self.COM_STMT_BULK_EXECUTE)
        stream.write_bytes(_STRUCT_I.pack(self.statement_id))
        
        # Flags: SEND_TYPES_TO_SERVER (128)
        stream.write_uint16(self.SEND_TYPES_TO_SERVER)
        
        if not self.parameter_sets:
            return stream.get_payload()
        
        # Write parameter types (2 bytes per parameter) - only once for all sets
        for param in self.parameter_sets[0]:
            field_type, unsigned = self._get_parameter_type(param)
            stream.write_bytes(_STRUCT_BB.pack(field_type, unsigned))
        
        # Write parameter data for each row
        # Protocol: Until end of packet, for each parameter:
        #   - byte<1>: indicator (0=NONE/value follows, 1=NULL, 2=DEFAULT, etc.)
        #   - If indicator == 0: binary parameter value
        for param_set in self.parameter_sets:
            for param in param_set:
                if param is None:
                    stream.write_byte(1)  # NULL indicator
                elif isinstance(param, MrdbIndicator):
                    if param.indicator == 0:
                        stream.write_byte(0)  # NONE indicator - value follows
                        self._write_parameter_value(stream, param)
                    else:
                        stream.write_byte(param.indicator)
                else:
                    stream.write_byte(0)  # NONE indicator - value follows
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
            return FIELD_TYPE.BLOB, 0
        elif isinstance(param, MrdbIndicator):
            return FIELD_TYPE.NULL, 0
        else:
            return FIELD_TYPE.VAR_STRING, 0

    def _write_parameter_value(self, stream: PayloadWriter, param: Any):
        """Write parameter value in binary format"""
        if isinstance(param, bool):
            stream.write_byte(1 if param else 0)
        elif isinstance(param, int):
            stream.write_bytes(_STRUCT_q.pack(param))
        elif isinstance(param, float):
            if repr(param) in ("nan", "inf", "-inf"):
                raise NotSupportedError(f"Float value '{repr(param)}' is not supported.")
            stream.write_bytes(_STRUCT_d.pack(param))
        elif isinstance(param, decimal.Decimal):
            if param.__str__() in ("NaN", "sNaN", "Infinity", "-Infinity"):
                raise NotSupportedError(f"Decimal value '{param.__str__()}' is not supported.")
            stream.write_length_encoded_string(str(param))
        elif isinstance(param, str):
            stream.write_length_encoded_string(param)
        elif isinstance(param, (bytes, bytearray)):
            stream.write_length_encoded_bytes(param)
        elif isinstance(param, datetime.datetime):
            if param.microsecond:
                stream.write_bytes(_STRUCT_DATETIME_WITH_MICRO.pack(
                    11, param.year, param.month, param.day,
                    param.hour, param.minute, param.second, param.microsecond
                ))
            else:
                stream.write_bytes(_STRUCT_DATETIME_NO_MICRO.pack(
                    7, param.year, param.month, param.day,
                    param.hour, param.minute, param.second
                ))
        elif isinstance(param, datetime.date):
            stream.write_bytes(_STRUCT_DATE.pack(4, param.year, param.month, param.day))
        elif isinstance(param, datetime.time):
            if param.microsecond:
                stream.write_bytes(_STRUCT_TIME_WITH_MICRO.pack(
                    12, 0, 0, param.hour, param.minute, param.second, param.microsecond
                ))
            else:
                stream.write_bytes(_STRUCT_TIME_NO_MICRO.pack(
                    8, 0, 0, param.hour, param.minute, param.second
                ))
        elif isinstance(param, datetime.timedelta):
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
                stream.write_bytes(_STRUCT_TIME_WITH_MICRO.pack(
                    12, 1 if negative else 0, days, hours, minutes, seconds, microseconds
                ))
            else:
                stream.write_bytes(_STRUCT_TIME_NO_MICRO.pack(
                    8, 1 if negative else 0, days, hours, minutes, seconds
                ))
        elif isinstance(param, array.array) and param.typecode == 'f':
            if len(param) == 0:
                return
            if HAS_NUMPY:
                float_bytes = numpy.array(param, numpy.float32).tobytes()
            else:
                float_bytes = param.tobytes()
            stream.write_length_encoded_bytes(float_bytes)
        else:
            # Fallback: convert to string
            stream.write_length_encoded_string(str(param))

    def is_binary(self) -> bool:
        return True

    def type(self) -> str:
        return "COM_STMT_BULK_EXECUTE"
