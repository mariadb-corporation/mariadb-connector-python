# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
OK Packet parser for MariaDB protocol

Based on MySQL/MariaDB protocol OK packet structure.
"""

from typing import TYPE_CHECKING, Optional
from ...client.socket.payload_parser import PayloadParser
from ...completion import Completion
from mariadb_shared import constants

if TYPE_CHECKING:
    from ...client.context import Context


class OkPacket(Completion):
    """
    OK Packet from MariaDB server
    
    Structure:
    - 1 byte: OK marker (0x00 or 0xFE)
    - length-encoded int: affected_rows
    - length-encoded int: last_insert_id
    - 2 bytes: server_status
    - 2 bytes: warning_count
    - optional: info string (length-encoded)
    - optional: session tracking data (if CLIENT_SESSION_TRACK enabled)
    """
    
    def __init__(
        self,
        affected_rows: int = 0,
        insert_id: int = 0,
        server_status: int = 0,
        warning_count: int = 0,
        info: Optional[str] = None
    ):
        """Initialize OK packet with affected rows, insert ID, status, and warnings"""
        # Initialize parent Completion with common fields
        super().__init__(
            affected_rows=affected_rows,
            insert_id=insert_id,
            warning_count=warning_count
        )
        
        # OkPacket-specific fields
        self.server_status = server_status
        self.info = info
    

    def is_output_parameters(self) -> bool:
        """Check if completion has output parameters"""
        return (self.server_status & constants.STATUS.PS_OUT_PARAMS) != 0
    
    @staticmethod
    def decode(data: bytearray, context: 'Context') -> 'OkPacket':
        """Decode OK packet from bytearray with context"""
        parser = PayloadParser(data)
        
        parser.read_byte() # Skip OK marker (0x00 or 0xFE)
        affected_rows = parser.read_length_encoded_int()
        insert_id = parser.read_length_encoded_int()
        server_status = parser.read_int16()
        warning_count = parser.read_int16()
        
        # Update context with server status
        if context:
            context.server_status = server_status
            context.warning_count = warning_count
        
        # Optional info string and session tracking
        info = None
        if parser.has_remaining():
            # Check if session tracking is present
            if (context and 
                context.has_capability(constants.CAPABILITY.SESSION_TRACKING) and
                (server_status & constants.STATUS.SESSION_STATE_CHANGED)):
                
                # With session tracking, the format is:
                # - info string (length-encoded)
                # - session tracking data (length-encoded, then tracking blocks)
                try:
                    # Read info string length
                    info_length = parser.read_length_encoded_int()
                    if info_length > 0:
                        info_bytes = parser.read_bytes(info_length)
                        info = info_bytes.decode('utf-8', errors='replace')
                    
                    # Process session tracking data
                    if parser.has_remaining():
                        _process_session_tracking(parser, context)
                except Exception:
                    # Log but don't fail on session tracking errors
                    pass
            else:
                # No session tracking - just read info string if present
                try:
                    info_length = parser.read_length_encoded_int()
                    if info_length > 0:
                        info_bytes = parser.read_bytes(info_length)
                        info = info_bytes.decode('utf-8', errors='replace')
                except Exception:
                    pass
        
        return OkPacket(
            affected_rows=affected_rows,
            insert_id=insert_id,
            server_status=server_status,
            warning_count=warning_count,
            info=info
        )
    
    def __repr__(self) -> str:
        return (f"OkPacket(affected_rows={self.affected_rows}, "
                f"insert_id={self.insert_id}, "
                f"server_status=0x{self.server_status:04X}, "
                f"warning_count={self.warning_count})")


def _process_session_tracking(parser: PayloadParser, context: 'Context') -> None:
    """
    Process session tracking information from OK packet
    
    Args:
        parser: PayloadParser with remaining session tracking data
        context: Connection context to update
    """
    while parser.has_remaining():
        try:
            # Total length of session tracking data (length-encoded)
            total_length = parser.read_length_encoded_int()
            if total_length == 0:
                break
            
            # Track start position to ensure we don't read beyond this tracking block
            start_pos = parser.pos
            
            # Session tracking type (1 byte)
            tracking_type = parser.read_byte()
            
            # Data length (length-encoded)
            data_length = parser.read_length_encoded_int()
            
            # Process based on tracking type
            if tracking_type == constants.SESSION_TRACK.SYSTEM_VARIABLES:
                # System variable change
                while parser.pos < start_pos + total_length:
                    var_name_len = parser.read_length_encoded_int()
                    var_name = parser.read_bytes(var_name_len).decode('utf-8')
                    
                    var_value_len = parser.read_length_encoded_int()
                    var_value = parser.read_bytes(var_value_len).decode('utf-8')
                    
                    # Update context with system variable change
                    if hasattr(context, 'update_system_variable'):
                        context.update_system_variable(var_name, var_value)
            
            elif tracking_type == constants.SESSION_TRACK.SCHEMA:
                # Schema change
                schema_len = parser.read_length_encoded_int()
                schema = parser.read_bytes(schema_len).decode('utf-8')
                if hasattr(context, 'database'):
                    context.database = schema
            
            elif tracking_type == constants.SESSION_TRACK.STATE_CHANGE:
                # Session state change
                state_data = parser.read_bytes(data_length)
                # Process state change if needed
                pass
            
            else:
                # Unknown tracking type - skip data
                parser.skip(data_length)
            
            # Ensure we're at the correct position
            expected_pos = start_pos + total_length
            if parser.pos < expected_pos:
                parser.skip(expected_pos - parser.pos)
            
        except Exception:
            # If we can't parse session tracking, stop processing
            break
