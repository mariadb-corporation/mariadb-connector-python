# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

import hashlib

from ...client.context import Context
from ...connection_attributes import get_default_connection_attributes, encode_connection_attributes
from ..client_message import ClientMessage
from ..payload_writer import PayloadWriter
from ...configuration import Configuration
from mariadb_shared.constants import CAPABILITY

class HandshakeResponse(ClientMessage):
    """
    Handshake response packet for MySQL authentication
    """
    __slots__ = ('configuration', 'context')
    
    
    def __init__(self, configuration: Configuration, context: Context):
        """Initialize handshake response with configuration and context"""
        self.configuration = configuration
        self.context = context
        
    def payload(self, context: Context) -> bytearray:
        """Generate handshake response payload as bytes"""
        stream = PayloadWriter()
        # Client capabilities (4 bytes)
        stream.write_uint32(context.client_capabilities & 0xFFFFFFFF)
        
        # Max packet size (4 bytes)
        stream.write_uint32(1024 * 1024 * 1024)
        stream.write_byte(45)
        
        # Reserved (19 bytes of zeros) - use extend to avoid 19 individual appends
        stream.write_bytes(b'\x00' * 19)

        # Client extended capabilities (4 bytes)
        stream.write_uint32(context.client_capabilities >> 32)

        # Username (null-terminated)
        if self.configuration.user:
            stream.write_string(self.configuration.user)
            stream.write_byte(0x00)
        else:
            stream.write_byte(0x00)  # Empty username

        # Authentication response
        from ...plugin.authentication.native_password_plugin import NativePasswordPlugin
        auth_response = NativePasswordPlugin.encrypt_password(self.configuration.password, context.auth_data)
        if auth_response:
            if context.server_capabilities & CAPABILITY.SECURE_CONNECTION:
                # Length-encoded auth response
                stream.write_byte(len(auth_response))
                stream.write_bytes(auth_response)
            else:
                stream.write_bytes(auth_response)
                stream.write_byte(0x00)
        else:
            stream.write_byte(0x00)
        
        # Database name (if specified)
        if self.configuration.database and (context.client_capabilities & CAPABILITY.CONNECT_WITH_DB):
            stream.write_string(self.configuration.database)
            stream.write_byte(0x00)
            context.database = self.configuration.database
        
        # Authentication plugin name
        if (context.client_capabilities & CAPABILITY.PLUGIN_AUTH):
            stream.write_string("mysql_native_password")
            stream.write_byte(0x00)
        
        # Connection attributes
        if (context.client_capabilities & CAPABILITY.CONNECT_ATTRS):
            
            # Get default attributes
            host = self.configuration.host if hasattr(self.configuration, 'host') else None
            default_attrs = get_default_connection_attributes(host=host)
            
            # Encode attributes
            attr_data = encode_connection_attributes(default_attrs)
            stream.write_length_encoded_int(len(attr_data))
            stream.write_bytes(attr_data)
        
        return stream.get_payload()
    
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