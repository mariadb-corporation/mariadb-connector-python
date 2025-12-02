# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
COM_CHANGE_USER packet implementation

Changes the user and optionally the database for the current connection.
"""

from typing import Optional
from ...client.context import Context
from ..client_message import ClientMessage
from ..payload_writer import PayloadWriter
from ...connection_attributes import get_default_connection_attributes, encode_connection_attributes
from mariadb_shared.constants import CAPABILITY

class ChangeUserPacket(ClientMessage):
    """
    COM_CHANGE_USER packet
    
    Changes the user and optionally the database for the current connection.
    Resets the connection state (variables, temp tables, prepared statements, etc.)
    """
    __slots__ = ('username', 'password', 'database', 'charset_collation', 'connect_attrs')
    
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
    
    def payload(self, context: Context) -> bytearray:
        stream = PayloadWriter()
        # Command byte
        stream.write_byte(0x11)  # COM_CHANGE_USER
        
        # Username (null-terminated string)
        stream.write_string(self.username)
        stream.write_byte(0x00)

        # Authentication response
        from ...plugin.authentication.native_password_plugin import NativePasswordPlugin
        auth_response = NativePasswordPlugin.encrypt_password(self.password, context.auth_data)        
        if auth_response:
            if context.client_capabilities & CAPABILITY.SECURE_CONNECTION:
                # Length-encoded auth response
                stream.write_byte(len(auth_response))
                stream.write_bytes(auth_response)
            else:
                stream.write_bytes(auth_response)
                stream.write_byte(0x00)
        else:
            stream.write_byte(0x00)
        
        # Database name (null-terminated string)
        if context.client_capabilities & CAPABILITY.CONNECT_WITH_DB:
            stream.write_string(self.database)
            stream.write_byte(0x00)
        
        # Character set collation (2 bytes)
        stream.write_uint16(self.charset_collation)
        
        # Authentication plugin name (if supported)
        if context.client_capabilities & CAPABILITY.PLUGIN_AUTH:
            stream.write_string("mysql_native_password\0")
        
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
            stream.write_length_encoded_int(len(attr_data))
            stream.write_bytes(attr_data)
        
        return stream.get_payload()

    def is_binary(self) -> bool:
        return False

    def type(self) -> str:
        return "COM_CHANGE_USER"        