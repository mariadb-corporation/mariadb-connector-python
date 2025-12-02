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
    __slots__ = ('client_capabilities',)
    
    def __init__(self, client_capabilities: int):
        """Initialize SSL request packet with client capabilities"""
        self.client_capabilities: int = client_capabilities

    def payload(self, context: Context) -> bytearray:
        # Pack SSL request packet: header (4) + client_capabilities (4) + max_packet_size (4) + charset (1) + reserved (19) + extended_capabilities (4) = 36 bytes
        return bytearray(struct.pack(
            '<4sIIB19sI',  # Little-endian: 4 bytes header, uint32, uint32, byte, 19 bytes, uint32
            b'\x00\x00\x00\x00',  # Packet header (will be overwritten by write_payload)
            self.client_capabilities & 0xFFFFFFFF,  # Lower 32 bits of capabilities
            1024 * 1024 * 1024,  # max_packet_size (1GB)
            45,  # charset (utf8mb4_general_ci)
            b'\x00' * 19,  # reserved (19 bytes of zeros)
            (self.client_capabilities >> 32) & 0xFFFFFFFF  # Upper 32 bits of capabilities (extended capabilities)
        ))

    def is_binary(self) -> bool:
        return False
    
    def type(self) -> str:
        return "SSL_REQUEST"
        