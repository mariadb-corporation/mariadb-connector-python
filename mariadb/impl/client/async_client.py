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

from mariadb.impl.message.server.ok_packet import OkPacket
from mariadb.impl.message.server.error_packet import ErrorPacket
from mariadb.impl.message.server.eof_packet import EofPacket
from mariadb.impl.message.server.prepare_stmt_packet import PrepareStmtPacket
from mariadb.impl.message.server.column_definition_packet import ColumnDefinitionPacket
from .base_client import BaseClient
from .socket.payload_parser import PayloadParser
from .socket.stream import AsyncStream
from ..configuration import Configuration
from ..host_address import HostAddress
from ..message.client_message import ClientMessage
from ..message.client.handshake_response import HandshakeResponse
from ..message.client.reset_connection_packet import ResetConnectionPacket
from ..message.client.query_packet import QueryPacket
from ..message.client.quit_packet import QuitPacket
from ..message.client.prepare_packet import PreparePacket
from ..message.client.change_user_packet import ChangeUserPacket
from ..plugin.authentication_plugin_loader import AuthenticationPluginLoader
from ..completion import Completion
from ...exceptions import OperationalError, DatabaseError, NotSupportedError
from mariadb_shared.constants import STATUS
from mariadb_shared import constants


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
        self.stream: Optional[AsyncStream] = None
        
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
            
            self.stream = AsyncStream(self.reader, self.writer)
            
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
        try:
            # Read initial handshake packet from server
            handshake_packet: bytes = await self.stream.read_payload()
            if (handshake_packet[0] == 0xff):
                raise ErrorPacket.decode(handshake_packet).toError(self.exception_factory)

            self.context = self._parse_handshake(handshake_packet)
            self.stream.connection_id = self.context.connection_id
            
            client_capabilities = self._calculate_client_capabilities()

            # Handle SSL if enabled
            if self.configuration.ssl:
                await self._handle_ssl_connection(client_capabilities)
            
            # Store client capabilities in context for later use
            self.context.client_capabilities = client_capabilities
            self.context.eof_deprecated = bool(client_capabilities & constants.CAPABILITY.DEPRECATE_EOF)
            self.context.extended_metadata = bool(client_capabilities & constants.CAPABILITY.EXTENDED_METADATA)

            # Create and send handshake response
            response = HandshakeResponse(self.configuration, self.context)
            await self.stream.send_payload(response.encode(self.context), response.type(), reset_sequence=False)

            # Handle authentication (may involve multiple rounds)
            await self._handle_authentication()
            
            self.connected = True
                
        except Exception as e:
            # Cleanup without calling close() to avoid masking the original exception
            try:
                await self._cleanup_connection()
            except:
                # Ignore cleanup errors to avoid masking the original exception
                pass
            raise e
    
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
            await self.execute(query_packet, self.configuration, can_redo=True)
    
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
        ssl_request = SslRequestPacket(client_capabilities)
        encoded = ssl_request.encode(self.context)
        await self.stream.send_payload(encoded, ssl_request.type(), False)
        
        try:
            # Upgrade socket to SSL
            # Import SSL utility
            from .socket.ssl_utility import SSLUtility
            
            # Create SSL context
            ssl_context = SSLUtility.create_ssl_context(self.configuration)
            
            # Get the transport and protocol from the writer
            transport = self.writer.transport
            protocol = transport.get_protocol()
            
            # Get the event loop
            loop = asyncio.get_event_loop()
            
            # Perform TLS upgrade using loop.start_tls()
            # This returns a new SSL transport
            new_transport = await loop.start_tls(
                transport,
                protocol,
                ssl_context,
                server_side=False,
                server_hostname=self.configuration.host
            )
            
            # After start_tls, the protocol's transport is updated automatically
            # The existing reader and writer now use the SSL transport
            # Update the stream's writer transport reference
            self.writer._transport = new_transport
            
            # Update the stream sequence for the next packet
            self.stream.sequence.set(1)
            
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

            change_user_packet = ChangeUserPacket(new_conf.user, new_conf.password, new_conf.database)
            await self._send_message(change_user_packet)
            await self._handle_authentication()
                
        except Exception as e:
            self.configuration = old_conf
            if isinstance(e, DatabaseError):
                raise
            raise OperationalError(f"Change user failed: {e}")

    async def _handle_authentication(self) -> None:
        """Process authentication response from server using plugin system"""
        # Import plugin system
        from ..plugin.authentication.plugin_registry import register_builtin_plugins
        
        # Ensure plugins are registered
        register_builtin_plugins()
        
        # Read initial authentication result
        auth_result: bytearray = await self.stream.read_payload()
        
        # Check if server requests plugin authentication
        if len(auth_result) > 0:
            packet_type = auth_result[0]
            
            if packet_type == self.OK_PACKET:
                # OK packet - authentication successful with handshake response
                OkPacket.decode(auth_result, self.context)
                return
            elif packet_type == self.ERROR_PACKET:
                # Error packet - authentication failed
                raise ErrorPacket.decode(auth_result, self.context).toError(self.exception_factory)
            elif packet_type == self.EOF_PACKET:
                # Auth switch request - server wants different plugin
                await self._handle_auth_switch(auth_result)
                return
            else:
                # Continue with plugin authentication
                self._handle_plugin_auth_continue(auth_result)
                return
        
        raise OperationalError("Empty authentication result packet")
    
    async def _handle_auth_switch(self, packet: bytearray) -> None:
        """Handle authentication plugin switch request"""
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
            plugin_factory = AuthenticationPluginLoader.get(plugin_name, self.configuration)
            
            # Initialize plugin
            plugin = plugin_factory.initialize(self.configuration.password, plugin_data, self.configuration, self.host_address)
            
            # Process authentication - plugin will send response and read server's reply
            response: bytearray = await plugin.processAsync(self.stream, self.context)
            
            # Handle final response
            self._handle_auth_final_response(response)
            
        except Exception as e:
            # Re-raise if it's already a proper exception
            if hasattr(e, 'errno') and hasattr(e, 'sqlstate'):
                raise
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
                    await self.execute(query_packet, config=self.configuration, can_redo=False)
                    
            except Exception as e:
                raise OperationalError(f"Failed to execute init command '{self.configuration.init_command}': {e}")

    async def _send_message(self, message: ClientMessage) -> None:
        """Send client message to server"""
        try:
            await self.stream.send_payload(message.encode(self.context), message.type(), reset_sequence=True)
        except NotSupportedError as e:
            raise e    
        except Exception as e:
            raise OperationalError(f"Failed to send message: {e}")
    
    async def execute(self, message: ClientMessage, config: 'Configuration', can_redo: bool = False, buffered: bool = True) -> List[Completion]:
        """Execute command asynchronously and return list of completion results"""
        with self.lock:
            if self.closed:
                raise OperationalError("Connection is closed")
            
            try:
                
                # Send message
                await self._send_message(message)               
                
                # Read and parse results
                results = []
                is_binary = message.is_binary()
                
                # Continue reading results while MORE_RESULTS_EXIST is set
                while True:
                    result_packet: bytes = await self.stream.read_payload()
                    completion = await self._parse_result_packet(result_packet, config, is_binary, buffered)
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
    
    # =========================================================================
    # Connection Control
    # =========================================================================
    
    async def ping(self) -> None:
        """Send ping command to server asynchronously"""
        from ..message.client.ping_packet import PingPacket
        await self.execute(PingPacket(), self.configuration)
    
    async def abort(self, executor: Any) -> None:
        """Abort connection"""
        await self.close()
    
    async def close(self) -> None:
        """Close connection and cleanup resources asynchronously"""
        with self.lock:
            if self.closed:
                return
            
            # Send COM_QUIT packet to gracefully close the connection
            if self.connected and self.writer:
                try:
                    quit_packet = QuitPacket()
                    await self._send_message(quit_packet)
                    await self.writer.drain()
                except Exception:
                    # Ignore errors when sending quit - connection may already be broken
                    pass
            self.closed = True
            self.connected = False
            await self._cleanup_connection()
    
    
    def set_socket_timeout(self, seconds: float) -> None:
        """Set socket timeout in seconds"""
        self.socket_timeout = seconds
        # Note: asyncio doesn't support setting timeout on individual sockets
        # Timeouts should be handled at the operation level using asyncio.wait_for()
    
    async def reset(self) -> None:
        """Reset connection state without reconnecting asynchronously"""
        await self.execute(ResetConnectionPacket())
    
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
    
    def get_socket_ip(self) -> Optional[str]:
        """Get socket IP address"""
        if not self.writer:
            return None
        try:
            peername = self.writer.transport.get_extra_info('peername')
            if peername and isinstance(peername, tuple):
                return peername[0]
        except:
            pass
        return None
    
    async def _parse_result_packet(self, packet: bytes, config: 'Configuration', is_binary: bool = False, buffered: bool = True) -> Completion:
        """Parse result packet into completion object asynchronously"""
        if len(packet) == 0:
            raise OperationalError("Empty result packet")
        
        packet_type = packet[0]
        if packet_type == self.OK_PACKET:
            # OK packet
            return OkPacket.decode(packet, self.context)
        elif packet_type == self.ERROR_PACKET:
            # Error packet
            raise ErrorPacket.decode(packet, self.context).toError(self.exception_factory)
        else:
            # Result set packet - parse according to MySQL/MariaDB protocol
            return await self._parse_result_set(packet, config, is_binary, buffered)
    
    # _parse_ok_packet(), _process_session_tracking(), _process_system_variables(), 
    # and _process_schema_change() are inherited from BaseClient
    
    async def _parse_result_set(self, packet: bytes, config: 'Configuration', is_binary: bool = False, buffered: bool = True) -> 'Completion':
        """Parse result set with column definitions and row data asynchronously"""
        from ..completion import Completion
        
        try:
            # Step 1: Parse column count from first packet
            parser = PayloadParser(packet)
            column_count = parser.read_length_encoded_int()
            
            
            # Step 2: Read column definition packets
            columns: List[ColumnDefinitionPacket] = []
            for i in range(column_count):
                col_packet: bytearray = await self.stream.read_payload()
                columns.append(ColumnDefinitionPacket.decode(col_packet, self.context))
            
            # Step 3: Handle EOF packet after column definitions based on capabilities
            # Check if DEPRECATE_EOF capability is set
            
            if not self.context.isEofDeprecated():
                # skip intermediate EOF packet
                await self.stream.read_payload()
            
            # Step 4: If unbuffered, create streaming result
            if not buffered:
                from ..result import AsyncStreamingResult
                streaming_result = AsyncStreamingResult(
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

            # Step 5: Read row data packets until EOF (buffered mode)
            rows = []
            while True:
                row_packet: bytes = await self.stream.read_payload()
                
                # Check for EOF/OK packet based on DEPRECATE_EOF capability and packet length
                # EOF/OK packets start with 0xFE and have specific length constraints
                if (row_packet[0] == self.EOF_PACKET and 
                    ((self.context.isEofDeprecated() and len(row_packet) < 16777215) or 
                     (not self.context.isEofDeprecated() and len(row_packet) < 8))):
                    
                    if not self.context.isEofDeprecated():
                        # Traditional EOF packet
                        completion = EofPacket.decode(row_packet, self.context)
                    else:
                        # OK packet with 0xFE header (DEPRECATE_EOF enabled) - use existing OK packet parser
                        completion = OkPacket.decode(row_packet, self.context)
                    
                    # Create AsyncCompleteResult with all rows
                    from ..result import AsyncCompleteResult
                    complete_result = AsyncCompleteResult(
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
    
    async def _cleanup_connection(self) -> None:
        """Cleanup socket and stream resources asynchronously"""       
        if hasattr(self, 'writer') and self.writer:
            try:
                self.writer.close()
                await asyncio.wait_for(self.writer.wait_closed(), timeout=1.0)
            except (asyncio.TimeoutError, ssl.SSLError, Exception):
                pass
            self.writer = None
        if hasattr(self, 'reader'):
            self.reader = None
        if hasattr(self, 'stream'):
            self.stream = None
    
    # =========================================================================
    # Prepared Statements
    # =========================================================================
    
    async def prepare_statement(self, sql: str) -> PrepareStmtPacket:
        """Prepare SQL statement and return statement info asynchronously"""
        with self.lock:
            if self.closed:
                raise OperationalError("Connection is closed")
            
            try:
                prepare_packet = PreparePacket(sql)
                await self._send_message(prepare_packet)
                return await self._parse_prepare_response(await self.stream.read_payload(), sql)
                
            except DatabaseError as e:
                raise e
            except Exception as e:
                raise OperationalError(f"Statement preparation failed: {e}")
    
    async def _parse_prepare_response(self, packet: bytearray, sql: str) -> PrepareStmtPacket:
        """Parse COM_STMT_PREPARE response packet asynchronously"""
        if len(packet) == 0:
            raise OperationalError("Empty prepare response packet")
        
        packet_type = packet[0]
        
        if packet_type == self.ERROR_PACKET:
            # Error packet
            raise ErrorPacket.decode(packet, self.context).toError(self.exception_factory)
        elif packet_type == self.OK_PACKET:
            prepare_stmt_packet = PrepareStmtPacket.decode(packet, self.context)
            # Read parameter metadata if present
            if prepare_stmt_packet.parameter_count > 0:
                # Skip parameter metadata
                for _ in range(prepare_stmt_packet.parameter_count):
                    await self.stream.read_payload()                

                # Read EOF packet after parameters (if not deprecated)
                if not self.context.isEofDeprecated():
                    await self.stream.read_payload()
            
            # Read column metadata if present
            if prepare_stmt_packet.column_count > 0:
                columns = []
                for _ in range(prepare_stmt_packet.column_count):
                    columns.append(ColumnDefinitionPacket.decode(await self.stream.read_payload(), self.context))
                prepare_stmt_packet.columns = columns
                
                # Read EOF packet after columns (if not deprecated)
                if not self.context.isEofDeprecated():
                    await self.stream.read_payload()
            
            return prepare_stmt_packet
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
                    await self._send_message(StmtClosePacket(stmt.statement_id))               
        except Exception as e:
            pass
        finally:
            stmt.close()