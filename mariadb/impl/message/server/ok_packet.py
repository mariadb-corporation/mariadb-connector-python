# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
OK Packet parser for MariaDB protocol

Based on MySQL/MariaDB protocol OK packet structure.
"""

from typing import TYPE_CHECKING, Optional
from ..payload_reader import PayloadReader
from ...completion import Completion
from mariadb_shared import constants

if TYPE_CHECKING:
    from ...client.context import Context


_PS_OUT_PARAMS_MASK = constants.STATUS.PS_OUT_PARAMS
_SESSION_STATE_CHANGED = constants.STATUS.SESSION_STATE_CHANGED
_SESSION_TRACKING_CAP = constants.CAPABILITY.SESSION_TRACKING

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
    __slots__ = (
        'server_status',
        'info',
    )
    
    def __init__(
        self,
        affected_rows: int,
        insert_id: int,
        server_status: int,
        warning_count: int,
        info: bytes,
    ):
        self.affected_rows = affected_rows
        self.insert_id = insert_id
        self.warning_count = warning_count
        self.result_set = None
        self.server_status = server_status
        self.info = info

    def is_output_parameters(self) -> bool:
        return (self.server_status & _PS_OUT_PARAMS_MASK) != 0
    
    @staticmethod
    def decode(data: memoryview, context: 'Context') -> 'OkPacket':
        parser = PayloadReader(data)
        
        parser.skip(1)
        affected_rows = parser.read_length_encoded_int()
        insert_id = parser.read_length_encoded_int()
        server_status = parser.read_int16()
        warning_count = parser.read_int16()
        
        context.server_status = server_status
        context.warning_count = warning_count
        
        # Fast path: no info/tracking (most common case)
        if not parser.has_remaining():
            return OkPacket(affected_rows, insert_id, server_status, warning_count, b'')
        
        info = b''
        info_length = parser.read_length_encoded_int()
        if info_length > 0:
            info = parser.read_bytes(info_length)
        
        # Session tracking check
        if ((server_status & _SESSION_STATE_CHANGED) and 
            context.has_capability(_SESSION_TRACKING_CAP) and 
            parser.has_remaining()):
            _process_session_tracking(parser, context)

        return OkPacket(affected_rows, insert_id, server_status, warning_count, info)


def _process_session_tracking(parser: PayloadReader, context: 'Context') -> None:
    """Process session tracking data (separate function for better branch prediction)"""
    while parser.has_remaining():
        total_length = parser.read_length_encoded_int()
        if total_length == 0:
            break
        
        start_pos = parser.pos
        tracking_type = parser.read_byte()
        data_length = parser.read_length_encoded_int()
        
        if tracking_type == constants.SESSION_TRACK.SYSTEM_VARIABLES:
            end_pos = start_pos + total_length
            while parser.pos < end_pos:
                var_name_len = parser.read_length_encoded_int()
                var_name = parser.read_bytes(var_name_len).decode('utf-8')
                var_value_len = parser.read_length_encoded_int()
                if (var_name == 'character_set_client'):
                    var_value = parser.read_bytes(var_value_len).decode('utf-8')
                    context.charset = var_value
                else:
                    parser.skip(var_value_len)    
                    
        elif tracking_type == constants.SESSION_TRACK.SCHEMA:
            schema_len = parser.read_length_encoded_int()
            context.database = parser.read_bytes(schema_len).decode('utf-8')
    
        else:
            parser.skip(data_length)
        
        expected_pos = start_pos + total_length
        if parser.pos < expected_pos:
            parser.skip(expected_pos - parser.pos)