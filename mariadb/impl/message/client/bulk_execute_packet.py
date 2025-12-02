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
    __slots__ = ('statement_id', 'parameter_sets', 'sql', 'parameter_types', 'parameter_writers')
    
    COM_STMT_BULK_EXECUTE = 0xFA
    
    # Bulk flags
    SEND_TYPES_TO_SERVER = 128  # Send parameter types
    SEND_UNIT_RESULTS = 64  # retrieve unit results
    
    def __init__(self, statement_id: Optional[int], parameter_sets: List[List[Any]], sql: str = ""):
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
        # Determine parameter types and write functions by analyzing all parameter sets
        self.parameter_types: List[tuple[int, int]] = []
        self.parameter_writers: List = []  # Write functions for each parameter
        self._determine_parameter_types()

    def payload(self, context: Context) -> bytearray:
        stream = PayloadWriter()
        stream.write_byte(self.COM_STMT_BULK_EXECUTE)
        stream.write_bytes(_STRUCT_I.pack(self.statement_id) if self.statement_id is not None else b'\xFF\xFF\xFF\xFF')
        
        # Flags: SEND_TYPES_TO_SERVER (128)
        stream.write_uint16(self.SEND_TYPES_TO_SERVER)
        
        if not self.parameter_sets:
            return stream.get_payload()
        
        # Write parameter types (2 bytes per parameter) - determined from all parameter sets
        for field_type, unsigned in self.parameter_types:
            stream.write_bytes(_STRUCT_BB.pack(field_type, unsigned))
        
        # Write parameter data for each row
        # Protocol: Until end of packet, for each parameter:
        #   - byte<1>: indicator (0=NONE/value follows, 1=NULL, 2=DEFAULT, etc.)
        #   - If indicator == 0: binary parameter value
        for param_set in self.parameter_sets:
            for param_idx, param in enumerate(param_set):
                if param is None:
                    stream.write_byte(1)  # NULL indicator
                elif isinstance(param, MrdbIndicator):
                    if param.indicator == 0:
                        stream.write_byte(0)  # NONE indicator - value follows
                        self.parameter_writers[param_idx](stream, param)
                    else:
                        stream.write_byte(param.indicator)
                else:
                    stream.write_byte(0)  # NONE indicator - value follows
                    self.parameter_writers[param_idx](stream, param)
        
        return stream.get_payload()

    def _determine_parameter_types(self) -> None:
        """
        Determine parameter types and write functions by analyzing all parameter sets.
        For each column position, find the minimum type that can hold all values
        and store the corresponding write function.
        """
        if not self.parameter_sets:
            return
        
        # Map field types to write functions
        type_to_writer = {
            FIELD_TYPE.TINY: self._write_tiny,
            FIELD_TYPE.SHORT: self._write_short,
            FIELD_TYPE.LONG: self._write_long,
            FIELD_TYPE.LONGLONG: self._write_longlong,
            FIELD_TYPE.DOUBLE: self._write_double,
            FIELD_TYPE.NEWDECIMAL: self._write_decimal,
            FIELD_TYPE.VAR_STRING: self._write_string,
            FIELD_TYPE.BLOB: self._write_blob,
            FIELD_TYPE.DATETIME: self._write_datetime,
            FIELD_TYPE.DATE: self._write_date,
            FIELD_TYPE.TIME: self._write_time,
        }
        
        num_params = len(self.parameter_sets[0])
        
        for param_idx in range(num_params):
            # Collect all values at this parameter position across all sets
            max_type = FIELD_TYPE.NULL
            
            for param_set in self.parameter_sets:
                if param_idx >= len(param_set):
                    continue
                    
                param = param_set[param_idx]
                param_type, _ = self._get_parameter_type(param)
                
                # Determine the maximum type needed
                if param_type != FIELD_TYPE.NULL:
                    if max_type == FIELD_TYPE.NULL:
                        max_type = param_type
                    else:
                        # For integers, upgrade to larger type if needed
                        max_type = self._get_wider_integer_type(max_type, param_type)
            
            self.parameter_types.append((max_type, 0))
            # Store the write function for this parameter
            writer = type_to_writer.get(max_type, self._write_string)
            self.parameter_writers.append(writer)
    
    def _get_wider_integer_type(self, type1: int, type2: int) -> int:
        """
        Get the wider of two integer types.
        
        Args:
            type1: First field type
            type2: Second field type
            
        Returns:
            The wider field type that can hold both
        """
        # Integer type hierarchy: TINY < SHORT < LONG < LONGLONG
        int_types = [FIELD_TYPE.TINY, FIELD_TYPE.SHORT, FIELD_TYPE.LONG, FIELD_TYPE.LONGLONG]
        
        # If both are integer types, return the wider one
        if type1 in int_types and type2 in int_types:
            return int_types[max(int_types.index(type1), int_types.index(type2))]
        
        # If types don't match or aren't integers, prefer type2 (current param type)
        if type1 != type2:
            return type2
        
        return type1
    
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

    # =========================================================================
    # Type-specific write methods
    # =========================================================================
    
    def _write_tiny(self, stream: PayloadWriter, param: Any):
        """Write TINY (1 byte signed integer)"""
        if isinstance(param, bool):
            stream.write_byte(1 if param else 0)
        else:
            stream.write_bytes(_STRUCT_b.pack(param))
    
    def _write_short(self, stream: PayloadWriter, param: Any):
        """Write SHORT (2 byte signed integer)"""
        stream.write_bytes(_STRUCT_h.pack(param))
    
    def _write_long(self, stream: PayloadWriter, param: Any):
        """Write LONG (4 byte signed integer)"""
        stream.write_bytes(_STRUCT_i.pack(param))
    
    def _write_longlong(self, stream: PayloadWriter, param: Any):
        """Write LONGLONG (8 byte signed integer)"""
        stream.write_bytes(_STRUCT_q.pack(param))
    
    def _write_double(self, stream: PayloadWriter, param: Any):
        """Write DOUBLE (8 byte float)"""
        if repr(param) in ("nan", "inf", "-inf"):
            raise NotSupportedError(f"Float value '{repr(param)}' is not supported.")
        stream.write_bytes(_STRUCT_d.pack(param))
    
    def _write_decimal(self, stream: PayloadWriter, param: Any):
        """Write DECIMAL as length-encoded string"""
        if param.__str__() in ("NaN", "sNaN", "Infinity", "-Infinity"):
            raise NotSupportedError(f"Decimal value '{param.__str__()}' is not supported.")
        stream.write_length_encoded_string(str(param))
    
    def _write_string(self, stream: PayloadWriter, param: Any):
        """Write VAR_STRING as length-encoded string"""
        stream.write_length_encoded_string(param)
    
    def _write_blob(self, stream: PayloadWriter, param: Any):
        """Write BLOB as length-encoded bytes"""
        if isinstance(param, array.array) and param.typecode == 'f':
            if len(param) == 0:
                return
            if HAS_NUMPY:
                float_bytes = numpy.array(param, numpy.float32).tobytes()
            else:
                float_bytes = param.tobytes()
            stream.write_length_encoded_bytes(float_bytes)
        else:
            stream.write_length_encoded_bytes(param)
    
    def _write_datetime(self, stream: PayloadWriter, param: Any):
        """Write DATETIME in MySQL binary format"""
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
    
    def _write_date(self, stream: PayloadWriter, param: Any):
        """Write DATE in MySQL binary format"""
        stream.write_bytes(_STRUCT_DATE.pack(4, param.year, param.month, param.day))
    
    def _write_time(self, stream: PayloadWriter, param: Any):
        """Write TIME in MySQL binary format"""
        if isinstance(param, datetime.timedelta):
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
        else:  # datetime.time
            if param.microsecond:
                stream.write_bytes(_STRUCT_TIME_WITH_MICRO.pack(
                    12, 0, 0, param.hour, param.minute, param.second, param.microsecond
                ))
            else:
                stream.write_bytes(_STRUCT_TIME_NO_MICRO.pack(
                    8, 0, 0, param.hour, param.minute, param.second
                ))

    def is_binary(self) -> bool:
        return True

    def type(self) -> str:
        return "COM_STMT_BULK_EXECUTE"
