# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from typing import TYPE_CHECKING
from mariadb.impl.client.context import Context
from ..client_message import ClientMessage
if TYPE_CHECKING:
    from ...client.socket.stream import SyncStream

class SslRequestPacket(ClientMessage):
    """
    SSL request packet for MySQL/MariaDB SSL handshake
    
    See https://mariadb.com/kb/en/connection/#sslrequest-packet
    """
    
    def __init__(self, client_capabilities: int):
        """Initialize SSL request packet with client capabilities"""
        self.client_capabilities: int = client_capabilities

    def process(self, stream: 'SyncStream', context: Context) -> None:
        stream.write_uint32(self.client_capabilities & 0xFFFFFFFF)  # Client capabilities (4 bytes)
        stream.write_uint32(1024 * 1024 * 1024)  # Max packet size (4 bytes)
        stream.write_byte(45)  # Charset (1 byte)
        stream.write_bytes(b'\x00' * 19)  # Reserved bytes (19 bytes)
        stream.write_uint32((self.client_capabilities >> 32) & 0xFFFFFFFF)  # MariaDB extended capabilities (4 bytes)

    def is_binary(self) -> bool:
        return False
    
    def type(self) -> str:
        return "SSL_REQUEST"
        