# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
COM_CHANGE_USER packet implementation

Changes the user and optionally the database for the current connection.
"""

from typing import Optional
from ...client.context import Context

from ..client_message import ClientMessage
from ...client.socket.payload_writer import PayloadWriter
from ...connection_attributes import get_default_connection_attributes, encode_connection_attributes
from mariadb_shared.constants import CAPABILITY


class ChangeUserPacket(ClientMessage):
    """
    COM_CHANGE_USER packet
    
    Changes the user and optionally the database for the current connection.
    Resets the connection state (variables, temp tables, prepared statements, etc.)
    """
    
    def __init__(self, 
                 username: str,
                 password: Optional[str] = None,
                 database: Optional[str] = None,
                 charset_collation: int = 33,  # utf8mb4_general_ci
                 connect_attrs: Optional[dict] = None):
        """Initialize COM_CHANGE_USER packet with username, password, database, and charset"""
        self.username = username or ""
        self.password = password
        self.database = database or ""
        self.charset_collation = charset_collation
        self.connect_attrs = connect_attrs or {}
    
    def encode(self, context: Context) -> bytearray:
        """Encode COM_CHANGE_USER packet with username, auth response, database, charset, and attributes"""
        # Build payload
        writer = PayloadWriter()
        
        # Command byte
        writer.write_byte(0x11)  # COM_CHANGE_USER
        
        # Username (null-terminated string)
        writer.write_null_terminated_string(self.username)
        
        # Authentication response
        from ...plugin.authentication.native_password_plugin import NativePasswordPlugin
        auth_response = NativePasswordPlugin.encrypt_password(self.password, context.auth_data)        
        if auth_response:
            if context.client_capabilities & CAPABILITY.SECURE_CONNECTION:
                # Length-encoded auth response
                writer.write_byte(len(auth_response))
                writer.write_bytes(auth_response)
            else:
                writer.write_bytes(auth_response)
                writer.write_byte(0x00)
        else:
            writer.write_byte(0)
        
        # Database name (null-terminated string)
        if context.client_capabilities & CAPABILITY.CONNECT_WITH_DB:
            writer.write_null_terminated_string(self.database)
            context.database = self.database

        
        # Character set collation (2 bytes)
        writer.write_short(self.charset_collation)
        
        # Authentication plugin name (if supported)
        if context.client_capabilities & CAPABILITY.PLUGIN_AUTH:
            writer.write_null_terminated_string("mysql_native_password")
        
        # Connection attributes (if supported)
        if context.client_capabilities & CAPABILITY.CONNECT_ATTRS:
            
            # Get default attributes
            host = context.host if hasattr(context, 'host') else None
            default_attrs = get_default_connection_attributes(host=host)
            
            # Merge with user-provided attributes (user attrs override defaults)
            if self.connect_attrs:
                default_attrs.update(self.connect_attrs)
            
            # Encode attributes
            attr_data = encode_connection_attributes(default_attrs)
            writer.write_length_encoded_int(len(attr_data))
            writer.write_bytes(attr_data)
        return writer.get_payload()
        
    def is_binary(self) -> bool:
        return False

    def type(self) -> str:
        return "COM_CHANGE_USER"        