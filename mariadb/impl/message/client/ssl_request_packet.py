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


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...client.socket.stream import Stream
    from mariadb.impl.client.context import Context

from ...client.socket.payload_writer import PayloadWriter
from ..client_message import ClientMessage
from mariadb_shared import constants


class SslRequestPacket(ClientMessage):
    """
    SSL request packet for MySQL/MariaDB SSL handshake
    
    Equivalent to the Java SslRequestPacket class.
    """
    
    def __init__(self, client_capabilities: int):
        """
        Initialize SSL request packet
        
        Args:
            client_capabilities: Client capabilities flags
            exchange_charset: Connection charset to set
        """
        self.client_capabilities: int = client_capabilities
    
    def encode(self, stream: 'Stream', context: 'Context') -> None:
        """
        Encode SSL request packet using payload-based approach
        
        Args:
            stream: Stream to send payload through
            context: Connection context
        """
        # Build payload
        writer = PayloadWriter()
        
        # Write SSL request packet content
        writer.write_int(self.client_capabilities & 0xFFFFFFFF)  # Client capabilities (4 bytes)
        writer.write_int(1024 * 1024 * 1024)  # Max packet size (4 bytes)
        writer.write_byte(45)  # Charset (1 byte)
        writer.write_bytes(b'\x00' * 19)  # Reserved bytes (19 bytes)
        writer.write_int((self.client_capabilities >> 32) & 0xFFFFFFFF)  # MariaDB extended capabilities (4 bytes)
        
        # Send payload through stream (don't reset sequence - continue from handshake)
        stream.send_payload(writer.get_payload(), "SSL_REQUEST", reset_sequence=False)

    def is_binary(self) -> bool:
        return False