# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Sync Client implementation for MariaDB connections

Uses blocking I/O operations.
"""

from re import M
import socket
import ssl
import copy
from typing import List, Optional
import logging

from mariadb.impl.message.server.ok_packet import OkPacket
from mariadb.impl.message.server.error_packet import ErrorPacket
from mariadb.impl.message.server.eof_packet import EofPacket
from mariadb.impl.message.server.prepare_stmt_packet import PrepareStmtPacket
from mariadb.impl.message.server.column_definition_packet import ColumnDefinitionPacket
from .base_client import BaseClient
from .socket.payload_parser import PayloadParser
from .socket.write_stream import SyncWriteStream
from .socket.mutable_int import MutableInt
from ..configuration import Configuration
from ..message.client_message import ClientMessage
from ..message.client.handshake_response import HandshakeResponse
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

MAX_PACKET_SIZE = 0xFFFFFF

class SyncClient(BaseClient):
    """
    Synchronous client implementation for MariaDB connections
    
    Handles all low-level protocol communication with the MariaDB server
    using blocking I/O operations.
 
    """

    logger = logging.getLogger(__name__)
    
    # =========================================================================
    # Initialization
    # =========================================================================
    
    def __init__(self, configuration: Configuration) -> None:
        """Initialize synchronous client with configuration and host address"""
        super().__init__(configuration)
        
        # Sync-specific attributes
        self.socket: Optional[socket.socket] = None
        self.write_stream: Optional[SyncWriteStream] = None
        self.sequence: MutableInt = MutableInt(-1)
        
        # Read buffer management
        self.default_readbuf: bytearray = bytearray(8192)
        self.default_read_view: memoryview = memoryview(self.default_readbuf)

        self._readbuf: bytearray = self.default_readbuf
        self._read_view: memoryview = self.default_read_view
        self.max_allowed_packet: int = 0xFFFFFF

    # =========================================================================
    # Packet Reading
    # =========================================================================
    
    def _recv_exact(self, size: int, offset: int) -> None:
        """Read exactly size bytes into buffer at offset"""
        view = self._read_view[offset:offset + size]
        pos = 0
        while pos < size:
            chunk = self.socket.recv_into(view[pos:], size - pos)
            if chunk == 0:
                raise OperationalError("Connection lost during packet read")
            pos += chunk
    
    def reset_buffer(self) -> None:
        self._readbuf = self.default_readbuf
        self._read_view = self.default_read_view

    def _ensure_read_capacity(self, size: int) -> None:
        """Ensure buffer is large enough, within max_allowed_packet limit"""
        if size > len(self._readbuf):
            new_buf = bytearray(size)
            new_buf[:len(self._readbuf)] = self._readbuf
            self._readbuf = new_buf
            self._read_view = memoryview(self._readbuf)
    
    def read_payload(self) -> memoryview:
        """
        Read one complete MariaDB logical packet (may consist of multiple sub-packets)
        
        Returns:
            memoryview of the packet payload
            
        IMPORTANT: Data must be consumed before next read_payload() call
        """
        # Read first packet to determine if we need continuation
        self._recv_exact(4, 0)
        pkt_len = self._readbuf[0] | (self._readbuf[1] << 8) | (self._readbuf[2] << 16)
        self.sequence.set(self._readbuf[3])
        
        # Read first payload chunk
        self._ensure_read_capacity(pkt_len + 4)
        self._recv_exact(pkt_len, 4)
        
        # Log if debug enabled
        if self.logger.isEnabledFor(logging.DEBUG):
            from ..debug_utils import hex_dump
            conn_id_str = f"[conn_id={self.context.connection_id}]" if self.context and self.context.connection_id >= 0 else ""
            self.logger.debug(hex_dump(self._readbuf[0:pkt_len + 4], f"RECV sync: {conn_id_str}"))
        
        if pkt_len < MAX_PACKET_SIZE:
            return self._read_view[4:pkt_len + 4]
        
        # multiple packets
        result_offset = 0
        self._readbuf[result_offset:result_offset + pkt_len] = self._read_view[4:pkt_len + 4]
        result_len = pkt_len
        
        while True:
            # Read next packet header
            self._recv_exact(4, 0)
            pkt_len = self._readbuf[0] | (self._readbuf[1] << 8) | (self._readbuf[2] << 16)
            self.sequence.set(self._readbuf[3])
            
            # Ensure buffer has space for accumulated result + new chunk
            needed = result_len + pkt_len + 4
            self._ensure_read_capacity(needed)
            
            # Read payload chunk directly after accumulated data
            self._recv_exact(pkt_len, result_len)
            
            # Log if debug enabled
            if self.logger.isEnabledFor(logging.DEBUG):
                from ...debug_utils import hex_dump
                conn_id_str = f"[conn_id={self.context.connection_id}]" if self.context and self.context.connection_id >= 0 else ""
                # Log the header + chunk we just read
                header_and_chunk = bytearray(4 + pkt_len)
                header_and_chunk[0:3] = pkt_len.to_bytes(3, 'little')
                header_and_chunk[3] = self.sequence.get()
                header_and_chunk[4:] = self._readbuf[result_len:result_len + pkt_len]
                self.logger.debug(hex_dump(header_and_chunk, f"RECV sync: {conn_id_str}"))
            
            result_len += pkt_len
            
            # Continuation condition
            if pkt_len < MAX_PACKET_SIZE:
                break
        
        return self._read_view[0:result_len]

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
            
            self.write_stream = SyncWriteStream(self.socket)
            # Share the same sequence counter between read and write
            self.write_stream.sequence = self.sequence
            
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
        handshake_packet = self.read_payload()
        if (handshake_packet[0] == 0xff):
            raise ErrorPacket.decode(handshake_packet).toError(self.exception_factory)
        self.context = self._parse_handshake(handshake_packet)
        
        self.write_stream.connection_id = self.context.connection_id

        client_capabilities = self._calculate_client_capabilities()

        if self.configuration.ssl:
            self._handle_ssl_connection(client_capabilities)

        self.context.client_capabilities = client_capabilities
        self.context.eof_deprecated = bool(client_capabilities & constants.CAPABILITY.DEPRECATE_EOF)
        self.context.extended_metadata = bool(client_capabilities & constants.CAPABILITY.EXTENDED_METADATA)

        # Initialize auth plugin for handshake response (default: mysql_native_password)
        from ..plugin.authentication.native_password_plugin import NativePasswordPlugin
        self.auth_plugin = NativePasswordPlugin(self.configuration.password, self.context.auth_data)

        message = HandshakeResponse(self.configuration, self.context)
        self.write_stream.write_payload(message.payload(self.context), message.type(), False)
        self._handle_authentication(self.read_payload())
        
        self.connected = True

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
        message = SslRequestPacket(client_capabilities)
        self.write_stream.write_payload(message.payload(self.context), message.type(), False)
        
        try:
            # Import SSL utility
            from .socket.ssl_utility import SSLUtility
            
            # Prepare SSL context with optional fingerprint validation
            ssl_context, self.cert_fingerprint_validator = SSLUtility.prepare_ssl_context(
                self.configuration,
                self.context
            )
            
            # Wrap socket with SSL
            self.socket = ssl_context.wrap_socket(
                self.socket,
                server_hostname=self.host_address.host if self.configuration.ssl_verify_cert and not self.cert_fingerprint_validator else None
            )
            
            # Capture fingerprint if using fingerprint validation
            if self.cert_fingerprint_validator:
                self.cert_fingerprint_validator.capture_fingerprint(self.socket)
            
            # Create new write stream with the upgraded connection
            connection_id = self.context.connection_id if self.context else -1
            self.write_stream = SyncWriteStream(self.socket, connection_id)
            # Share the same sequence counter
            self.write_stream.sequence = self.sequence
            self.sequence.set(1)
        except Exception as e:
            raise OperationalError(f"Failed to upgrade socket to SSL: {e}")
    

    # =========================================================================
    # Authentication
    # =========================================================================

    def _handle_authentication(self, packet: memoryview) -> None:
        """Process authentication response from server"""
        if len(packet) == 0:
            raise OperationalError("Empty authentication response")
        
        packet_type = packet[0]
        
        if packet_type == self.OK_PACKET:
            ok_packet = OkPacket.decode(packet, self.context)
            # Validate SSL fingerprint if needed
            self.validate_ssl_fingerprint(ok_packet)
        elif packet_type == self.ERROR_PACKET:
            raise ErrorPacket.decode(packet, self.context).toError(self.exception_factory)
        elif packet_type == self.AUTH_SWITCH_REQUEST_PACKET:
            # Auth switch - server requests different auth plugin
            self._handle_auth_switch(packet)
        else:
            raise OperationalError(f"Unexpected packet during authentication: {packet[0]:02x}")

    def _handle_auth_switch(self, packet: memoryview) -> None:
        """Handle authentication plugin switch request"""
        parser = PayloadParser(packet)
        parser.skip(1)  # Skip 0xFE marker
        plugin_name = parser.read_null_terminated_string("ascii")
        auth_data = parser.read_remaining()
        try:
            plugin_factory = AuthenticationPluginLoader.get(plugin_name, self.configuration)
            plugin = plugin_factory.initialize(self.configuration.password, auth_data, self.configuration, self.host_address)
            # Store plugin for fingerprint validation
            self.auth_plugin = plugin
            response = plugin.processSync(self.read_payload, self.write_stream, self.context)
            self._handle_authentication(response)
        except DatabaseError as e:
            raise e
        except Exception as e:
            raise OperationalError(f"Authentication plugin '{plugin_name}' failed: {e}")
    
    # =========================================================================
    # Command Execution
    # =========================================================================

    def execute(self, message: ClientMessage, config: 'Configuration' = None, buffered: bool = True, prepare_stmt_packet: Optional[PrepareStmtPacket] = None) -> List[Completion]:
        """Execute command and return list of completion results"""
        with self.lock:
            if self.closed:
                raise OperationalError("Connection is closed")
            
            try:
                self.write_stream.write_payload(message.payload(self.context), message.type(), True)
                results = []
                self.reset_buffer()
                is_binary = message.is_binary()
                while True:
                    packet = self.read_payload()
                    if packet[0] == self.OK_PACKET:
                        results.append(OkPacket.decode(packet, self.context))
                    elif packet[0] == self.ERROR_PACKET:
                        raise ErrorPacket.decode(packet, self.context).toError(self.exception_factory)
                    else:
                        """Parse result set with column definitions and row data"""
                        # Parse column count from first packet
                        parser = PayloadParser(packet)
                        column_count = parser.read_length_encoded_int()

                        # Read column definitions
                        columns: List[ColumnDefinitionPacket] = [None] * column_count
                        if self.context.has_capability(constants.CAPABILITY.CACHE_METDATA) and parser.read_byte() == 0:
                            # skip metadata
                            columns = prepare_stmt_packet.columns
                        else:
                            for i in range(column_count):
                                col_packet = self.read_payload()
                                columns[i] = ColumnDefinitionPacket.decode(col_packet, self.context)
                        
                        # Read EOF packet after column definitions (if not deprecated)
                        if not self.context.isEofDeprecated():
                            self.read_payload()  # Skip EOF packet

                        # Build decoder list once for all rows (performance optimization)
                        decoders = self._build_decoder_list(columns, is_binary)
                        
                        # Select appropriate row parser based on protocol
                        row_parser = self._parse_binary_row_data if is_binary else self._parse_text_row_data

                        # If unbuffered, create streaming result
                        if not buffered:
                            from ..result import SyncStreamingResult
                            streaming_result = SyncStreamingResult(self.read_payload,
                                self.context,
                                columns,
                                column_count,
                                config,
                                row_parser,  # Pass appropriate row parser function
                                decoders  # Pass pre-built decoder list
                            )
                            
                            # Create completion with streaming result
                            completion = OkPacket()
                            completion.result_set = streaming_result
                            results.append(completion)
                        else:    
                            # Read rows
                            rows: List[tuple] = []
                            while True:
                                row_packet = self.read_payload()
                                # Check for EOF/OK packet based on DEPRECATE_EOF capability and packet length
                                # EOF/OK packets start with 0xFE and have specific length constraints
                                if (row_packet[0] == 0xFE and 
                                    ((self.context.isEofDeprecated() and len(row_packet) < 16777215) or 
                                    (not self.context.isEofDeprecated() and len(row_packet) < 8))):
                                    
                                    if not self.context.isEofDeprecated():
                                        completion = EofPacket.decode(row_packet, self.context)
                                    else:
                                        completion = OkPacket.decode(row_packet, self.context)

                                    # Apply converters to all rows at once
                                    rows = self._apply_converters_to_rows(rows, columns, config)

                                    from ..result import SyncCompleteResult
                                    complete_result = SyncCompleteResult(
                                        columns,
                                        column_count,
                                        config,
                                        rows
                                    )
                                    completion.result_set = complete_result
                                    results.append(completion)
                                    break
                                elif row_packet[0] == self.ERROR_PACKET:
                                    raise ErrorPacket.decode(row_packet, self.context).toError(self.exception_factory)                                    
                                else:
                                    # Row data packet - use pre-built decoders
                                    rows.append(row_parser(row_packet, columns, config, decoders))
                            
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
        self.execute([ping_packet], self.configuration)

    def change_user(self, user: Optional[str], password: Optional[str], database: Optional[str]) -> None:
        """Change current user and database"""
        try:
            old_conf = self.configuration

            new_conf = copy.copy(self.configuration)
            new_conf.user = user if user is not None else self.configuration.user
            new_conf.password = password if password is not None else self.configuration.password
            new_conf.database = database if database is not None else self.context.database
            self.configuration = new_conf

            message = ChangeUserPacket(new_conf.user, new_conf.password, new_conf.database)
            self.write_stream.write_payload(message.payload(self.context), message.type(), True)
            self._handle_authentication(self.read_payload())
        except DatabaseError as e:
            self.configuration = old_conf
            raise
        except Exception as e:
            self.configuration = old_conf
            raise OperationalError(f"Change user failed: {e}")

    def close(self) -> None:
        """Close connection and cleanup resources"""
        with self.lock:
            if self.closed:
                return
            
            # Send COM_QUIT packet to gracefully close the connection
            if self.connected and self.socket:
                try:
                    message = QuitPacket()
                    self.write_stream.write_payload(message.payload(self.context), message.type(), True)
                except Exception:
                    # Ignore errors when sending quit - connection may already be broken
                    pass
            self.closed = True
            self.connected = False
            self._cleanup_connection()

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

    def _cleanup_connection(self) -> None:
        """Cleanup socket and stream resources"""       
        if hasattr(self, 'socket') and self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
        # Read buffer cleanup handled by garbage collection
        if hasattr(self, 'write_stream'):
            self.write_stream = None
    

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
            
            message = PreparePacket(sql)
            self.write_stream.write_payload(message.payload(self.context), message.type(), True)

            return self._parse_prepare_response(self.read_payload(), sql)

    def _parse_prepare_response(self, packet: memoryview, sql: str) -> PrepareStmtPacket:
        """Parse COM_STMT_PREPARE response packet"""
        if len(packet) == 0:
            raise OperationalError("Empty prepare response packet")
        
        packet_type = packet[0]
        
        if packet_type == 0x00:
            prepare_stmt_packet = PrepareStmtPacket.decode(packet, self.context, sql)

            # Read parameter metadata if present
            if prepare_stmt_packet.parameter_count > 0:
                # Skip parameter metadata
                for _ in range(prepare_stmt_packet.parameter_count):
                    self.read_payload()  # Skip parameter metadata

                if not self.context.isEofDeprecated():
                    self.read_payload()  # Skip EOF packet
            
            # Read column metadata if present
            if prepare_stmt_packet.column_count > 0:
                for _ in range(prepare_stmt_packet.column_count):
                    prepare_stmt_packet.columns.append(ColumnDefinitionPacket.decode(self.read_payload(), self.context))
                
                if not self.context.isEofDeprecated():
                    self.read_payload()  # Skip EOF packet
            
            return prepare_stmt_packet
        elif packet_type == self.ERROR_PACKET:
            raise ErrorPacket.decode(packet, self.context).toError(self.exception_factory)
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
                    message = StmtClosePacket(stmt.statement_id)
                    self.write_stream.write_payload(message.payload(self.context), message.type(), True)
        except:
            # Ignore errors when closing
            pass
        finally:
            stmt.close()