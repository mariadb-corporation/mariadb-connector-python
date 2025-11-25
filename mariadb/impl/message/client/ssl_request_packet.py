# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

import struct
from mariadb.impl.client.context import Context
from ..client_message import ClientMessage

class SslRequestPacket(ClientMessage):
    """
    SSL request packet for MySQL/MariaDB SSL handshake
    
    See https://mariadb.com/kb/en/connection/#sslrequest-packet
    """
    
    def __init__(self, client_capabilities: int):
        """Initialize SSL request packet with client capabilities"""
        self.client_capabilities: int = client_capabilities

    def payload(self, context: Context) -> bytes:
        # Pack SSL request packet: client_capabilities (4) + max_packet_size (4) + charset (1) + reserved (19) + extended_capabilities (4) = 32 bytes
        return struct.pack(
            '<IIB19sI',  # Little-endian: uint32, uint32, byte, 19 bytes, uint32
            self.client_capabilities & 0xFFFFFFFF,  # Client capabilities (4 bytes)
            1024 * 1024 * 1024,  # Max packet size (4 bytes)
            45,  # Charset (1 byte)
            b'\x00' * 19,  # Reserved bytes (19 bytes)
            (self.client_capabilities >> 32) & 0xFFFFFFFF  # MariaDB extended capabilities (4 bytes)
        )

    def is_binary(self) -> bool:
        return False
    
    def type(self) -> str:
        return "SSL_REQUEST"
        