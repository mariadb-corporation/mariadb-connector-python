# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from mariadb.impl.client.context import Context

from ...client.socket.payload_writer import PayloadWriter
from ..client_message import ClientMessage


class SslRequestPacket(ClientMessage):
    """
    SSL request packet for MySQL/MariaDB SSL handshake
    
    See https://mariadb.com/kb/en/connection/#sslrequest-packet
    """
    
    def __init__(self, client_capabilities: int):
        """Initialize SSL request packet with client capabilities"""
        self.client_capabilities: int = client_capabilities
    
    def encode(self, context: Context) -> bytearray:
        """Encode SSL request packet with capabilities and charset"""
        writer = PayloadWriter()
        writer.write_int(self.client_capabilities & 0xFFFFFFFF)  # Client capabilities (4 bytes)
        writer.write_int(1024 * 1024 * 1024)  # Max packet size (4 bytes)
        writer.write_byte(45)  # Charset (1 byte)
        writer.write_bytes(b'\x00' * 19)  # Reserved bytes (19 bytes)
        writer.write_int((self.client_capabilities >> 32) & 0xFFFFFFFF)  # MariaDB extended capabilities (4 bytes)
        return writer.get_payload()

    def is_binary(self) -> bool:
        return False
    
    def type(self) -> str:
        return "SSL_REQUEST"
        