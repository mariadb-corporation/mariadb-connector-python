# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

import array
import datetime
import decimal
from typing import Any, List, Optional, Union

try:
    import numpy
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

from ...client.context import Context
from ...client.socket.payload_writer import PayloadWriter
from ...string_utils import StringEscaper
from mariadb_shared.constants.STATUS import NO_BACKSLASH_ESCAPES
from mariadb_shared.constants.INDICATOR import MrdbIndicator
from ..client_message import ClientMessage
from ....exceptions import NotSupportedError
BINARY_PREFIX: bytes = bytearray(b"_binary'")
QUOTE_BYTE: int = b"'"[0]
COM_QUERY = 0x03

class QueryPacket(ClientMessage):


    """
    Query packet for SQL execution with optional parameter binding
    """
    
    
    def __init__(self, sql: str, parameters: Optional[List[Any]] = None):
        """Initialize COM_QUERY packet with SQL and optional parameters"""
        self.sql = sql
        self.parameters = parameters or []
        
    def encode(self, context: Context) -> bytearray:
        """Encode COM_QUERY packet with SQL and bound parameters"""
        writer = PayloadWriter()
        writer.write_byte(COM_QUERY)
        if self.parameters:
            # Use parameter binding - write SQL with placeholders and parameters
            self._encode_parameterized_query(writer, context)
        else:
            # Simple query - write SQL directly
            writer.write_string(self.sql, 'utf-8')
        return writer.get_payload()
    
    def _encode_parameterized_query(self, writer: PayloadWriter, context: Context) -> None:
        """
        Encode parameterized query by interleaving SQL fragments with parameters
        
        Args:
            writer: Packet writer
        """
        # Parse SQL into fragments separated by '?' placeholders
        sql_parts = self.sql.split('?')

        #if len(sql_parts) - 1 != len(self.parameters):
        #    raise ValueError(f"Parameter count mismatch: SQL has {len(sql_parts) - 1} placeholders, got {len(self.parameters)} parameters")
        no_backslash_escapes = context.server_status & NO_BACKSLASH_ESCAPES > 0
        # Write SQL fragments interleaved with parameters
        for i, sql_part in enumerate(sql_parts):
            # Write SQL fragment
            if sql_part:  # Don't write empty strings
                writer.write_string(sql_part, 'utf-8')
            
            # Write parameter (except after the last SQL fragment)
            if i < len(self.parameters):
                self._write_parameter_value(writer, self.parameters[i], no_backslash_escapes)
            elif i < len(sql_parts) - 1:
                writer.write_string('NULL', 'ascii')
                    
    
    def _write_parameter_value(self, writer: PayloadWriter, param: Any, no_backslash_escapes: bool) -> None:
        """
        Write parameter value directly as its string representation
        (for COM_QUERY, parameters are converted to strings)
        
        Args:
            writer: Packet writer
            param: Parameter value
        """
        if param is None:
            writer.write_string('NULL', 'ascii')
        elif isinstance(param, MrdbIndicator):
            # Handle MariaDB indicator values
            if param.indicator == 1:  # NULL
                writer.write_string('NULL', 'ascii')
            elif param.indicator == 2:  # DEFAULT
                writer.write_string('DEFAULT', 'ascii')
            elif param.indicator == 3:  # IGNORE
                # Skip this parameter - should be handled at a higher level
                pass
            elif param.indicator == 4:  # IGNORE_ROW
                # Skip entire row - should be handled at a higher level
                pass
            else:
                # Unknown indicator, treat as NULL
                writer.write_string('NULL', 'ascii')
        else:
            match param:
                case str():
                    writer.write_byte(QUOTE_BYTE)
                    writer.write_string(StringEscaper.escape_string(param, no_backslash_escapes))
                    writer.write_byte(QUOTE_BYTE)
                case bytes() | bytearray():
                    writer.write_bytes(BINARY_PREFIX)
                    writer.write_escaped_bytes(param, no_backslash_escapes)
                    writer.write_byte(QUOTE_BYTE)
                case bool():
                    # Handle boolean before int/float since bool is a subclass of int in Python
                    writer.write_string( '1' if param else '0', 'ascii')
                case int():
                    writer.write_string( str(param), 'ascii')
                case float():
                    if repr(param) in ("nan", "inf", "-inf"):
                        raise NotSupportedError(f"Float value '{repr(param)}' is not supported.")
                    writer.write_string( str(param), 'ascii')
                

                case datetime.datetime():
                    # DATETIME: 'YYYY-MM-DD HH:MM:SS.ffffff'
                    if param.microsecond:
                        writer.write_string(f"'{param.strftime('%Y-%m-%d %H:%M:%S')}.{param.microsecond:06d}'", 'ascii')
                    else:
                        writer.write_string(f"'{param.strftime('%Y-%m-%d %H:%M:%S')}'", 'ascii')
                case datetime.date():
                    # DATE: 'YYYY-MM-DD'
                    writer.write_string(f"'{param.strftime('%Y-%m-%d')}'", 'ascii')
                case datetime.time():
                    # TIME: 'HH:MM:SS.ffffff'
                    if param.microsecond:
                        writer.write_string(f"'{param.strftime('%H:%M:%S')}.{param.microsecond:06d}'", 'ascii')
                    else:
                        writer.write_string(f"'{param.strftime('%H:%M:%S')}'", 'ascii')
                case datetime.timedelta():
                    # Convert timedelta to TIME format (can be negative)
                    total_seconds = int(param.total_seconds())
                    hours, remainder = divmod(abs(total_seconds), 3600)
                    minutes, seconds = divmod(remainder, 60)
                    microseconds = param.microseconds
                    
                    sign = '-' if total_seconds < 0 else ''
                    if microseconds:
                        writer.write_string(f"'{sign}{hours:02d}:{minutes:02d}:{seconds:02d}.{microseconds:06d}'", 'ascii')
                    else:
                        writer.write_string(f"'{sign}{hours:02d}:{minutes:02d}:{seconds:02d}'", 'ascii')
                case decimal.Decimal():
                    if param.__str__() in ("NaN", "sNaN", "Infinity", "-Infinity"):
                        raise NotSupportedError(f"Decimal value '{param.__str__()}' is not supported.")                    
                    # DECIMAL/NUMERIC: no quotes needed, just string representation                    
                    writer.write_string(str(param), 'ascii')
                case array.array() if param.typecode == 'f':
                    if len(param) == 0:
                        writer.write_string('NULL', 'ascii')
                        return
                    # Float array for VECTOR columns - encode as numpy float32 bytes
                    if HAS_NUMPY:
                        float_bytes = numpy.array(param, numpy.float32).tobytes()
                    else:
                        # Fallback: use array.tobytes() directly
                        float_bytes = param.tobytes()
                    writer.write_bytes(BINARY_PREFIX)
                    writer.write_escaped_bytes(float_bytes, no_backslash_escapes)
                    writer.write_byte(QUOTE_BYTE)
                case _:
                    # For other types, convert to string and escape
                    writer.write_byte(QUOTE_BYTE)
                    writer.write_string(StringEscaper.escape_string(str(param), no_backslash_escapes))
                    writer.write_byte(QUOTE_BYTE)

    def is_binary(self) -> bool:
        return False

    def type(self) -> str:
        return "COM_QUERY"
        