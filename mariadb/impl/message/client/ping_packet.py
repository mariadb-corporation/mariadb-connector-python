# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Ping packet for MariaDB connection testing

Equivalent to the Java PingPacket class.
"""

from ...client.context import Context

from ..client_message import ClientMessage
from ...client.socket.payload_writer import PayloadWriter


class PingPacket(ClientMessage):
    """
    Ping packet for connection testing
    
    Equivalent to the Java PingPacket class.
    """
    
    COM_PING = 0x0E
    
    def __init__(self):
        """Initialize COM_PING packet"""
        pass
        
    def encode(self, context: Context) -> bytearray:
        """Encode COM_PING packet"""
        return bytearray([PingPacket.COM_PING])
    
    def is_binary(self) -> bool:
        return False

    def type(self) -> str:
        return "COM_PING"                   