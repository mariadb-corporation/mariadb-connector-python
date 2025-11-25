# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Async Client implementation for MariaDB connections

Uses asyncio for non-blocking I/O operations.
"""

import asyncio
import ssl
import copy
from typing import List, Optional, Any
import logging

from mariadb.impl.message.server.ok_packet import OkPacket
from mariadb.impl.message.server.error_packet import ErrorPacket
from mariadb.impl.message.server.eof_packet import EofPacket
from mariadb.impl.message.server.prepare_stmt_packet import PrepareStmtPacket
from mariadb.impl.message.server.column_definition_packet import ColumnDefinitionPacket
from .base_client import BaseClient
from .socket.payload_parser import PayloadParser
from .socket.write_stream import AsyncWriteStream
from .socket.mutable_int import MutableInt
from ..configuration import Configuration
from ..message.client_message import ClientMessage
from ..message.client.handshake_response import HandshakeResponse
from ..message.client.query_packet import QueryPacket
from ..message.client.quit_packet import QuitPacket
from ..message.client.prepare_packet import PreparePacket
from ..message.client.change_user_packet import ChangeUserPacket
from ..plugin.authentication_plugin_loader import AuthenticationPluginLoader
from ..completion import Completion
from ...exceptions import OperationalError, DatabaseError
from mariadb_shared.constants import STATUS
from mariadb_shared import constants

MAX_PACKET_SIZE = 0xFFFFFF
logger = logging.getLogger(__name__)

class AsyncClient(BaseClient):
    """
    Asynchronous client implementation for MariaDB connections
    
    Handles all low-level protocol communication with the MariaDB server
    using non-blocking I/O operations with asyncio.
 
    """
    
    # =========================================================================
    # Initialization
    # =========================================================================
    
    def __init__(self, configuration: Configuration) -> None:
        """Initialize asynchronous client with configuration and host address"""
        super().__init__(configuration)
        
        # Async-specific attributes
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.write_stream: Optional[AsyncWriteStream] = None
        self.sequence: MutableInt = MutableInt(-1)
        
        # Read buffer management
        self._readbuf: bytearray = bytearray(8192)
        self._read_view: memoryview = memoryview(self._readbuf)
        self.max_allowed_packet: int = 0xFFFFFF
        self.cert_fingerprint_validator: Optional['SSLFingerprintValidator'] = None
        self.auth_plugin: Optional['AuthenticationPlugin'] = None
    
    # =========================================================================
    # Packet Reading
    # =========================================================================
    
    def _ensure_read_capacity(self, size: int) -> None:
        """Ensure buffer is large enough, within max_allowed_packet limit"""
        if size > len(self._readbuf):
            new_size = min(self.max_allowed_packet + 4, max(size, len(self._readbuf) * 2))
            new_buf = bytearray(new_size)
            new_buf[:len(self._readbuf)] = self._readbuf
            self._readbuf = new_buf
            self._read_view = memoryview(self._readbuf)
    
    async def read_payload(self) -> memoryview:
        """
        Read one complete MariaDB logical packet (may consist of multiple sub-packets)
        
        Returns:
            memoryview of the packet payload
            
        IMPORTANT: Data must be consumed before next read_payload() call
        """
        
        # Read first packet header
        header = await self.reader.readexactly(4)
        pkt_len = header[0] | (header[1] << 8) | (header[2] << 16)
        self.sequence.set(header[3])
        
        # Read first payload chunk
        self._ensure_read_capacity(pkt_len)
        payload = await self.reader.readexactly(pkt_len)
        self._readbuf[0:pkt_len] = payload
        
        # Log if debug enabled
        if logger.isEnabledFor(logging.DEBUG):
            from ..debug_utils import hex_dump
            conn_id_str = f"[conn_id={self.context.connection_id}]" if self.context and self.context.connection_id >= 0 else ""
            full_packet = header + payload
            logger.debug(hex_dump(full_packet, f"RECV async: {conn_id_str}"))
        
        # Fast path: single packet (99.9999% of cases)
        if pkt_len < MAX_PACKET_SIZE:
            return self._read_view[0:pkt_len]
        
        # Slow path: multiple packets (rare)
        result_len = pkt_len
        
        while True:
            # Read next packet header
            header = await self.reader.readexactly(4)
            pkt_len = header[0] | (header[1] << 8) | (header[2] << 16)
            self.sequence.set(header[3])
            
            # Ensure buffer has space for accumulated result + new chunk
            needed = result_len + pkt_len
            self._ensure_read_capacity(needed)
            
            # Read payload chunk directly after accumulated data
            payload = await self.reader.readexactly(pkt_len)
            self._readbuf[result_len:result_len + pkt_len] = payload
            
            # Log if debug enabled
            if logger.isEnabledFor(logging.DEBUG):
                conn_id_str = f"[conn_id={self.context.connection_id}]" if self.context and self.context.connection_id >= 0 else ""
                full_packet = header + payload
                logger.debug(hex_dump(full_packet, f"RECV async: {conn_id_str}"))
            
            result_len += pkt_len
            
            # Continuation condition
            if pkt_len < MAX_PACKET_SIZE:
                break
        
        return self._read_view[0:result_len]
        
    async def connect(self) -> None:
        """Establish async connection to MariaDB server with host failover support"""
        if self.connected:
            return
        
        # Get list of hosts to try
        hosts = self.configuration.get_hosts()
        last_exception = None
        
        for hostAddress in hosts:
            try:
                # Update host address for this attempt
                self.host_address = hostAddress
                
                await self._create_socket()
                await self._perform_handshake()
            
                # Ensure autocommit and charset are correctly set
                await self._ensure_default()
                # Execute init command if specified
                if self.configuration.init_command:
                    await self._execute_init_command()

                return  # Success!

            except Exception as e:
                last_exception = e
                await self._cleanup_connection()
                # Continue to next host
                continue

        # All hosts failed
        if last_exception:
            raise last_exception
        raise OperationalError("Connection failed to all hosts")
    
    async def _create_socket(self) -> None:
        """Create and configure async TCP or Unix socket connection"""
        try:
            if self.configuration.unix_socket:
                # Unix socket connection
                if self.connect_timeout:
                    self.reader, self.writer = await asyncio.wait_for(
                        asyncio.open_unix_connection(self.configuration.unix_socket),
                        timeout=self.connect_timeout
                    )
                else:
                    self.reader, self.writer = await asyncio.open_unix_connection(
                        self.configuration.unix_socket
                    )
            else:
                # TCP connection
                if self.connect_timeout:
                    self.reader, self.writer = await asyncio.wait_for(
                        asyncio.open_connection(self.host_address.host, self.host_address.port),
                        timeout=self.connect_timeout
                    )
                else:
                    self.reader, self.writer = await asyncio.open_connection(
                        self.host_address.host,
                        self.host_address.port
                    )
            
            self.write_stream = AsyncWriteStream(self.writer)
            # Share the same sequence counter
            self.write_stream.sequence = self.sequence
            
        except Exception as e:
            if self.writer:
                self.writer.close()
                try:
                    await self.writer.wait_closed()
                except:
                    pass
            self.reader = None
            self.writer = None
            # Use errno 2002 for connection errors (Can't connect to server)
            raise self.exception_factory.create_exception(
                f"Failed to create socket server on '{self.host_address.host}':{self.host_address.port}: {e}", 
                errno=2002, 
                sql_state='HY000'
            )
    
    async def _perform_handshake(self) -> None:
        """Perform initial handshake and authentication with server asynchronously"""
        # Read initial handshake packet from server
        handshake_packet = await self.read_payload()
        if (handshake_packet[0] == 0xff):
            raise ErrorPacket.decode(handshake_packet).toError(self.exception_factory)

        self.context = self._parse_handshake(handshake_packet)
        self.write_stream.connection_id = self.context.connection_id
        
        client_capabilities = self._calculate_client_capabilities()

        # Handle SSL if enabled
        if self.configuration.ssl:
            await self._handle_ssl_connection(client_capabilities)
        
        # Store client capabilities in context for later use
        self.context.client_capabilities = client_capabilities
        self.context.eof_deprecated = bool(client_capabilities & constants.CAPABILITY.DEPRECATE_EOF)
        self.context.extended_metadata = bool(client_capabilities & constants.CAPABILITY.EXTENDED_METADATA)

        # Initialize auth plugin for handshake response (default: mysql_native_password)
        from ..plugin.authentication.native_password_plugin import NativePasswordPlugin
        self.auth_plugin = NativePasswordPlugin(self.configuration.password, self.context.auth_data)

        # Create and send handshake response
        message = HandshakeResponse(self.configuration, self.context)
        await self.write_stream.write_payload(message.payload(self.context), message.type(), False)

        # Handle authentication (may involve multiple rounds)
        auth_result = await self.read_payload()
        await self._handle_authentication(auth_result)
        
        self.connected = True
    
    async def _ensure_default(self) -> None:
        """Ensure autocommit and charset are correctly set"""
        sql_commands = []
        if ((self.context.server_status & constants.STATUS.AUTOCOMMIT) > 0) != self.configuration.autocommit:
            sql_commands.append('autocommit = ' + str(int(self.configuration.autocommit)))
        if (self.context.charset != 'utf8mb4'):
            sql_commands.append('NAMES utf8mb4')
            self.context.charset = 'utf8mb4'

        if len(sql_commands) > 0:
            sql_command = 'SET ' + ', '.join(sql_commands)
            query_packet = QueryPacket(sql_command)
            await self.execute(query_packet, self.configuration)
    
    # _parse_handshake() and _calculate_client_capabilities() are inherited from BaseClient
    
    async def _handle_ssl_connection(self, client_capabilities: int) -> None:
        """Setup SSL/TLS connection if configured"""
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
        await self.write_stream.write_payload(message.payload(self.context), message.type(), False)

        try:
            # Import SSL utility
            from .socket.ssl_utility import SSLUtility
            
            # Prepare SSL context with optional fingerprint validation
            ssl_context, self.cert_fingerprint_validator = SSLUtility.prepare_ssl_context(
                self.configuration,
                self.context
            )
            # Get the transport and protocol from the writer
            transport = self.writer.transport
            protocol = transport.get_protocol()
            
            # Get the event loop
            loop = asyncio.get_event_loop()
            
            # Determine server hostname for SSL verification
            server_hostname = None
            if self.configuration.ssl_verify_cert and not self.cert_fingerprint_validator:
                server_hostname = self.host_address.host
            
            # Perform TLS upgrade using loop.start_tls()
            # This returns a new SSL transport
            new_transport = await loop.start_tls(
                transport,
                protocol,
                ssl_context,
                server_side=False,
                server_hostname=server_hostname
            )
            
            # Capture fingerprint if using fingerprint validation
            if self.cert_fingerprint_validator:
                # Get the SSL socket from the transport
                ssl_socket = new_transport.get_extra_info('ssl_object')
                if ssl_socket:
                    self.cert_fingerprint_validator.capture_fingerprint(ssl_socket)

            # After start_tls, the protocol's transport is updated automatically
            # The existing reader and writer now use the SSL transport
            # Update the stream's writer transport reference
            self.writer._transport = new_transport
            
            # Update the stream sequence for the next packet
            self.sequence.set(1)
            
        except ssl.SSLError as e:
            # SSL-specific error - close transport immediately to avoid cleanup issues
            try:
                transport.close()
            except:
                pass
            raise OperationalError(f"SSL handshake failed: {e}")
        except Exception as e:
            raise OperationalError(f"Failed to upgrade socket to SSL: {e}")


    async def change_user(self, user: Optional[str], password: Optional[str], database: Optional[str]) -> None:
        """Change current user and database"""
        try:
            old_conf = self.configuration

            new_conf = copy.copy(self.configuration)
            new_conf.user = user if user is not None else self.configuration.user
            new_conf.password = password if password is not None else self.configuration.password
            new_conf.database = database if database is not None else self.context.database
            self.configuration = new_conf

            message = ChangeUserPacket(new_conf.user, new_conf.password, new_conf.database)
            await self.write_stream.write_payload(message.payload(self.context), message.type(), True)

            # Read initial authentication result
            auth_result = await self.read_payload()
            await self._handle_authentication(auth_result)
                
        except Exception as e:
            self.configuration = old_conf
            if isinstance(e, DatabaseError):
                raise
            raise OperationalError(f"Change user failed: {e}")

    async def _handle_authentication(self, auth_result: memoryview) -> None:
        """Process authentication response from server using plugin system"""
        # Import plugin system
        from ..plugin.authentication.plugin_registry import register_builtin_plugins
        
        # Ensure plugins are registered
        register_builtin_plugins()

        # Check if server requests plugin authentication
        packet_type = auth_result[0]
        
        if packet_type == self.OK_PACKET:
            # OK packet - authentication successful with handshake response
            ok_packet = OkPacket.decode(auth_result, self.context)
            # Validate SSL fingerprint if needed
            self.validate_ssl_fingerprint(ok_packet)
        elif packet_type == self.ERROR_PACKET:
            # Error packet - authentication failed
            raise ErrorPacket.decode(auth_result, self.context).toError(self.exception_factory)
        elif packet_type == self.AUTH_SWITCH_REQUEST_PACKET:
            # Auth switch request - server wants different plugin
            await self._handle_auth_switch(auth_result)
        else:
            raise OperationalError(f"Unexpected packet during authentication: {packet_type:02x}")
        
    async def _handle_auth_switch(self, packet: memoryview) -> None:
        """Handle authentication plugin switch request"""
        parser = PayloadParser(packet)
        parser.skip(1)  # Skip 0xFE marker
        plugin_name = parser.read_null_terminated_string("ascii")
        auth_data = parser.read_remaining()
        # Get authentication plugin
        try:
            plugin_factory = AuthenticationPluginLoader.get(plugin_name, self.configuration)
            plugin = plugin_factory.initialize(self.configuration.password, auth_data, self.configuration, self.host_address)
            self.auth_plugin = plugin
            response: bytearray = await plugin.processAsync(self.read_payload, self.write_stream, self.context)
            await self._handle_authentication(response)
        except DatabaseError as e:
            raise e            
        except Exception as e:
            raise OperationalError(f"Authentication plugin '{plugin_name}' failed: {e}")
    
    # _handle_plugin_auth_continue() and _handle_auth_final_response() inherited from BaseClient
    
    async def _execute_init_command(self) -> None:
        """Execute initialization command if specified in configuration"""
        if self.configuration.init_command:
            try:
                init_command = self.configuration.init_command.strip()
                if init_command:
                    # Use the existing QueryPacket and execute method
                    from ...impl.message.client.query_packet import QueryPacket
                    
                    query_packet = QueryPacket(init_command)
                    
                    # Execute the query - this handles all the packet framing and response parsing
                    await self.execute(query_packet, self.configuration)
                    
            except Exception as e:
                raise OperationalError(f"Failed to execute init command '{self.configuration.init_command}': {e}")

    async def execute(self, message: ClientMessage, config: 'Configuration' = None, buffered: bool = True, prepare_stmt_packet: Optional[PrepareStmtPacket] = None) -> List[Completion]:
        """Execute command and return list of completion results"""
        with self.lock:
            if self.closed:
                raise OperationalError("Connection is closed")
            
            try:
                await self.write_stream.write_payload(message.payload(self.context), message.type(), True)
                results = []
                
                is_binary = message.is_binary()
                while True:
                    packet = await self.read_payload()
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
                                col_packet = await self.read_payload()
                                columns[i] = ColumnDefinitionPacket.decode(col_packet, self.context)
                        
                        # Read EOF packet after column definitions (if not deprecated)
                        if not self.context.isEofDeprecated():
                            await self.read_payload()  # Skip EOF packet

                        # Build decoder list once for all rows (performance optimization)
                        decoders = self._build_decoder_list(columns, is_binary)
                        
                        # Select appropriate row parser based on protocol
                        row_parser = self._parse_binary_row_data if is_binary else self._parse_text_row_data

                        # If unbuffered, create streaming result
                        if not buffered:
                            from ..result import AsyncStreamingResult
                            streaming_result = AsyncStreamingResult(self.read_payload,
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
                                row_packet = await self.read_payload()
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

                                    from ..result import AsyncCompleteResult
                                    complete_result = AsyncCompleteResult(
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
    
    async def ping(self) -> None:
        """Send ping command to server asynchronously"""
        from ..message.client.ping_packet import PingPacket
        await self.execute(PingPacket(), self.configuration)
    
    async def close(self) -> None:
        """Close connection and cleanup resources asynchronously"""
        with self.lock:
            if self.closed:
                return
            
            # Send COM_QUIT packet to gracefully close the connection
            if self.connected and self.writer:
                try:
                    message = QuitPacket()
                    await self.write_stream.write_payload(message.payload(self.context), message.type(), True)

                    await self.writer.drain()
                except Exception:
                    # Ignore errors when sending quit - connection may already be broken
                    pass
            self.closed = True
            self.connected = False
            await self._cleanup_connection()
    
    # =========================================================================
    # SSL/TLS Information
    # =========================================================================
    
    def get_ssl_cipher(self) -> Optional[tuple]:
        """Get current SSL cipher information"""
        if self.writer and hasattr(self.writer, '_transport'):
            transport = self.writer._transport
            if hasattr(transport, 'get_extra_info'):
                ssl_object = transport.get_extra_info('ssl_object')
                if ssl_object and hasattr(ssl_object, 'cipher'):
                    try:
                        return ssl_object.cipher()
                    except:
                        return None
        return None
    
    def get_ssl_version(self) -> Optional[str]:
        """Get current TLS/SSL version string"""
        if self.writer and hasattr(self.writer, '_transport'):
            transport = self.writer._transport
            if hasattr(transport, 'get_extra_info'):
                ssl_object = transport.get_extra_info('ssl_object')
                if ssl_object and hasattr(ssl_object, 'version'):
                    try:
                        return ssl_object.version()
                    except:
                        return None
        return None
    
    def get_peer_certificate(self) -> Optional[dict]:
        """Get peer SSL certificate information"""
        if self.writer and hasattr(self.writer, '_transport'):
            transport = self.writer._transport
            if hasattr(transport, 'get_extra_info'):
                ssl_object = transport.get_extra_info('ssl_object')
                if ssl_object and hasattr(ssl_object, 'getpeercert'):
                    try:
                        return ssl_object.getpeercert()
                    except:
                        return None
        return None
    
    async def _cleanup_connection(self) -> None:
        """Cleanup socket and stream resources asynchronously"""       
        if hasattr(self, 'writer') and self.writer:
            try:
                self.write_stream.writer.close()
                await asyncio.wait_for(self.writer.wait_closed(), timeout=1.0)
            except (asyncio.TimeoutError, ssl.SSLError, Exception):
                pass
            self.writer = None
        if hasattr(self, 'reader'):
            self.reader = None
        # Read buffer cleanup handled by garbage collection
        if hasattr(self, 'write_stream'):
            self.write_stream = None
    
    # =========================================================================
    # Prepared Statements
    # =========================================================================
    
    async def prepare_statement(self, sql: str) -> PrepareStmtPacket:
        """Prepare SQL statement and return statement info asynchronously"""
        with self.lock:
            if self.closed:
                raise OperationalError("Connection is closed")
            
            message = PreparePacket(sql)
            await self.write_stream.write_payload(message.payload(self.context), message.type(), True)

            return await self._parse_prepare_response(await self.read_payload(), sql)
    
    async def _parse_prepare_response(self, packet: memoryview, sql: str) -> PrepareStmtPacket:
        """Parse COM_STMT_PREPARE response packet asynchronously"""
        if len(packet) == 0:
            raise OperationalError("Empty prepare response packet")
        
        packet_type = packet[0]
        
        if packet_type == self.OK_PACKET:
            prepare_stmt_packet = PrepareStmtPacket.decode(packet, self.context)
            # Read parameter metadata if present
            if prepare_stmt_packet.parameter_count > 0:
                # Skip parameter metadata
                for _ in range(prepare_stmt_packet.parameter_count):
                    await self.read_payload()  # Skip EOF packet                

                # Read EOF packet after parameters (if not deprecated)
                if not self.context.isEofDeprecated():
                    await self.read_payload()  # Skip EOF packet
            
            # Read column metadata if present
            if prepare_stmt_packet.column_count > 0:
                columns = []
                for _ in range(prepare_stmt_packet.column_count):
                    columns.append(ColumnDefinitionPacket.decode(await self.read_payload(), self.context))
                prepare_stmt_packet.columns = columns
                
                # Read EOF packet after columns (if not deprecated)
                if not self.context.isEofDeprecated():
                    await self.read_payload()  # Skip EOF packet
            
            return prepare_stmt_packet
        elif packet_type == self.ERROR_PACKET:
            # Error packet
            raise ErrorPacket.decode(packet, self.context).toError(self.exception_factory)
        else:
            raise OperationalError(f"Unexpected prepare response packet type: {packet_type}")
    
    async def close_prepared_statement(self, stmt: PrepareStmtPacket) -> None:
        """Close prepared statement and free resources asynchronously"""
        if stmt.is_closed():
            return
        
        try:
            # Send COM_STMT_CLOSE packet
            with self.lock:
                if not self.closed:
                    from ..message.client.stmt_close_packet import StmtClosePacket
                    message = StmtClosePacket(stmt.statement_id)
                    await self.write_stream.write_payload(message.payload(self.context), message.type(), True)               
        except Exception as e:
            pass
        finally:
            stmt.close()