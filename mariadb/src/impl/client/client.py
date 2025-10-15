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
Standard Client implementation for MariaDB connections

Equivalent to the Java StandardClient class.
"""

import socket
import ssl
import sys
import threading
import time
from typing import List, Optional, Any, Dict, Union, Tuple
from .context import Context
from .socket.packet_reader import PacketReader
from .socket.packet_writer import PacketWriter
from .socket.mutable_int import MutableInt
from ..configuration import Configuration
from ..host_address import HostAddress
from ..message.client_message import ClientMessage
from ..message.client.handshake_response import HandshakeResponse
from ..message.client.query_packet import QueryPacket
from ..message.client.ping_packet import PingPacket
from ..completion import Completion
from ..export.exception_factory import ExceptionFactory
from ...exceptions import OperationalError, DatabaseError
from ... import constants


class Client:
    """
    Standard client implementation for MariaDB connections
    
    Equivalent to the Java StandardClient class.
    """
    
    # MariaDB replication hack prefix
    MARIADB_RPL_HACK_PREFIX = "5.5.5-"
    
    # Session tracking constants
    SESSION_TRACK_SYSTEM_VARIABLES = 0
    SESSION_TRACK_SCHEMA = 1
    SESSION_TRACK_STATE_CHANGE = 2
    SESSION_TRACK_GTIDS = 3
    SESSION_TRACK_TRANSACTION_CHARACTERISTICS = 4
    SESSION_TRACK_TRANSACTION_STATE = 5
    
    def __init__(self, configuration: Configuration, host_address: HostAddress) -> None:
        """
        Initialize standard client
        
        Args:
            configuration: Connection configuration
            host_address: Host address to connect to
        """
        self.configuration = configuration
        self.host_address = host_address
        
        
        self.socket: Optional[socket.socket] = None
        self.reader: Optional[PacketReader] = None
        self.writer: Optional[PacketWriter] = None
        self.ssl_wrapper = None
        self.sequence = MutableInt(0)  # Shared sequence number
        self.context: Optional[Context] = None
        self.exception_factory = ExceptionFactory()
        self.closed = False
        self.socket_timeout = configuration.socket_timeout
        self.connect_timeout = configuration.connect_timeout
        self.lock = threading.RLock()
        
        # Connection state
        self.connected = False
        self.read_only = configuration.read_only
        
    def connect(self) -> None:
        """
        Establish connection to MariaDB server with host failover support
        
        Raises:
            OperationalError: If connection fails to all hosts
        """
        with self.lock:
            if self.connected:
                return
            
            # Get list of hosts to try
            hosts = self.configuration.get_hosts()
            last_exception = None
            
            for host, port in hosts:
                try:
                    # Update host address for this attempt
                    self.host_address.host = host
                    self.host_address.port = port
                    
                    self._create_socket()
                    self._perform_handshake()
                    self.connected = True
                    return  # Success!
                    
                except Exception as e:
                    last_exception = e
                    self._cleanup_connection()
                    # Continue to next host
                    continue
            
            # All hosts failed
            if last_exception:
                raise OperationalError(f"Connection failed to all hosts: {last_exception}")
            else:
                raise OperationalError("Connection failed: No hosts to try")
    
    def _create_socket(self) -> None:
        """
        Create and configure socket connection
        
        Raises:
            OperationalError: If socket creation fails
        """
        try:
            if self.configuration.socket_path:
                # Unix socket connection
                self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.socket.settimeout(self.connect_timeout / 1000.0)
                self.socket.connect(self.configuration.socket_path)
            else:
                # TCP connection
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.settimeout(self.connect_timeout / 1000.0)
                
                # Set socket options
                self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                
                # Connect to server
                address = (self.host_address.host, self.host_address.port)
                self.socket.connect(address)
            
            # Set socket timeout for operations
            self.socket.settimeout(self.socket_timeout / 1000.0)
            
            # Wrap socket with SocketStream for protocol handling
            from .socket.stream.socket_stream import SocketStream
            stream = SocketStream(self.socket)
            
            # Create reader and writer with shared sequence number
            self.reader = PacketReader(stream=stream, debug=self.configuration.debug)
            self.writer = PacketWriter(stream=stream, debug=self.configuration.debug)
            
        except Exception as e:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
            raise OperationalError(f"Failed to create socket: {e}")
    
    def _perform_handshake(self) -> None:
        """
        Perform MySQL handshake protocol
        
        Raises:
            OperationalError: If handshake fails
        """
        try:
            # Read initial handshake packet from server
            handshake_packet = self.reader.read_packet()
            
            # Parse handshake packet and create context
            self.context = self._parse_handshake(handshake_packet)
            client_capabilities = self._calculate_client_capabilities()

            # Handle SSL if enabled
            if self.configuration.ssl:
                self._handle_ssl_connection(client_capabilities)
            
            # Store client capabilities in context for later use
            self.context.client_capabilities = client_capabilities
            self.context.eof_deprecated = bool(client_capabilities & constants.CAPABILITY.DEPRECATE_EOF)
            self.context.extended_metadata = bool(client_capabilities & constants.CAPABILITY.EXTENDED_METADATA)

            # Create and send handshake response
            response = HandshakeResponse(self.configuration, self.context)
            self._send_message(response)
            
            # Handle authentication (may involve multiple rounds)
            self._handle_authentication()
            
            # Enable compression if negotiated
            self._enable_compression_if_negotiated()
            
            # Execute init command if specified
            if self.configuration.init_command:
                self._execute_init_command()
                
        except Exception as e:
            self.close()
            raise OperationalError(f"Connection failed: {e}")
    
    def _parse_handshake(self, packet: bytes) -> Context:
        """
        Parse initial handshake packet from server
        
        Args:
            packet: Handshake packet data
            
        Returns:
            Connection context
            
        Raises:
            OperationalError: If packet is invalid
        """
        if len(packet) < 10:
            raise OperationalError("Invalid handshake packet: too short")
        
        import struct
        pos = 0
        
        # Protocol version (1 byte)
        protocol_version = packet[pos]
        pos += 1
        
        if protocol_version != 0x0a:
            raise OperationalError(f"Unexpected initial handshake protocol value [{protocol_version}]")
        
        # Server version (null-terminated string)
        version_end = packet.find(0, pos)
        if version_end == -1:
            raise OperationalError("Invalid handshake packet: missing server version")
        
        server_version = packet[pos:version_end].decode('utf-8')
        pos = version_end + 1
        
        # Thread ID / Connection ID (4 bytes)
        if pos + 4 > len(packet):
            raise OperationalError("Invalid handshake packet: missing thread ID")
        
        thread_id = struct.unpack('<I', packet[pos:pos + 4])[0]
        pos += 4
        
        # Auth plugin data part 1 - seed1 (8 bytes)
        if pos + 8 > len(packet):
            raise OperationalError("Invalid handshake packet: missing seed1")
        
        seed1 = packet[pos:pos + 8]
        pos += 8
        
        # Skip filler (1 byte, should be 0x00)
        if pos >= len(packet):
            raise OperationalError("Invalid handshake packet: missing filler")
        pos += 1
        
        # Server capabilities first 2 bytes
        if pos + 2 > len(packet):
            raise OperationalError("Invalid handshake packet: missing server capabilities")
        
        server_capabilities_2_first_bytes = struct.unpack('<H', packet[pos:pos + 2])[0]
        pos += 2
        
        # Default collation (1 byte)
        if pos >= len(packet):
            raise OperationalError("Invalid handshake packet: missing default collation")
        
        default_collation = packet[pos]
        pos += 1
        
        # Server status (2 bytes)
        if pos + 2 > len(packet):
            raise OperationalError("Invalid handshake packet: missing server status")
        
        server_status = struct.unpack('<H', packet[pos:pos + 2])[0]
        pos += 2
        
        # Server capabilities 4 first bytes (combine lower and upper 2 bytes)
        server_capabilities_upper = 0
        if pos + 2 <= len(packet):
            server_capabilities_upper = struct.unpack('<H', packet[pos:pos + 2])[0]
            pos += 2
        
        server_capabilities_4_first_bytes = server_capabilities_2_first_bytes + (server_capabilities_upper << 16)
        
        # Salt length calculation
        salt_length = 0
        if (server_capabilities_4_first_bytes & constants.CAPABILITY.PLUGIN_AUTH) != 0:
            if pos < len(packet):
                salt_length = max(12, packet[pos] - 9)
                pos += 1
            else:
                raise OperationalError("Invalid handshake packet: missing salt length")
        else:
            # Skip 1 byte
            if pos < len(packet):
                pos += 1
        
        # Skip reserved bytes (6 bytes)
        if pos + 6 <= len(packet):
            pos += 6
        else:
            # Handle shorter packets gracefully
            pos = min(pos + 6, len(packet))
        
        # MariaDB additional capabilities (4 bytes)
        # Filled only if MariaDB server 10.2+
        mariadb_additional_capacities = 0
        if pos + 4 <= len(packet):
            mariadb_additional_capacities = struct.unpack('<I', packet[pos:pos + 4])[0]
            pos += 4
        
        # Handle seed2 and combine with seed1
        seed = seed1
        if (server_capabilities_4_first_bytes & constants.CAPABILITY.SECURE_CONNECTION) != 0:
            if salt_length > 0:
                # Read salt_length bytes for seed2
                if pos + salt_length <= len(packet):
                    seed2 = packet[pos:pos + salt_length]
                    pos += salt_length
                else:
                    # Read what's available
                    seed2 = packet[pos:]
                    pos = len(packet)
            else:
                # Read null-terminated seed2
                seed2_end = packet.find(0, pos)
                if seed2_end != -1:
                    seed2 = packet[pos:seed2_end]
                    pos = seed2_end + 1
                else:
                    seed2 = packet[pos:]
                    pos = len(packet)
            
            # Combine seed1 and seed2
            seed = seed1 + seed2
        
        # Skip null terminator if present
        if pos < len(packet) and packet[pos] == 0:
            pos += 1
        
        # Check for MariaDB 10.x replication hack, remove fake prefix if needed
        server_mariadb = False
        if server_version.startswith(self.MARIADB_RPL_HACK_PREFIX):
            server_mariadb = True
            server_version = server_version[len(self.MARIADB_RPL_HACK_PREFIX):]
        else:
            server_mariadb = "MariaDB" in server_version
        
        # Calculate final server capabilities
        # Since MariaDB 10.2
        if (server_capabilities_4_first_bytes & constants.CAPABILITY.MYSQL) == 0:
            server_capabilities = (server_capabilities_4_first_bytes & 0xffffffff) + (mariadb_additional_capacities << 32)
            server_mariadb = True
        else:
            server_capabilities = server_capabilities_4_first_bytes & 0xffffffff
        
        # Auth plugin type (null-terminated string)
        auth_plugin_name = None
        if (server_capabilities_4_first_bytes & constants.CAPABILITY.PLUGIN_AUTH) != 0:
            if pos < len(packet):
                plugin_end = packet.find(0, pos)
                if plugin_end != -1:
                    auth_plugin_name = packet[pos:plugin_end].decode('utf-8')
                else:
                    auth_plugin_name = packet[pos:].decode('utf-8')
        
        # Create context with parsed information
        context = Context()
        context.server_version = server_version
        context.parse_server_version(server_version)
        context.connection_id = thread_id
        context.protocol_version = protocol_version
        context.server_capabilities = server_capabilities
        context.server_status = server_status
        context.auth_plugin = auth_plugin_name
        context.auth_data = seed
        
        # Set MariaDB flag in version
        context.version.is_mariadb = server_mariadb
        
        
        return context
    

    def _calculate_client_capabilities(self) -> int:
        """
        Calculate client capabilities based on configuration
        
        Returns:
            Client capabilities flags
        """
        capabilities = (
            constants.CAPABILITY.LONG_PASSWORD |
            constants.CAPABILITY.FOUND_ROWS |
            constants.CAPABILITY.LONG_FLAG |
            constants.CAPABILITY.PROTOCOL_41 |
            constants.CAPABILITY.TRANSACTIONS |
            constants.CAPABILITY.SECURE_CONNECTION |
            constants.CAPABILITY.MULTI_STATEMENTS |
            constants.CAPABILITY.MULTI_RESULTS |
            constants.CAPABILITY.PS_MULTI_RESULTS |
            constants.CAPABILITY.PLUGIN_AUTH |
            constants.CAPABILITY.CONNECT_ATTRS |
            constants.CAPABILITY.PLUGIN_AUTH_LENENC_CLIENT_DATA |
            constants.CAPABILITY.CAN_HANDLE_EXPIRED_PASSWORDS |
            constants.CAPABILITY.SESSION_TRACKING |
            constants.CAPABILITY.DEPRECATE_EOF |
            constants.CAPABILITY.BULK_OPERATIONS |
            constants.CAPABILITY.EXTENDED_METADATA |
            constants.CAPABILITY.CACHE_METDATA
        )
        
        # Add database capability if database specified and server supports it
        if self.configuration.database:
            capabilities |= constants.CAPABILITY.CONNECT_WITH_DB
        
        # Add SSL capability if SSL enabled and server supports it
        if self.configuration.ssl:
            capabilities |= constants.CAPABILITY.SSL
        
        # Add compression capability if enabled and server supports it
        if self.configuration.use_compression:
            capabilities |= constants.CAPABILITY.COMPRESS
        
        # Only use capabilities that the server supports
        return capabilities & self.context.server_capabilities
    
    
    def _handle_ssl_connection(self, client_capabilities: int) -> None:
        """
        Handle SSL connection setup
        
        Raises:
            OperationalError: If SSL setup fails
        """
        # Check if server supports SSL
        if not self.context.has_capability(constants.CAPABILITY.SSL):
            raise OperationalError("Trying to connect with SSL, but SSL not enabled in the server")
        
        # Import SSL request packet
        from ..message.client.ssl_request_packet import SslRequestPacket
        
        # Calculate client capabilities with SSL enabled
        # Add SSL capability if SSL enabled and server supports it
        client_capabilities |= constants.CAPABILITY.SSL
        
        # Send SSL request packet
        ssl_request = SslRequestPacket(
            client_capabilities,
            self.context.default_collation
        )
        ssl_request.encode(self.writer, self.context)
        
        # Upgrade socket to SSL
        self._upgrade_to_ssl_socket()
    
    def _upgrade_to_ssl_socket(self) -> None:
        """
        Upgrade the current socket to SSL
        
        Raises:
            OperationalError: If SSL upgrade fails
        """
        try:
            # Import SSL socket wrapper
            from .socket.ssl_socket import SSLSocketWrapper
            
            # Create SSL wrapper
            ssl_wrapper = SSLSocketWrapper(self.socket, self.configuration)
            
            # Wrap socket with SSL
            ssl_socket = ssl_wrapper.wrap_socket(server_hostname=self.configuration.host)
            
            # Replace the socket in reader and writer streams
            self.socket = ssl_socket
            self.reader.stream.socket = ssl_socket
            self.writer.stream.socket = ssl_socket
            
            # Store SSL wrapper for later use
            self.ssl_wrapper = ssl_wrapper
            
        except Exception as e:
            raise OperationalError(f"Failed to upgrade socket to SSL: {e}")
    
    def _handle_authentication(self) -> None:
        """
        Handle authentication process using plugin system
        
        Raises:
            OperationalError: If authentication fails
        """
        # Import plugin system
        from ...plugin.authentication_plugin_loader import AuthenticationPluginLoader
        from ...plugin.authentication.plugin_registry import register_builtin_plugins
        
        # Ensure plugins are registered
        register_builtin_plugins()
        
        # Read initial authentication result
        auth_result = self.reader.read_packet()
        
        # Check if server requests plugin authentication
        if len(auth_result) > 0:
            packet_type = auth_result[0]
            
            if packet_type == 0x00:
                # OK packet - authentication successful with handshake response
                self._parse_ok_packet(auth_result)
                return
            elif packet_type == 0xFF:
                # Error packet - authentication failed
                self._parse_error_packet(auth_result)
                return
            elif packet_type == 0xFE:
                # Auth switch request - server wants different plugin
                self._handle_auth_switch(auth_result)
                return
            else:
                # Continue with plugin authentication
                self._handle_plugin_auth_continue(auth_result)
                return
        
        raise OperationalError("Empty authentication result packet")
    
    def _handle_auth_switch(self, packet: bytes) -> None:
        """
        Handle authentication switch request
        
        Args:
            packet: Auth switch packet
            
        Raises:
            OperationalError: If authentication fails
        """
        if len(packet) < 2:
            raise OperationalError("Invalid auth switch packet")
        
        # Parse auth switch packet
        # Format: 0xFE + plugin_name + 0x00 + plugin_data
        plugin_name_end = packet.find(0, 1)
        if plugin_name_end == -1:
            raise OperationalError("Invalid auth switch packet format")
        
        plugin_name = packet[1:plugin_name_end].decode('utf-8')
        plugin_data = packet[plugin_name_end + 1:]
        
        # Get authentication plugin
        try:
            from ...plugin.authentication_plugin_loader import AuthenticationPluginLoader
            plugin_factory = AuthenticationPluginLoader.get(plugin_name, self.configuration)
            
            # Initialize plugin
            password = getattr(self.configuration, 'password', None)
            plugin = plugin_factory.initialize(password, plugin_data, self.configuration, self.host_address)
            
            # Process authentication
            response = plugin.process(self.writer, self.reader, self.context)
            
            # Handle final response
            self._handle_auth_final_response(response)
            
        except Exception as e:
            raise OperationalError(f"Authentication plugin '{plugin_name}' failed: {e}")
    
    def _handle_plugin_auth_continue(self, packet: bytes) -> None:
        """
        Handle continuation of plugin authentication
        
        Args:
            packet: Authentication continuation packet
        """
        # For now, treat as successful authentication
        # This would need more sophisticated handling for multi-round auth
        self._parse_ok_packet(packet)
    
    def _handle_auth_final_response(self, packet: bytes) -> None:
        """
        Handle final authentication response
        
        Args:
            packet: Final authentication response packet
            
        Raises:
            OperationalError: If authentication fails
        """
        if len(packet) == 0:
            raise OperationalError("Empty authentication response packet")
        
        packet_type = packet[0]
        
        if packet_type == 0x00:
            # OK packet - authentication successful
            self._parse_ok_packet(packet)
        elif packet_type == 0xFF:
            # Error packet - authentication failed
            self._parse_error_packet(packet)
        else:
            raise OperationalError(f"Unexpected authentication response: {packet_type:02x}")
    
    def _execute_init_command(self) -> None:
        """
        Execute initialization command if specified in configuration
        
        Raises:
            OperationalError: If init command execution fails
        """
        if self.configuration.init_command:
            try:
                init_command = self.configuration.init_command.strip()
                if init_command:
                    # Use the existing QueryPacket and execute method
                    from ...impl.message.client.query_packet import QueryPacket
                    
                    query_packet = QueryPacket(init_command)
                    
                    # Execute the query - this handles all the packet framing and response parsing
                    completions = self.execute(query_packet, can_redo=False)
                    
                    # For init commands, we just need to ensure they executed successfully
                    # The execute method will handle OK/ERROR packets and throw exceptions if needed
                    
            except Exception as e:
                raise OperationalError(f"Failed to execute init command '{self.configuration.init_command}': {e}")
    
    def _enable_compression_if_negotiated(self) -> None:
        """
        Enable compression if it was negotiated during handshake
        """
        if (self.configuration.use_compression and 
            self.context and 
            self.context.has_capability(constants.CAPABILITY.COMPRESS)):
            
            # Wrap the raw socket with compression stream
            from .socket.stream.compress_stream import CompressStream
            
            # Create compression stream wrapper around the raw socket
            compress_stream = CompressStream(self.socket, self.configuration.debug)
            
            # Replace stream with compression stream in reader and writer
            self.reader.stream = compress_stream
            self.writer.stream = compress_stream
    
    def _send_message(self, message: ClientMessage) -> None:
        """
        Send client message to server
        
        Args:
            message: Message to send
            
        Raises:
            OperationalError: If send fails
        """
        try:
            message.encode(self.writer, self.context)
        except Exception as e:
            raise OperationalError(f"Failed to send message: {e}")
    
    def execute(self, message: ClientMessage, can_redo: bool = False) -> List[Completion]:
        """
        Send client message and read result
        
        Args:
            message: Client message to send
            can_redo: Whether the message can be redone in case of failover
            
        Returns:
            List of completion results
            
        Raises:
            SQLException: If execution fails
        """
        with self.lock:
            if self.closed:
                raise OperationalError("Connection is closed")
            
            try:
                # Send message
                self._send_message(message)
                
                # Read and parse results
                results = []
                result_packet = self.reader.read_packet()
                completion = self._parse_result_packet(result_packet)
                results.append(completion)
                
                return results
                
            except Exception as e:
                raise OperationalError(f"Execution failed: {e}")
    
    def execute_with_statement(self, message: ClientMessage, stmt: Any, can_redo: bool = False) -> List[Completion]:
        """Execute with statement context"""
        return self.execute(message, can_redo)
    
    def execute_with_options(self, 
                           message: ClientMessage,
                           stmt: Any,
                           fetch_size: int,
                           max_rows: int,
                           result_set_concurrency: int,
                           result_set_type: int,
                           close_on_completion: bool,
                           can_redo: bool = False) -> List[Completion]:
        """Execute with full options"""
        return self.execute(message, can_redo)
    
    def execute_pipeline(self,
                        messages: List[ClientMessage],
                        stmt: Any,
                        fetch_size: int,
                        max_rows: int,
                        result_set_concurrency: int,
                        result_set_type: int,
                        close_on_completion: bool,
                        can_redo: bool = False) -> List[Completion]:
        """Execute pipeline of messages"""
        results = []
        for message in messages:
            result = self.execute(message, can_redo)
            results.extend(result)
        return results
    
    def read_streaming_results(self,
                             completions: List[Completion],
                             fetch_size: int,
                             max_rows: int,
                             result_set_concurrency: int,
                             result_set_type: int,
                             close_on_completion: bool) -> None:
        """Read streaming results"""
        # Simplified implementation
        pass
    
    def close_prepare(self, prepare: Any) -> None:
        """Close prepare command"""
        # Simplified implementation
        pass
    
    def abort(self, executor: Any) -> None:
        """Abort connection"""
        self.close()
    
    def close(self) -> None:
        """Close client connection"""
        with self.lock:
            if self.closed:
                return
            
            self.closed = True
            self.connected = False
            self._cleanup_connection()
    
    def set_read_only(self, read_only: bool) -> None:
        """Set read-only mode"""
        self.read_only = read_only
    
    def get_socket_timeout(self) -> int:
        """Get socket timeout"""
        return self.socket_timeout
    
    def set_socket_timeout(self, milliseconds: int) -> None:
        """Set socket timeout"""
        self.socket_timeout = milliseconds
        if self.socket:
            self.socket.settimeout(milliseconds / 1000.0)
    
    def is_closed(self) -> bool:
        """Check if closed"""
        return self.closed
    
    def reset(self) -> None:
        """Reset connection"""
        # Simplified implementation
        pass
    
    def is_primary(self) -> bool:
        """Check if primary connection"""
        return not self.read_only
    
    
    def get_exception_factory(self) -> ExceptionFactory:
        """Get exception factory"""
        return self.exception_factory
    
    def get_host_address(self) -> HostAddress:
        """Get host address"""
        return self.host_address
    
    def get_socket_ip(self) -> Optional[str]:
        """Get socket IP"""
        if self.socket and hasattr(self.socket, 'getpeername'):
            try:
                peer = self.socket.getpeername()
                return peer[0] if isinstance(peer, tuple) else None
            except:
                return None
        return None
    
    def _parse_result_packet(self, packet: bytes) -> Completion:
        """
        Parse result packet into completion
        
        Args:
            packet: Result packet data
            
        Returns:
            Completion object
            
        Raises:
            OperationalError: If packet is invalid
        """
        if len(packet) == 0:
            raise OperationalError("Empty result packet")
        
        packet_type = packet[0]
        
        if packet_type == 0x00:
            # OK packet
            return self._parse_ok_packet(packet)
        elif packet_type == 0xFF:
            # Error packet
            self._parse_error_packet(packet)
        else:
            # Result set packet - parse according to MySQL/MariaDB protocol
            return self._parse_result_set(packet)
    
    def _parse_ok_packet(self, packet: bytes) -> Completion:
        """
        Parse OK packet with full session tracking support
        
        Args:
            packet: OK packet data
            
        Returns:
            Completion object
        """
        import struct
        pos = 1  # Skip OK marker (0x00)
        
        # Affected rows (length-encoded)
        affected_rows, pos = self.reader.read_length_encoded_int(packet, pos)
        
        # Last insert ID (length-encoded)
        last_insert_id, pos = self.reader.read_length_encoded_int(packet, pos)
        
        # Server status (2 bytes)
        if pos + 2 <= len(packet):
            server_status = struct.unpack('<H', packet[pos:pos + 2])[0]
            pos += 2
            if self.context:
                self.context.server_status = server_status
        else:
            server_status = 0
        
        # Warning count (2 bytes)
        if pos + 2 <= len(packet):
            warning_count = struct.unpack('<H', packet[pos:pos + 2])[0]
            pos += 2
            if self.context:
                self.context.warning_count = warning_count
        else:
            warning_count = 0
        
        # Process additional information if present
        if pos < len(packet):
            # Skip info string (length-encoded)
            try:
                info_length, pos = self.reader.read_length_encoded_int(packet, pos)
                pos += info_length  # Skip info string content
            except:
                # If we can't read info length, skip remaining processing
                pass
            
            # Process session tracking if CLIENT_SESSION_TRACK capability is enabled
            if (self.context and 
                self.context.has_capability(constants.CAPABILITY.SESSION_TRACKING) and 
                pos < len(packet)):
                
                try:
                    self._process_session_tracking(packet, pos)
                except Exception as e:
                    # Log error but don't fail the packet parsing
                    pass
        
        
        return Completion(affected_rows=affected_rows, insert_id=last_insert_id)
    
    def _process_session_tracking(self, packet: bytes, pos: int) -> None:
        """
        Process session tracking information from OK packet
        
        Args:
            packet: Packet data
            pos: Current position in packet
        """
        while pos < len(packet):
            try:
                # Read session state buffer length
                session_length, pos = self.reader.read_length_encoded_int(packet, pos)
                session_end = pos + session_length
                
                if session_end > len(packet):
                    break
                
                # Process session state data
                while pos < session_end:
                    if pos >= len(packet):
                        break
                    
                    # Read session tracking type
                    tracking_type = packet[pos]
                    pos += 1
                    
                    if tracking_type == self.SESSION_TRACK_SYSTEM_VARIABLES:
                        pos = self._process_system_variables(packet, pos, session_end)
                    elif tracking_type == self.SESSION_TRACK_SCHEMA:
                        pos = self._process_schema_change(packet, pos, session_end)
                    else:
                        # Skip unknown tracking types
                        try:
                            skip_length, pos = self.reader.read_length_encoded_int(packet, pos)
                            pos += skip_length
                        except:
                            break
                
                pos = session_end
                
            except Exception as e:
                break
    
    def _process_system_variables(self, packet: bytes, pos: int, end_pos: int) -> int:
        """Process system variable changes"""
        try:
            while pos < end_pos:
                # Read variable data length
                var_length, pos = self.reader.read_length_encoded_int(packet, pos)
                var_end = pos + var_length
                
                if var_end > end_pos:
                    break
                
                # Read variable name
                name_length, pos = self.reader.read_length_encoded_int(packet, pos)
                if pos + name_length > var_end:
                    break
                
                var_name = packet[pos:pos + name_length].decode('utf-8', errors='replace')
                pos += name_length
                
                # Read variable value (can be null)
                if pos < var_end:
                    value_length, pos = self.reader.read_length_encoded_int(packet, pos)
                    if value_length > 0 and pos + value_length <= var_end:
                        var_value = packet[pos:pos + value_length].decode('utf-8', errors='replace')
                        pos += value_length
                    else:
                        var_value = None
                else:
                    var_value = None
                
                # Update context based on variable
                if self.context:
                    if var_name == 'character_set_client':
                        self.context.charset = var_value or 'utf8mb4'
                    elif var_name == 'connection_id':
                        if var_value:
                            self.context.connection_id = int(var_value)
                
                
                pos = var_end
                
        except Exception as e:
            pass
        
        return pos
    
    def _process_schema_change(self, packet: bytes, pos: int, end_pos: int) -> int:
        """Process schema (database) change"""
        try:
            # Read schema data length
            schema_length, pos = self.reader.read_length_encoded_int(packet, pos)
            
            if pos + schema_length > end_pos:
                return end_pos
            
            # Read database name (can be null for no database)
            db_length, pos = self.reader.read_length_encoded_int(packet, pos)
            
            if db_length > 0 and pos + db_length <= end_pos:
                database = packet[pos:pos + db_length].decode('utf-8', errors='replace')
                pos += db_length
            else:
                database = None
            
            # Update context
            if self.context:
                self.context.database = database
            
                
        except Exception as e:
            pass
        
        return pos
    
    def _parse_result_set(self, packet: bytes) -> 'Completion':
        """
        Parse result set according to MySQL/MariaDB protocol
        
        Args:
            packet: First packet containing column count
            
        Returns:
            Completion object with result set data
        """
        from ..completion import Completion
        
        try:
            # Step 1: Parse column count from first packet
            column_count, _ = self.reader.read_length_encoded_int(packet, 0)
            
            
            # Step 2: Read column definition packets
            columns = []
            for i in range(column_count):
                col_packet = self.reader.read_packet()
                column_info = self._parse_column_definition(col_packet)
                columns.append(column_info)
            
            # Step 3: Handle EOF packet after column definitions based on capabilities
            # Check if DEPRECATE_EOF capability is set
            
            if not self.context.isEofDeprecated():
                # skip intermediate EOF packet
                self.reader.read_packet()
            
            # Step 4: Read row data packets until EOF
            rows = []
            while True:
                row_packet = self.reader.read_packet()
                
                if len(row_packet) == 0:
                    break
                
                # Check for EOF/OK packet based on DEPRECATE_EOF capability and packet length
                # EOF/OK packets start with 0xFE and have specific length constraints
                if (row_packet[0] == 0xFE and 
                    ((self.context.isEofDeprecated() and len(row_packet) < 16777215) or 
                     (not self.context.isEofDeprecated() and len(row_packet) < 8))):
                    
                    # This is an EOF or OK packet - end of result set
                    pos = 1  # Skip packet type byte
                    
                    if not self.context.isEofDeprecated():
                        # Traditional EOF packet
                        if len(row_packet) >= 5:
                            import struct
                            warnings = struct.unpack('<H', row_packet[pos:pos + 2])[0]
                            server_status = struct.unpack('<H', row_packet[pos + 2:pos + 4])[0]
                            
                    else:
                        # OK packet with 0xFE header (DEPRECATE_EOF enabled) - use existing OK packet parser
                        ok_completion = self._parse_ok_packet(row_packet)
                        
                    
                    break
                else:
                    # Row data packet
                    row_data = self._parse_row_data(row_packet, columns)
                    rows.append(row_data)
            
            # Create completion with result set
            completion = Completion(
                affected_rows=len(rows),
                insert_id=0,
                warning_count=0,
                is_result_set=True
            )
            
            # Store result set data in completion
            completion.result_set = {
                'columns': columns,
                'rows': rows,
                'column_count': column_count
            }
            
            
            return completion
            
        except Exception as e:
            raise OperationalError(f"Failed to parse result set: {e}")
    
    def _parse_column_definition(self, packet: bytes) -> dict:
        """
        Parse column definition packet according to MySQL/MariaDB protocol
        
        Args:
            packet: Column definition packet
            
        Returns:
            Dictionary with column information
        """
        pos = 0
        
        # Read the 6 identifiers as per Java implementation
        catalog, pos = self.reader.read_length_encoded_string(packet, pos)
        schema, pos = self.reader.read_length_encoded_string(packet, pos)  
        table, pos = self.reader.read_length_encoded_string(packet, pos)
        org_table, pos = self.reader.read_length_encoded_string(packet, pos)
        name, pos = self.reader.read_length_encoded_string(packet, pos)
        org_name, pos = self.reader.read_length_encoded_string(packet, pos)
        
        # Handle extended info only if EXTENDED_METADATA capability is enabled
        ext_type_name = None
        ext_type_format = None
        
        # Check if we have the length field (0x0C) or extended metadata
        if self.context.hasExtendedMetadata() and pos < len(packet) and packet[pos] != 0x0C:
            if packet[pos] != 0:
                # Has extended info - read length-encoded buffer
                ext_length, pos = self.reader.read_length_encoded_int(packet, pos)
                ext_end = pos + ext_length
                
                while pos < ext_end and pos < len(packet):
                    if pos >= len(packet):
                        break
                    ext_type = packet[pos]
                    pos += 1
                    
                    if ext_type == 0:
                        # Extended type name
                        name_length, pos = self.reader.read_length_encoded_int(packet, pos)
                        if pos + name_length <= len(packet):
                            ext_type_name = packet[pos:pos + name_length].decode('ascii', errors='ignore')
                            pos += name_length
                    elif ext_type == 1:
                        # Extended type format
                        format_length, pos = self.reader.read_length_encoded_int(packet, pos)
                        if pos + format_length <= len(packet):
                            ext_type_format = packet[pos:pos + format_length].decode('ascii', errors='ignore')
                            pos += format_length
                    else:
                        # Skip unknown extended data
                        skip_length, pos = self.reader.read_length_encoded_int(packet, pos)
                        pos += skip_length
            else:
                # Skip the 0 byte
                pos += 1
        
        # Skip length field (always 0x0c) - this should be at the current position now
        if pos < len(packet) and packet[pos] == 0x0C:
            pos += 1
        
        # Read fixed-length fields (12 bytes total)
        import struct
        if pos + 12 <= len(packet):
            # charset (2 bytes, little endian)
            charset = struct.unpack('<H', packet[pos:pos + 2])[0]
            pos += 2
            # column length (4 bytes, little endian)  
            column_length = struct.unpack('<I', packet[pos:pos + 4])[0]
            pos += 4
            # column type (1 byte)
            column_type = packet[pos]
            pos += 1
            # flags (2 bytes, little endian)
            flags = struct.unpack('<H', packet[pos:pos + 2])[0]
            pos += 2
            # decimals (1 byte)
            decimals = packet[pos]
            pos += 1
        else:
            charset = column_length = column_type = flags = decimals = 0
        
        column_info = {
            'catalog': catalog,
            'schema': schema,
            'table': table,
            'org_table': org_table,
            'name': name,
            'org_name': org_name,
            'character_set': charset,
            'column_length': column_length,
            'column_type': column_type,
            'flags': flags,
            'decimals': decimals,
            'ext_type_name': ext_type_name,
            'ext_type_format': ext_type_format
        }
        
        
        return column_info
    
    def _parse_row_data(self, packet: bytes, columns: list) -> tuple:
        """
        Parse row data packet
        
        Args:
            packet: Row data packet
            columns: Column definitions
            
        Returns:
            Tuple of row values
        """
        try:
            pos = 0
            row_values = []
            
            for column in columns:
                if pos >= len(packet):
                    row_values.append(None)
                    continue
                
                # Read length-encoded string for each column value
                value, pos = self.reader.read_length_encoded_string(packet, pos)
                
                # Convert value based on column type
                if value is None:
                    row_values.append(None)
                else:
                    # Basic type conversion
                    column_type = column.get('column_type', 253)
                    converted_value = self._convert_column_value(value, column_type)
                    
                    
                    row_values.append(converted_value)
            
            return tuple(row_values)
            
        except Exception as e:
            # Return tuple with None values if parsing fails
            return tuple(None for _ in columns)
    
    def _convert_column_value(self, value: str, column_type: int):
        """
        Convert column value based on MySQL type
        
        Args:
            value: String value from packet
            column_type: MySQL column type
            
        Returns:
            Converted value
        """
        if value is None:
            return None
        
        try:
            # Basic type conversions for common types
            if column_type in (1, 2, 3, 8, 9):  # TINY, SHORT, LONG, LONGLONG, INT24
                return int(value)
            elif column_type in (4, 5):  # FLOAT, DOUBLE
                return float(value)
            elif column_type in (0, 10, 11, 12, 13, 14):  # DECIMAL, DATE, TIME, DATETIME, YEAR, NEWDATE
                return value  # Keep as string for now
            else:
                # Default to string for VARCHAR, TEXT, etc.
                return value
        except (ValueError, TypeError):
            # If conversion fails, return as string
            return value
    
    def _parse_error_packet(self, packet: bytes) -> None:
        """Parse error packet and raise exception"""
        if len(packet) < 3:
            raise DatabaseError("Invalid error packet")
        
        import struct
        pos = 1  # Skip error marker
        
        # Error code
        error_code = struct.unpack('<H', packet[pos:pos + 2])[0]
        pos += 2
        
        # Error message
        error_message = packet[pos:].decode('utf-8', errors='replace')
        
        raise DatabaseError(f"MySQL Error {error_code}: {error_message}")
    
    def _cleanup_connection(self) -> None:
        """Clean up connection resources"""
        if self.writer:
            try:
                self.writer.close()
            except:
                pass
            self.writer = None
        
        if self.reader:
            try:
                self.reader.close()
            except:
                pass
            self.reader = None
        
        # Close SSL wrapper if present
        if self.ssl_wrapper:
            try:
                self.ssl_wrapper.close()
            except:
                pass
            self.ssl_wrapper = None
        
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
    
    def escape_string(self, string: str) -> str:
        """
        Escape a string for use in SQL statements
        
        Args:
            string: String to escape
            
        Returns:
            str: Escaped string with quotes
        """
        no_backslash_escapes = (self.context.server_status & constants.STATUS.NO_BACKSLASH_ESCAPES) > 0
        
        # Use proper escaping logic based on server mode
        if no_backslash_escapes:
            # When NO_BACKSLASH_ESCAPES is set, single quotes are escaped by doubling them
            escaped = string.replace("'", "''")
        else:
            # Standard escaping: backslash, quote, double quote, zero byte
            escaped = string.replace('\\', '\\\\')  # Backslash first
            escaped = escaped.replace("'", "\\'")   # Single quote
            escaped = escaped.replace('"', '\\"')   # Double quote  
            escaped = escaped.replace('\0', '\\0')  # Zero byte
        
        return escaped
