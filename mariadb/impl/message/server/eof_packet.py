# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
EOF Packet parser for MariaDB protocol

Based on MySQL/MariaDB protocol EOF packet structure.
"""

from typing import TYPE_CHECKING
from ...completion import Completion
from ...client.socket.read_stream import PacketBuffer
if TYPE_CHECKING:
    from ...client.context import Context

from mariadb_shared import constants

class EofPacket(Completion):
    """
    EOF Packet from MariaDB server
    
    Structure (Traditional EOF packet - when DEPRECATE_EOF is not enabled):
    - 1 byte: EOF marker (0xFE)
    - 2 bytes: warning_count (little-endian)
    - 2 bytes: server_status (little-endian)
    
    Note: When DEPRECATE_EOF capability is enabled, the server sends
    an OK packet with 0xFE header instead of a traditional EOF packet.
    In that case, use OkPacket.decode() instead.
    """
    __slots__ = (
        'warning_count',
        'server_status',
    )
    def __init__(
        self,
        warning_count: int = 0,
        server_status: int = 0,
        is_output_parameters: bool = False
    ):
        """Initialize EOF packet with warning count and server status"""
        self.affected_rows = 0
        self.insert_id = 0
        self.warning_count = warning_count
        self.result_set = None
        
        # EofPacket-specific fields
        self.server_status = server_status
    
    def is_output_parameters(self) -> bool:
        """Check if completion has output parameters"""
        return (self.server_status & constants.STATUS.PS_OUT_PARAMS) != 0

    @staticmethod
    def decode(data: PacketBuffer, context: 'Context') -> 'EofPacket':
        """Decode EOF packet from bytearray with context"""
        warning_count = data[1] | (data[2] << 8)
        server_status = data[3] | (data[4] << 8)
        
        # Update context with server status
        context.server_status = server_status
        context.warning_count = warning_count
        
        # Check if this marks output parameters (PS_OUT_PARAMS flag)
        is_output_parameters = (server_status & constants.STATUS.PS_OUT_PARAMS) != 0
        data.release()
        
        return EofPacket(
            warning_count=warning_count,
            server_status=server_status,
            is_output_parameters=is_output_parameters
        )
    