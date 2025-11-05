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
Sync Client implementation for MariaDB connections

Uses blocking I/O operations.
"""

import decimal
import datetime
from re import M
import socket
import threading
import struct
import ipaddress
import uuid
import ssl
from typing import List, Optional, Any, Dict

from mariadb.impl.message.server.ok_packet import OkPacket
from mariadb.impl.message.server.error_packet import ErrorPacket
from mariadb.impl.message.server.eof_packet import EofPacket
from mariadb.impl.message.server.prepare_stmt_packet import PrepareStmtPacket
from mariadb.impl.message.server.column_definition_packet import ColumnDefinitionPacket
from .base_client import BaseClient
from .context import Context
from .socket.payload_parser import PayloadParser
from .socket.payload_writer import PayloadWriter
from .socket.stream import SyncStream
from ..configuration import Configuration
from ..host_address import HostAddress
from ..message.client_message import ClientMessage
from ..message.client.handshake_response import HandshakeResponse
from ..message.client.reset_connection_packet import ResetConnectionPacket
from ..message.client.query_packet import QueryPacket
from ..message.client.ping_packet import PingPacket
from ..message.client.quit_packet import QuitPacket
from ..message.client.prepare_packet import PreparePacket
from ..message.client.execute_packet import ExecutePacket
from ..message.client.change_user_packet import ChangeUserPacket
from ..plugin.authentication_plugin_loader import AuthenticationPluginLoader
from ..completion import Completion
from ...exceptions import OperationalError, DatabaseError, NotSupportedError
from mariadb_shared.constants import STATUS, FIELD_TYPE, FIELD_FLAG
from mariadb_shared import constants


class SyncClient(BaseClient):
    """
    Synchronous client implementation for MariaDB connections
    
    Uses blocking I/O operations.
    """
    
    def __init__(self, configuration: Configuration, host_address: HostAddress) -> None:
        """
        Initialize sync client
        
        Args:
            configuration: Connection configuration
            host_address: Host address to connect to
        """
        super().__init__(configuration, host_address)
        
        # Sync-specific attributes
        self.socket: Optional[socket.socket] = None
        self.stream: Optional[SyncStream] = None
        
    def connect(self) -> None:
        """
        Establish connection to MariaDB server with host failover support
        
        Raises:
            OperationalError: If connection fails to all hosts
        """
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
            
                # Ensure autocommit and charset are correctly set
                self._ensure_default()
                # Execute init command if specified
                if self.configuration.init_command:
                    self._execute_init_command()
                
                return  # Success!
                
            except Exception as e:
                last_exception = e
                self._cleanup_connection()
                continue  # Try next host
        
        # All hosts failed
        if last_exception:
            raise last_exception
        raise OperationalError("Connection failed to all hosts")
    
    def _create_socket(self) -> None:
        """
        Create socket connection
        
        Raises:
            OperationalError: If socket creation fails
        """
        try:
            if self.configuration.socket_path:
                # Unix socket connection
                self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                # Set connect timeout for Unix socket
                if self.connect_timeout:
                    self.socket.settimeout(self.connect_timeout)
                self.socket.connect(self.configuration.socket_path)
            else:
                # TCP connection - use connect_timeout for connection phase
                self.socket = socket.create_connection(
                    (self.host_address.host, self.host_address.port),
                    timeout=self.connect_timeout if self.connect_timeout else None
                )
            
            # Set socket options
            if self.socket_timeout:
                self.socket.settimeout(self.socket_timeout)
            
            # Create sync stream wrapper with connection_id
            self.stream = SyncStream(self.socket)
            
        except Exception as e:
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
            self.socket = None
            # Use errno 2002 for connection errors (Can't connect to server)
            raise self.exception_factory.create_exception(
                f"Can't connect to server on '{self.host_address.host}':{self.host_address.port}: {e}", 
                errno=2002,
                sql_state='HY000'
            )
    
    def _perform_handshake(self) -> None:
        """
        Perform MariaDB handshake protocol
        
        Raises:
            OperationalError: If handshake fails
        """
        try:
            # Read initial handshake packet from server
            handshake_packet = self.stream.read_payload()
            self.context = self._parse_handshake(handshake_packet)
            self.stream.connection_id = self.context.connection_id

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
            self.stream.send_payload(response.encode(self.context), response.type(), reset_sequence=False)

            # Read authentication response
            self._handle_authentication(self.stream.read_payload())
            
            # Enable compression if negotiated
            self._enable_compression_if_negotiated()
            self.connected = True
                
        except Exception as e:
            self.close()
            if isinstance(e, (OperationalError, DatabaseError)):
                raise
            raise OperationalError(f"Handshake failed: {e}")
    
    def _handle_authentication(self, packet: bytes) -> None:
        """
        Handle authentication response from server
        
        Args:
            packet: Authentication response packet
            handshake: Initial handshake data
            
        Raises:
            OperationalError: If authentication fails
        """
        if len(packet) == 0:
            raise OperationalError("Empty authentication response")
        
        packet_type = packet[0]
        
        if packet_type == 0x00:
            # OK packet - authentication successful
            OkPacket.decode(packet, self.context)
        elif packet_type == 0xFF:
            # Error packet - authentication failed
            raise ErrorPacket.decode(packet, self.context).toError(self.exception_factory)
        elif packet_type == 0xFE:
            # Auth switch request or auth more data
            if len(packet) == 1 or (len(packet) > 1 and packet[1] == 0x04):
                # Auth more data
                self._handle_plugin_auth_continue(packet)
            else:
                # Auth switch - server requests different auth plugin
                self._handle_auth_switch(packet)
        else:
            raise OperationalError(f"Unexpected authentication response: {packet_type:02x}")
    
    def _handle_auth_switch(self, packet: bytearray) -> None:
        """
        Handle authentication plugin switch request
        
        Args:
            packet: Auth switch packet
            handshake: Initial handshake data
            
        Raises:
            OperationalError: If auth switch fails
        """
        parser = PayloadParser(packet)
        parser.skip(1)  # Skip 0xFE marker
        
        # Read plugin name
        plugin_name = parser.read_null_terminated_string()
        
        # Read auth data
        auth_data = parser.read_remaining()
        
        try:
            # Load and execute the requested plugin
            plugin_factory = AuthenticationPluginLoader.get(plugin_name, self.configuration)
            
            # Initialize plugin
            plugin = plugin_factory.initialize(self.configuration.password, auth_data, self.configuration, self.host_address)
            
            # Process authentication - plugin will send response and read server's reply
            response = plugin.processSync(self.stream, self.context)
            
            # Handle final response
            self._handle_auth_final_response(response)
            
        except DatabaseError as e:
            raise e
        except Exception as e:
            raise OperationalError(f"Authentication plugin '{plugin_name}' failed: {e}")
    
    # _handle_plugin_auth_continue() and _handle_auth_final_response() inherited from BaseClient
    
    def _execute_init_command(self) -> None:
        """
        Execute initialization command if specified in configuration
        
        Raises:
            OperationalError: If init command execution fails
        """
        if self.configuration.init_command:
            try:
                query_packet = QueryPacket(self.configuration.init_command)
                self.execute(query_packet, self.configuration)
            except Exception as e:
                raise OperationalError(f"Failed to execute init command: {e}")
    
    def _enable_compression_if_negotiated(self) -> None:
        """Enable compression if negotiated with server"""
        if self.context.has_client_capability(constants.CAPABILITY.COMPRESS):
            # Import here to avoid circular dependency
            from .socket.compress_stream import SyncCompressSocket
            
            # Wrap the socket with compression socket
            compress_socket = SyncCompressSocket(
                self.socket, 
                self.context.connection_id
            )
            
            # Replace socket in stream with compression socket
            self.stream.socket = compress_socket
    
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
        ssl_request = SslRequestPacket(client_capabilities)
        encoded = ssl_request.encode(self.context)
        self.stream.send_payload(encoded, ssl_request.type(), False)

        #self._send_message(ssl_request, False)
        
        try:
            # Import SSL utility
            from .socket.ssl_utility import SSLUtility
            # Create SSL context
            ssl_context = SSLUtility.create_ssl_context(self.configuration)
            
            # Wrap socket with SSL
            self.socket = ssl_context.wrap_socket(
                self.socket,
                server_hostname=self.host_address.host
            )
            
            # Create new SyncStream with the upgraded connection
            connection_id = self.context.connection_id if self.context else -1
            self.stream = SyncStream(self.socket, connection_id)
            self.stream.sequence = 2
        except Exception as e:
            raise OperationalError(f"Failed to upgrade socket to SSL: {e}")
    
    def _send_message(self, message: ClientMessage, reset_sequence: bool = True) -> None:
        """
        Send a client message to the server
        
        Args:
            message: Client message to send
        """
        encoded = message.encode(self.context)
        self.stream.send_payload(encoded, message.type(), reset_sequence)
    
    def execute(self, message: ClientMessage, config: 'Configuration' = None, can_redo: bool = False, buffered: bool = True) -> List[Completion]:
        """
        Execute a client message and return list of completions
        
        Args:
            message: Client message to execute
            config: Configuration to use (defaults to self.configuration)
            can_redo: Whether the operation can be retried (unused in sync)
            buffered: If True, read all rows. If False, create streaming result.
            
        Returns:
            List of Completion objects
            
        Raises:
            OperationalError: If execution fails
        """
            
        with self.lock:
            if self.closed:
                raise OperationalError("Connection is closed")
            
            try:            
                # Send message
                self._send_message(message)
            
                # Read and parse results
                results = []
                is_binary = message.is_binary()
                
                # Continue reading results while MORE_RESULTS_EXIST is set
                while True:
                    result_packet: bytearray = self.stream.read_payload()
                    completion = self._parse_result_packet(result_packet, config, is_binary, buffered)
                    results.append(completion)
                    
                    # Check if there are more results to read
                    if (self.context and 
                        (self.context.server_status & STATUS.MORE_RESULTS_EXIST) == 0):
                        break
                
                return results
            except DatabaseError as e:
                raise e    
            except Exception as e:
                raise OperationalError(f"Execution failed: {e}")
    
    def ping(self) -> None:
        """
        Send ping to server
        
        Raises:
            OperationalError: If ping fails
        """
        ping_packet = PingPacket()
        self.execute(ping_packet)
    
    def change_user(self, user: Optional[str], password: Optional[str], database: Optional[str]) -> None:
        """
        Change user
        
        Args:
            user: New user (None = keep current user)
            password: New password (None = keep current password)
            database: New database (None = keep current database)
            
        Raises:
            OperationalError: If change user fails
        """
        try:
            # Use current credentials if None is passed
            actual_user = user if user is not None else self.configuration.user
            actual_password = password if password is not None else self.configuration.password
            actual_database = database if database is not None else self.context.database
            
            # Send COM_CHANGE_USER packet
            change_user_packet = ChangeUserPacket(actual_user, actual_password, actual_database)
            self._send_message(change_user_packet)
            
            # Read authentication response (similar to initial connection)
            self._handle_authentication(self.stream.read_payload())
            
            # Update connection state
            if user is not None:
                self.configuration.user = user
            if password is not None:
                self.configuration.password = password
            if database is not None:
                self.context.database = database
                
        except Exception as e:
            if isinstance(e, DatabaseError):
                raise
            raise OperationalError(f"Change user failed: {e}")
    
    def close(self) -> None:
        """Close connection gracefully"""
        with self.lock:
            if self.closed:
                return
            
            # Send COM_QUIT packet to gracefully close the connection
            if self.connected and self.socket:
                try:
                    quit_packet = QuitPacket()
                    self._send_message(quit_packet)
                except Exception:
                    # Ignore errors when sending quit - connection may already be broken
                    pass
            self.closed = True
            self.connected = False
            self._cleanup_connection()
    
    
    def set_socket_timeout(self, seconds: float) -> None:
        """Set socket timeout"""
        self.socket_timeout = seconds
        if self.socket:
            self.socket.settimeout(seconds if seconds else None)
    
    def reset(self) -> None:
        """Reset connection"""
        self.execute(ResetConnectionPacket())
    
    def get_ssl_cipher(self) -> Optional[tuple]:
        """
        Get current SSL cipher information
        
        Returns:
            Cipher tuple (name, version, bits) or None if not using SSL
        """
        if self.socket and isinstance(self.socket, ssl.SSLSocket):
            try:
                return self.socket.cipher()
            except:
                pass
        return None
    
    def get_ssl_version(self) -> Optional[str]:
        """
        Get current TLS/SSL version
        
        Returns:
            TLS version string (e.g., 'TLSv1.3') or None if not using SSL
        """
        if self.socket and isinstance(self.socket, ssl.SSLSocket):
            try:
                return self.socket.version()
            except:
                pass
        return None
    
    def get_peer_certificate(self) -> Optional[dict]:
        """
        Get peer SSL certificate information
        
        Returns:
            Certificate dict or None if not using SSL
        """
        if self.socket and isinstance(self.socket, ssl.SSLSocket):
            try:
                return self.socket.getpeercert()
            except:
                pass
        return None
    
    
    def get_socket_ip(self) -> Optional[str]:
        """Get socket IP"""
        if self.socket:
            try:
                peer = self.socket.getpeername()
                return peer[0] if isinstance(peer, tuple) else None
            except:
                pass
        return None
    
    def _parse_result_packet(self, packet: bytes, config: 'Configuration', is_binary: bool = False, buffered: bool = True) -> Completion:
        """
        Parse result packet into completion
        
        Args:
            packet: Result packet data
            config: Configuration for parsing
            is_binary: Whether result uses binary protocol
            buffered: If True, read all rows. If False, create streaming result.
            
        Returns:
            Completion object
            
        Raises:
            OperationalError: If parsing fails
        """
        if len(packet) == 0:
            raise OperationalError("Empty result packet")
        
        packet_type = packet[0]
        
        if packet_type == 0x00:
            # OK packet
            return OkPacket.decode(packet, self.context)
        elif packet_type == 0xFF:
            # Error packet
            raise ErrorPacket.decode(packet, self.context).toError(self.exception_factory)
        else:
            # Result set packet - parse according to MySQL/MariaDB protocol
            return self._parse_result_set(packet, config, is_binary, buffered)
    
    # _parse_ok_packet(), _process_session_tracking(), _process_system_variables(), 
    # and _process_schema_change() are inherited from BaseClient
    
    def _parse_result_set(self, packet: bytes, config: 'Configuration', is_binary: bool = False, buffered: bool = True) -> 'Completion':
        """
        Parse result set according to MySQL/MariaDB protocol
        
        Args:
            packet: First packet containing column count
            config: Configuration for parsing
            is_binary: Whether result uses binary protocol
            buffered: If True, read all rows. If False, create streaming result.
            
        Returns:
            Completion with result set
            
        Raises:
            OperationalError: If parsing fails
        """
        try:
            # Parse column count from first packet
            parser = PayloadParser(packet)
            column_count = parser.read_length_encoded_int()
            
            # Read column definitions
            columns: List[ColumnDefinitionPacket] = []
            for _ in range(column_count):
                columns.append(ColumnDefinitionPacket.decode(self.stream.read_payload(), self.context))
            
            # Read EOF packet after column definitions (if not deprecated)
            if not self.context.isEofDeprecated():
                self.stream.read_payload()

            # Step 4: If unbuffered, create streaming result
            if not buffered:
                from ..result import SyncStreamingResult
                streaming_result = SyncStreamingResult(
                    stream=self.stream,
                    context=self.context,
                    columns=columns,
                    column_count=column_count,
                    config=config,
                    is_binary=is_binary,
                    row_parser=self._parse_row_data  # Pass row parser function
                )
                
                # Create completion with streaming result
                completion = OkPacket()
                completion.result_set = streaming_result
                return completion

            # Read rows
            rows: List[tuple] = []
            while True:
                row_packet = self.stream.read_payload()

                # Check for EOF/OK packet based on DEPRECATE_EOF capability and packet length
                # EOF/OK packets start with 0xFE and have specific length constraints
                if (row_packet[0] == 0xFE and 
                    ((self.context.isEofDeprecated() and len(row_packet) < 16777215) or 
                     (not self.context.isEofDeprecated() and len(row_packet) < 8))):
                    
                    if not self.context.isEofDeprecated():
                        # Traditional EOF packet
                        completion = EofPacket.decode(row_packet, self.context)
                    else:
                        # OK packet with 0xFE header (DEPRECATE_EOF enabled) - use existing OK packet parser
                        completion = OkPacket.decode(row_packet, self.context)

                    # Create CompleteResult with all rows
                    from ..result import CompleteResult
                    complete_result = CompleteResult(
                        columns=columns,
                        column_count=column_count,
                        config=config,
                        rows=rows,
                        is_binary=is_binary
                    )
                    # Store result object in completion
                    completion.result_set = complete_result
                                        
                    return completion               
                    
                else:
                    # Row data packet
                    row_data = self._parse_row_data(row_packet, columns, config, is_binary)
                    rows.append(row_data)
            
            
        except Exception as e:
            raise OperationalError(f"Failed to parse result set: {e}")
    
    # _parse_column_definition(), _apply_converters(), _parse_row_data(), 
    # _parse_binary_row_data(), and _parse_binary_column_value() are inherited from BaseClient
    
    def _cleanup_connection(self) -> None:
        """Clean up connection resources"""       
        if hasattr(self, 'socket') and self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
        if hasattr(self, 'stream'):
            self.stream = None
    

    def _ensure_default(self) -> None:
        """
        Ensure the connection charset is set to utf8mb4.
        If not already set, execute SET NAMES utf8mb4 command.
        """
        sql_commands = []
        if ((self.context.server_status & constants.STATUS.AUTOCOMMIT) > 0) != self.configuration.autocommit:
            sql_commands.append('autocommit = ' + str(int(self.configuration.autocommit)))
        if (self.context.charset != 'utf8mb4'):
            sql_commands.append('NAMES utf8mb4')
            self.context.charset = 'utf8mb4'

        if len(sql_commands) > 0:
            sql_command = 'SET ' + ', '.join(sql_commands)
            query_packet = QueryPacket(sql_command)
            self.execute(query_packet)
    
    def prepare_statement(self, sql: str) -> PrepareStmtPacket:
        """
        Prepare a SQL statement
        
        Args:
            sql: SQL statement to prepare
            
        Returns:
            PrepareStmtPacket object
            
        Raises:
            OperationalError: If preparation fails
        """
        with self.lock:
            if self.closed:
                raise OperationalError("Connection is closed")
            
            # Send COM_STMT_PREPARE
            prepare_packet = PreparePacket(sql)
            self._send_message(prepare_packet)
            
            # Read response
            response = self.stream.read_payload()
            
            # Parse prepare response
            return self._parse_prepare_response(response, sql)

    def _parse_prepare_response(self, packet: bytearray, sql: str) -> PrepareStmtPacket:
        """
        Parse prepare response packet
        
        Args:
            packet: Response packet data
            sql: Original SQL statement
            
        Returns:
            PrepareStmtPacket object
            
        Raises:
            OperationalError: If response is invalid
        """
        if len(packet) == 0:
            raise OperationalError("Empty prepare response packet")
        
        packet_type = packet[0]
        
        if packet_type == 0xFF:
            # Error packet
            raise ErrorPacket.decode(packet, self.context).toError(self.exception_factory)
        elif packet_type == 0x00:
            prepare_stmt_packet = PrepareStmtPacket.decode(packet, self.context)
            # Read parameter metadata if present
            if prepare_stmt_packet.parameter_count > 0:
                # Skip parameter metadata
                for _ in range(prepare_stmt_packet.parameter_count):
                    self.stream.read_payload()                

                # Read EOF packet after parameters (if not deprecated)
                if not self.context.isEofDeprecated():
                    self.stream.read_payload()
            
            # Read column metadata if present
            if prepare_stmt_packet.column_count > 0:
                columns = []
                for _ in range(prepare_stmt_packet.column_count):
                    columns.append(ColumnDefinitionPacket.decode(self.stream.read_payload(), self.context))
                prepare_stmt_packet.columns = columns
                
                # Read EOF packet after columns (if not deprecated)
                if not self.context.isEofDeprecated():
                    self.stream.read_payload()
            
            return prepare_stmt_packet
        else:
            raise OperationalError(f"Unexpected prepare response packet type: {packet_type}")
    
    def close_prepared_statement(self, stmt: PrepareStmtPacket) -> None:
        """
        Close a prepared statement
        
        Args:
            stmt: Prepared statement to close
        """
        if stmt.is_closed():
            return
        
        try:
            # Send COM_STMT_CLOSE packet
            with self.lock:
                if not self.closed:
                    from ..message.client.stmt_close_packet import StmtClosePacket
                    self._send_message(StmtClosePacket(stmt.statement_id))               
        except:
            # Ignore errors when closing
            pass
        finally:
            stmt.close()


    def get_ssl_cipher(self) -> Optional[tuple]:
        """
        Get current SSL cipher information
        
        Returns:
            Cipher tuple (name, version, bits) or None if not using SSL
        """
        if self.socket and hasattr(self.socket, 'cipher'):
            try:
                return self.socket.cipher()
            except:
                return None
        return None
    
    def get_ssl_version(self) -> Optional[str]:
        """
        Get current TLS/SSL version
        
        Returns:
            TLS version string (e.g., 'TLSv1.3') or None if not using SSL
        """
        if self.socket and hasattr(self.socket, 'version'):
            try:
                return self.socket.version()
            except:
                return None
        return None
    
    def get_peer_certificate(self) -> Optional[dict]:
        """
        Get peer SSL certificate information
        
        Returns:
            Certificate dict or None if not using SSL
        """
        if self.socket and hasattr(self.socket, 'getpeercert'):
            try:
                return self.socket.getpeercert()
            except:
                return None
        return None
    