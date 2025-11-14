# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Sync Client implementation for MariaDB connections

Uses blocking I/O operations.
"""

from re import M
import socket
import ssl
from typing import List, Optional

from mariadb.impl.message.server.ok_packet import OkPacket
from mariadb.impl.message.server.error_packet import ErrorPacket
from mariadb.impl.message.server.eof_packet import EofPacket
from mariadb.impl.message.server.prepare_stmt_packet import PrepareStmtPacket
from mariadb.impl.message.server.column_definition_packet import ColumnDefinitionPacket
from .base_client import BaseClient
from .socket.payload_parser import PayloadParser
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
from ..message.client.change_user_packet import ChangeUserPacket
from ..plugin.authentication_plugin_loader import AuthenticationPluginLoader
from ..completion import Completion
from ...exceptions import OperationalError, DatabaseError
from mariadb_shared.constants import STATUS
from mariadb_shared import constants


class SyncClient(BaseClient):
    """
    Synchronous client implementation for MariaDB connections
    
    Handles all low-level protocol communication with the MariaDB server
    using blocking I/O operations.
 
    """
    
    # =========================================================================
    # Initialization
    # =========================================================================
    
    def __init__(self, configuration: Configuration) -> None:
        """Initialize synchronous client with configuration and host address"""
        super().__init__(configuration)
        
        # Sync-specific attributes
        self.socket: Optional[socket.socket] = None
        self.stream: Optional[SyncStream] = None

    # =========================================================================
    # Connection Management
    # =========================================================================

    def connect(self) -> None:
        """Establish connection to MariaDB server with host failover support"""
        if self.connected:
            return
        
        # Get list of hosts to try
        hosts = self.configuration.get_hosts()
        last_exception = None
        
        for host_address in hosts:
            try:
                self.host_address = host_address
                
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
        """Create and configure TCP or Unix socket connection"""
        try:
            if self.configuration.unix_socket:
                self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                if self.connect_timeout:
                    self.socket.settimeout(self.connect_timeout)
                self.socket.connect(self.configuration.unix_socket)
            else:
                self.socket = socket.create_connection(
                    (self.host_address.host, self.host_address.port),
                    timeout=self.connect_timeout if self.connect_timeout else None
                )
            
            if self.socket_timeout:
                self.socket.settimeout(self.socket_timeout)
            
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
        """Perform initial handshake and authentication with server"""
        try:
            handshake_packet = self.stream.read_payload()
            if (handshake_packet[0] == 0xff):
                raise ErrorPacket.decode(handshake_packet).toError(self.exception_factory)
            self.context = self._parse_handshake(handshake_packet)
            self.stream.connection_id = self.context.connection_id

            client_capabilities = self._calculate_client_capabilities()

            if self.configuration.ssl:
                self._handle_ssl_connection(client_capabilities)

            self.context.client_capabilities = client_capabilities
            self.context.eof_deprecated = bool(client_capabilities & constants.CAPABILITY.DEPRECATE_EOF)
            self.context.extended_metadata = bool(client_capabilities & constants.CAPABILITY.EXTENDED_METADATA)

            response = HandshakeResponse(self.configuration, self.context)
            self.stream.send_payload(response.encode(self.context), response.type(), reset_sequence=False)

            self._handle_authentication(self.stream.read_payload())
            
            self.connected = True
                
        except Exception as e:
            self.close()
            if isinstance(e, (OperationalError, DatabaseError)):
                raise
            raise OperationalError(f"Handshake failed: {e}")

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
            self.stream.sequence.set(1)
        except Exception as e:
            raise OperationalError(f"Failed to upgrade socket to SSL: {e}")
    

    # =========================================================================
    # Authentication
    # =========================================================================

    def _handle_authentication(self, packet: bytes) -> None:
        """Process authentication response from server"""
        if len(packet) == 0:
            raise OperationalError("Empty authentication response")
        
        packet_type = packet[0]
        
        if packet_type == self.OK_PACKET:
            OkPacket.decode(packet, self.context)
        elif packet_type == self.ERROR_PACKET:
            raise ErrorPacket.decode(packet, self.context).toError(self.exception_factory)
        elif packet_type == self.EOF_PACKET:
            # Auth switch request or auth more data
            if len(packet) == 1 or (len(packet) > 1 and packet[1] == 0x04):
                # Auth more data
                self._handle_plugin_auth_continue(packet)
            else:
                # Auth switch - server requests different auth plugin
                self._handle_auth_switch(packet)
        else:
            raise OperationalError(f"Unexpected packet during authentication: {packet[0]:02x}")

    def _handle_auth_switch(self, packet: bytearray) -> None:
        """Handle authentication plugin switch request"""
        parser = PayloadParser(packet)
        parser.skip(1)  # Skip 0xFE marker
        plugin_name = parser.read_null_terminated_string()
        auth_data = parser.read_remaining()
        
        try:
            plugin_factory = AuthenticationPluginLoader.get(plugin_name, self.configuration)
            plugin = plugin_factory.initialize(self.configuration.password, auth_data, self.configuration, self.host_address)
            response = plugin.processSync(self.stream, self.context)
            self._handle_auth_final_response(response)
        except DatabaseError as e:
            raise e
        except Exception as e:
            raise OperationalError(f"Authentication plugin '{plugin_name}' failed: {e}")

    # =========================================================================
    # Command Execution
    # =========================================================================

    def _send_message(self, message: ClientMessage, reset_sequence: bool = True) -> None:
        """Send client message to server"""
        encoded = message.encode(self.context)
        self.stream.send_payload(encoded, message.type(), reset_sequence)

    def execute(self, message: ClientMessage, config: 'Configuration' = None, can_redo: bool = False, buffered: bool = True) -> List[Completion]:
        """Execute command and return list of completion results"""
        with self.lock:
            if self.closed:
                raise OperationalError("Connection is closed")
            
            try:            
                self._send_message(message)
                results = []
                
                while True:
                    result_packet: bytearray = self.stream.read_payload()
                    completion = self._parse_result_packet(result_packet, config, message.is_binary(), buffered)
                    results.append(completion)
                    
                    if (self.context.server_status & STATUS.MORE_RESULTS_EXIST) == 0:
                        break
                
                return results
            except DatabaseError as e:
                raise e    
            except Exception as e:
                raise OperationalError(f"Execution failed: {e}")

    # =========================================================================
    # Connection Control
    # =========================================================================

    def ping(self) -> None:
        """Send ping command to server"""
        ping_packet = PingPacket()
        self.execute(ping_packet, self.configuration)

    def change_user(self, user: Optional[str], password: Optional[str], database: Optional[str]) -> None:
        """Change current user and database"""
        try:
            old_conf = self.configuration

            new_conf = Configuration(self.configuration.to_dict())
            new_conf.user = user if user is not None else self.configuration.user
            new_conf.password = password if password is not None else self.configuration.password
            new_conf.database = database if database is not None else self.context.database
            self.configuration = new_conf

            change_user_packet = ChangeUserPacket(new_conf.user, new_conf.password, new_conf.database)
            self._send_message(change_user_packet)
            self._handle_authentication(self.stream.read_payload())
                
        except Exception as e:
            self.configuration = old_conf
            if isinstance(e, DatabaseError):
                raise
            raise OperationalError(f"Change user failed: {e}")

    def close(self) -> None:
        """Close connection and cleanup resources"""
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
        """Set socket timeout in seconds"""
        self.socket_timeout = seconds
        if self.socket:
            self.socket.settimeout(seconds)

    def reset(self) -> None:
        """Reset connection state without reconnecting"""
        self.execute(ResetConnectionPacket(), self.configuration)

    # =========================================================================
    # SSL/TLS Information
    # =========================================================================
    def get_ssl_cipher(self) -> Optional[tuple]:
        """Get current SSL cipher information"""
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
        """Get peer SSL certificate information"""
        if self.socket and isinstance(self.socket, ssl.SSLSocket):
            try:
                return self.socket.getpeercert()
            except:
                pass
        return None

    def get_socket_ip(self) -> Optional[str]:
        """Get socket IP address"""
        if self.socket:
            try:
                peer = self.socket.getpeername()
                return peer[0] if isinstance(peer, tuple) else None
            except:
                pass
        return None

    def _parse_result_packet(self, packet: bytes, config: 'Configuration', is_binary: bool = False, buffered: bool = True) -> Completion:
        """Parse result packet into completion object"""
        if packet[0] == self.OK_PACKET:
            return OkPacket.decode(packet, self.context)
        elif packet[0] == self.ERROR_PACKET:
            raise ErrorPacket.decode(packet, self.context).toError(self.exception_factory)
        else:
            return self._parse_result_set(packet, config, is_binary, buffered)

    def _parse_result_set(self, packet: bytes, config: 'Configuration', is_binary: bool = False, buffered: bool = True) -> 'Completion':
        """Parse result set with column definitions and row data"""
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

            # If unbuffered, create streaming result
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
                        completion = EofPacket.decode(row_packet, self.context)
                    else:
                        completion = OkPacket.decode(row_packet, self.context)

                    from ..result import SyncCompleteResult
                    complete_result = SyncCompleteResult(
                        columns=columns,
                        column_count=column_count,
                        config=config,
                        rows=rows,
                        is_binary=is_binary
                    )
                    completion.result_set = complete_result
                                        
                    return completion               
                    
                else:
                    # Row data packet
                    row_data = self._parse_row_data(row_packet, columns, config, is_binary)
                    rows.append(row_data)
            
            
        except Exception as e:
            raise OperationalError(f"Failed to parse result set: {e}")
    
    def _cleanup_connection(self) -> None:
        """Cleanup socket and stream resources"""       
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
    
    # =========================================================================
    # Prepared Statements
    # =========================================================================
    
    def prepare_statement(self, sql: str) -> PrepareStmtPacket:
        """Prepare SQL statement and return statement info"""
        with self.lock:
            if self.closed:
                raise OperationalError("Connection is closed")
            
            prepare_packet = PreparePacket(sql)
            self._send_message(prepare_packet)
            
            response = self.stream.read_payload()
            return self._parse_prepare_response(response, sql)

    def _parse_prepare_response(self, packet: bytearray, sql: str) -> PrepareStmtPacket:
        """Parse COM_STMT_PREPARE response packet"""
        if len(packet) == 0:
            raise OperationalError("Empty prepare response packet")
        
        packet_type = packet[0]
        
        if packet_type == self.ERROR_PACKET:
            raise ErrorPacket.decode(packet, self.context).toError(self.exception_factory)
        elif packet_type == 0x00:
            prepare_stmt_packet = PrepareStmtPacket.decode(packet, self.context)

            # Read parameter metadata if present
            if prepare_stmt_packet.parameter_count > 0:
                # Skip parameter metadata
                for _ in range(prepare_stmt_packet.parameter_count):
                    self.stream.read_payload()                

                if not self.context.isEofDeprecated():
                    self.stream.read_payload()
            
            # Read column metadata if present
            if prepare_stmt_packet.column_count > 0:
                columns = []
                for _ in range(prepare_stmt_packet.column_count):
                    columns.append(ColumnDefinitionPacket.decode(self.stream.read_payload(), self.context))
                prepare_stmt_packet.columns = columns
                
                if not self.context.isEofDeprecated():
                    self.stream.read_payload()
            
            return prepare_stmt_packet
        else:
            raise OperationalError(f"Unexpected prepare response packet type: {packet_type}")
    
    def close_prepared_statement(self, stmt: PrepareStmtPacket) -> None:
        """Close prepared statement and free resources"""
        if stmt.is_closed():
            return
        
        try:
            with self.lock:
                if not self.closed:
                    from ..message.client.stmt_close_packet import StmtClosePacket
                    self._send_message(StmtClosePacket(stmt.statement_id))               
        except:
            # Ignore errors when closing
            pass
        finally:
            stmt.close()