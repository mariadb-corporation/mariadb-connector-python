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
Handshake Response packet for MariaDB authentication

Equivalent to the Java HandshakeResponse class.
"""

import hashlib
from typing import Any, Optional

from mariadb.impl.client.context import Context
from mariadb.impl.client.socket.packet_writer import PacketWriter
from ..client_message import ClientMessage
from ...configuration import Configuration
from mariadb_shared import constants


class HandshakeResponse(ClientMessage):
    """
    Handshake response packet for MySQL authentication
    
    Equivalent to the Java HandshakeResponse class.
    """
    
    
    def __init__(self, configuration: Configuration, context: Context):
        """
        Initialize handshake response
        
        Args:
            configuration: Connection configuration
            context: Connection context
        """
        self.configuration = configuration
        self.context = context
        

    def encode(self, writer: PacketWriter, context: Context) -> None:
        """
        Encode handshake response packet using payload-based approach
        
        Args:
            writer: Packet writer
            context: Connection context
            
        Raises:
            IOError: If encoding fails
        """
        # Start payload mode (don't reset sequence - continue from handshake)
        writer.start_payload(reset_sequence=False)
        
        # Client capabilities (4 bytes)
        writer.write_int(context.client_capabilities & 0xFFFFFFFF)
        
        # Max packet size (4 bytes)
        writer.write_int(1024 * 1024 * 1024)
        writer.write_byte(45)
        
        # Reserved (23 bytes of zeros)
        for _ in range(19):
            writer.write_byte(0)

        # Client extended capabilities (4 bytes)
        writer.write_int(context.client_capabilities >> 32)

        # Username (null-terminated)
        if self.configuration.user:
            writer.write_null_terminated_string(self.configuration.user)
        else:
            writer.write_byte(0)  # Empty username
        
        # Authentication response
        if self.configuration.password:
            auth_response = self._calculate_auth_response(context)
            writer.write_byte(len(auth_response))
            writer.write_bytes(auth_response)
        else:
            writer.write_byte(0)  # No password
        
        # Database name (if specified)
        if self.configuration.database and (context.client_capabilities & constants.CAPABILITY.CONNECT_WITH_DB):
            writer.write_null_terminated_string(self.configuration.database)
        
        # Authentication plugin name
        if (context.client_capabilities & constants.CAPABILITY.PLUGIN_AUTH):
            writer.write_null_terminated_string("mysql_native_password")
        
        if (context.client_capabilities & constants.CAPABILITY.CONNECT_ATTRS):
            writer.write_byte(0)  # TODO

        # Send packet with automatic header and chunking
        writer.send_payload("COM_HANDSHAKE_RESPONSE")
    
    def _calculate_auth_response(self, context: Context) -> bytes:
        """
        Calculate authentication response using mysql_native_password
        Args:
            context: Connection context
            
        Returns:
            Authentication response bytes
        """
        if not self.configuration.password:
            return b''
        
        # Get auth data from context (scramble)
        auth_data = getattr(context, 'auth_data', b'')
        if not auth_data or len(auth_data) < 20:
            raise IOError("Invalid or missing authentication data from server")
        
        # MySQL native password authentication
        # SHA1(password) XOR SHA1(scramble + SHA1(SHA1(password)))
        
        password_bytes = self.configuration.password.encode('utf-8')
        
        # SHA1(password)
        sha1_password = hashlib.sha1(password_bytes).digest()
        
        # SHA1(SHA1(password))
        sha1_sha1_password = hashlib.sha1(sha1_password).digest()
        
        # SHA1(scramble + SHA1(SHA1(password)))
        scramble_hash = hashlib.sha1(auth_data + sha1_sha1_password).digest()
        
        # XOR SHA1(password) with scramble_hash
        result = bytes(a ^ b for a, b in zip(sha1_password, scramble_hash))
        
        return result
    
    def description(self) -> str:
        """Get message description"""
        return f"HandshakeResponse(user={self.configuration.user}, database={self.configuration.database})"
    
    def can_be_redone(self) -> bool:
        """Handshake response cannot be redone"""
        return False
