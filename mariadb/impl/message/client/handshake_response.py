# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Handshake Response packet for MariaDB authentication

Equivalent to the Java HandshakeResponse class.
"""

import hashlib
from ...client.context import Context
from ...client.socket.payload_writer import PayloadWriter
from ...connection_attributes import get_default_connection_attributes, encode_connection_attributes
from ..client_message import ClientMessage
from ...configuration import Configuration
from mariadb_shared.constants import CAPABILITY


class HandshakeResponse(ClientMessage):
    """
    Handshake response packet for MySQL authentication
    
    Equivalent to the Java HandshakeResponse class.
    """
    
    
    def __init__(self, configuration: Configuration, context: Context):
        """Initialize handshake response with configuration and context"""
        self.configuration = configuration
        self.context = context
        

    def encode(self, context: Context) -> bytearray:
        """Encode handshake response packet with capabilities, auth, and connection attributes"""
        # Build payload
        writer = PayloadWriter()
        
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
        from ...plugin.authentication.native_password_plugin import NativePasswordPlugin
        auth_response = NativePasswordPlugin.encrypt_password(self.configuration.password, context.auth_data)
        if auth_response:
            if context.server_capabilities & CAPABILITY.SECURE_CONNECTION:
                # Length-encoded auth response
                writer.write_byte(len(auth_response))
                writer.write_bytes(auth_response)
            else:
                writer.write_bytes(auth_response)
                writer.write_byte(0x00)
        else:
            writer.write_byte(0)
        
        # Database name (if specified)
        if self.configuration.database and (context.client_capabilities & CAPABILITY.CONNECT_WITH_DB):
            writer.write_null_terminated_string(self.configuration.database)
        
        # Authentication plugin name
        if (context.client_capabilities & CAPABILITY.PLUGIN_AUTH):
            writer.write_null_terminated_string("mysql_native_password")
        
        # Connection attributes
        if (context.client_capabilities & CAPABILITY.CONNECT_ATTRS):
            
            # Get default attributes
            host = self.configuration.host if hasattr(self.configuration, 'host') else None
            default_attrs = get_default_connection_attributes(host=host)
            
            # Merge with user-provided attributes if any
            #if hasattr(self.configuration, 'connect_attrs') and self.configuration.connect_attrs:
            #    default_attrs.update(self.configuration.connect_attrs)
            
            # Encode attributes
            attr_data = encode_connection_attributes(default_attrs)
            writer.write_length_encoded_int(len(attr_data))
            writer.write_bytes(attr_data)

        # Send payload through stream (don't reset sequence - continue from handshake)
        return writer.get_payload()
    
    def _calculate_auth_response(self, context: Context) -> bytes:
        """Calculate authentication response"""
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
    
    def is_binary(self) -> bool:
        return False


    def type(self) -> str:
        return "HANDSHAKE_RESPONSE"                   