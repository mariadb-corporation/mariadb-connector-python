# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
OK Packet parser for MariaDB protocol

Based on MySQL/MariaDB protocol OK packet structure.
"""

import struct
from typing import TYPE_CHECKING
from ..payload_reader import PayloadReader
from ...completion import Completion
from mariadb_shared.exceptions import OperationalError
from mariadb_shared import constants

_unpack_H = struct.Struct('<H').unpack_from
_unpack_Q = struct.Struct('<Q').unpack_from
_unpack_hh = struct.Struct('<hh').unpack_from

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
        pos = 1  # skip 0x00/0xFE header

        # Read affected_rows (length-encoded int)
        b = data[pos]; pos += 1
        if b < 251:
            affected_rows = b
        elif b == 252:
            affected_rows = _unpack_H(data, pos)[0]; pos += 2
        elif b == 253:
            affected_rows = (data[pos] | (data[pos+1] << 8) | (data[pos+2] << 16)); pos += 3
        else:
            affected_rows = _unpack_Q(data, pos)[0]; pos += 8

        # Read insert_id (length-encoded int)
        b = data[pos]; pos += 1
        if b < 251:
            insert_id = b
        elif b == 252:
            insert_id = _unpack_H(data, pos)[0]; pos += 2
        elif b == 253:
            insert_id = (data[pos] | (data[pos+1] << 8) | (data[pos+2] << 16)); pos += 3
        else:
            insert_id = _unpack_Q(data, pos)[0]; pos += 8

        server_status, warning_count = _unpack_hh(data, pos)
        pos += 4
        
        context.server_status = server_status
        context.warning_count = warning_count
        
        # Fast path: no info/tracking (most common case)
        if pos >= len(data):
            return OkPacket(affected_rows, insert_id, server_status, warning_count, b'')
        
        # Slow path: use PayloadReader for remaining complex parsing
        parser = PayloadReader(data, pos)
        info = b''
        info_length = parser.read_length_encoded_int()
        if info_length is not None and info_length > 0:
            info = parser.read_bytes(info_length)
        
        # Session tracking check
        if ((server_status & _SESSION_STATE_CHANGED) and 
            context.has_capability(_SESSION_TRACKING_CAP) and 
            parser.has_remaining()):
            _process_session_tracking(parser, context)

        return OkPacket(affected_rows, insert_id, server_status, warning_count, info)


class CharsetMismatchError(OperationalError):
    """Raised when the server changes character_set_client away from the configured charset."""
    pass


def _process_session_tracking(parser: PayloadReader, context: 'Context') -> None:
    """Process session tracking data (separate function for better branch prediction)"""
    while parser.has_remaining():
        total_length = parser.read_length_encoded_int_not_null()
        if total_length == 0:
            break

        start_pos = parser.pos
        tracking_type = parser.read_byte()
        data_length = parser.read_length_encoded_int_not_null()

        if tracking_type == constants.SESSION_TRACK.SYSTEM_VARIABLES:
            end_pos = start_pos + total_length
            while parser.pos < end_pos:
                var_name_len = parser.read_length_encoded_int_not_null()
                var_name = parser.read_bytes(var_name_len).decode('utf-8')
                var_value_len = parser.read_length_encoded_int()
                if (var_name == 'character_set_client'):
                    if var_value_len is None:
                        raise CharsetMismatchError(
                            "character_set_client cannot be changed to NULL. "
                            "Connection closed."
                        )
                    var_value = parser.read_bytes(var_value_len).decode('utf-8')
                    if context.charset and var_value != context.charset:
                        raise CharsetMismatchError(
                            f"character_set_client changed to '{var_value}' "
                            "but only 'utf8mb4' is permitted. "
                            "Connection closed."
                        )
                    context.charset = var_value
                else:
                    if var_value_len:
                        parser.skip(var_value_len)
                    
        elif tracking_type == constants.SESSION_TRACK.SCHEMA:
            schema_len = parser.read_length_encoded_int_not_null()
            context.database = parser.read_bytes(schema_len).decode('utf-8')
    
        else:
            parser.skip(data_length)
        
        expected_pos = start_pos + total_length
        if parser.pos < expected_pos:
            parser.skip(expected_pos - parser.pos)