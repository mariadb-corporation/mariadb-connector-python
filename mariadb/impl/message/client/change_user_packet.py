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
COM_CHANGE_USER packet implementation

Changes the user and optionally the database for the current connection.
"""

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ...client.socket.stream.stream import Stream
    from ...client.context import Context

from ..client_message import ClientMessage
from ...client.socket.payload_writer import PayloadWriter
from ...connection_attributes import get_default_connection_attributes, encode_connection_attributes
from ....plugin.authentication.native_password_plugin import NativePasswordPlugin
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
        """
        Initialize COM_CHANGE_USER packet
        
        Args:
            username: New username
            password: New password (optional)
            database: New default database (optional)
            charset_collation: Character set collation ID
            auth_plugin: Authentication plugin name
            auth_response: Pre-computed authentication response
            connect_attrs: Connection attributes
        """
        self.username = username or ""
        self.password = password
        self.database = database or ""
        self.charset_collation = charset_collation
        self.connect_attrs = connect_attrs or {}
    
    def encode(self, stream: 'Stream', context: 'Context') -> None:
        """
        Encode COM_CHANGE_USER packet
        
        Args:
            stream: Stream to send payload through
            context: Connection context
        
        Packet format:
        - int<1>: 0x11 (COM_CHANGE_USER)
        - string: username (null-terminated)
        - If CLIENT_SECURE_CONNECTION:
            - int<1>: length of auth response
            - string: auth response (not null-terminated)
        - Else:
            - string: auth response (null-terminated)
        - string: database name (null-terminated)
        - int<2>: charset collation
        - If CLIENT_PLUGIN_AUTH:
            - string: auth plugin name (null-terminated)
        - If CLIENT_CONNECT_ATTRS:
            - int: size of connection attributes
            - Loop: key-value pairs (length-encoded strings)
        """
        # Build payload
        writer = PayloadWriter()
        
        # Command byte
        writer.write_byte(0x11)  # COM_CHANGE_USER
        
        # Username (null-terminated string)
        writer.write_null_terminated_string(self.username)
        
        # Authentication response
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
        stream.send_payload(writer.get_payload(), "COM_CHANGE_USER")
        
    def is_binary(self) -> bool:
        return False