#
# Copyright (C) 2020-2021 Georg Richter and MariaDB Corporation AB

# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Library General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.

# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Library General Public License for more details.

# You should have received a copy of the GNU Library General Public
# License along with this library; if not see <http://www.gnu.org/licenses>
# or write to the Free Software Foundation, Inc.,
# 51 Franklin St., Fifth Floor, Boston, MA 02110, USA
#

"""
SSL Request packet for MariaDB SSL handshake

Equivalent to the Java SslRequestPacket class.
See https://mariadb.com/kb/en/connection/#sslrequest-packet
"""


from mariadb.src.impl.client.context import Context
from mariadb.src.impl.client.socket.packet_writer import PacketWriter
from ..client_message import ClientMessage
from .... import constants


class SslRequestPacket(ClientMessage):
    """
    SSL request packet for MySQL/MariaDB SSL handshake
    
    Equivalent to the Java SslRequestPacket class.
    """
    
    def __init__(self, client_capabilities: int, exchange_charset: int):
        """
        Initialize SSL request packet
        
        Args:
            client_capabilities: Client capabilities flags
            exchange_charset: Connection charset to set
        """
        self.client_capabilities: int = client_capabilities
        self.exchange_charset: int = exchange_charset
    
    def encode(self, writer: PacketWriter, context: Context) -> None:
        """
        Encode SSL request packet using payload-based approach
        
        Args:
            writer: Packet writer
            context: Connection context
        """
        # Start payload mode (don't reset sequence - continue from handshake)
        writer.start_payload(reset_sequence=False)
        
        # Write SSL request packet content
        writer.write_int(self.client_capabilities & 0xFFFFFFFF)  # Client capabilities (4 bytes)
        writer.write_int(1024 * 1024 * 1024)  # Max packet size (4 bytes)
        writer.write_byte(self.exchange_charset)  # Charset (1 byte)
        writer.write_bytes(b'\x00' * 19)  # Reserved bytes (19 bytes)
        writer.write_int((self.client_capabilities >> 32) & 0xFFFFFFFF)  # MariaDB extended capabilities (4 bytes)
        
        # Send packet with automatic header and chunking
        writer.send_payload("SSL_REQUEST")
    
    def description(self) -> str:
        """
        Get message description for debugging
        
        Returns:
            Message description
        """
        return f"SSL_REQUEST(capabilities=0x{self.client_capabilities:x}, charset={self.exchange_charset})"
