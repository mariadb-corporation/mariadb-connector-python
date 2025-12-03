# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Async Client implementation for MariaDB connections

Uses asyncio for non-blocking I/O operations.
"""

import asyncio
import ssl
import struct
import copy
from typing import List, Optional

from mariadb.impl.message.server.ok_packet import OkPacket
from mariadb.impl.message.server.error_packet import ErrorPacket
from mariadb.impl.message.server.eof_packet import EofPacket
from mariadb.impl.message.server.prepare_stmt_packet import PrepareStmtPacket, CachedPrepareStmtPacket
from mariadb.impl.message.server.column_definition_packet import ColumnDefinitionPacket
from .base_client import BaseClient, MAX_PACKET_SIZE
from ..message.payload_reader import PayloadReader
from ..configuration import Configuration
from ..message.client_message import ClientMessage
from ..message.client.handshake_response import HandshakeResponse
from ..message.client.query_packet import QueryPacket
from ..message.client.quit_packet import QuitPacket
from ..message.client.prepare_packet import PreparePacket
from ..message.client.change_user_packet import ChangeUserPacket
from ..plugin.authentication_plugin_loader import AuthenticationPluginLoader
from ..completion import Completion
from ...exceptions import OperationalError, DatabaseError, ProgrammingError
from mariadb_shared.constants import STATUS
from mariadb_shared import constants

# Pre-compiled struct for packet header parsing (3 bytes length + 1 byte sequence)
_STRUCT_PKT_HDR = struct.Struct('<I')  # Read as 4-byte int, mask out sequence


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
        
        # Read buffer management
        self._readbuf: bytearray = bytearray(8192)
        self._read_view: memoryview = memoryview(self._readbuf)
        self._readbuf_capacity: int = 8192  # Cache buffer capacity
        self.max_allowed_packet: int = 0xFFFFFF
        self.cert_fingerprint_validator: Optional['SSLFingerprintValidator'] = None
        self.auth_plugin: Optional['AuthenticationPlugin'] = None
    
    # =========================================================================
    # Packet Reading
    # =========================================================================
    
    def _ensure_read_capacity(self, size: int) -> None:
        """Ensure buffer is large enough, within max_allowed_packet limit"""
        if size > self._readbuf_capacity:
            new_size = min(self.max_allowed_packet + 4, max(size, self._readbuf_capacity * 2))
            new_buf = bytearray(new_size)
            new_buf[:self._readbuf_capacity] = self._readbuf
            self._readbuf = new_buf
            self._read_view = memoryview(self._readbuf)
            self._readbuf_capacity = new_size
    
    async def read_payload(self) -> memoryview:
        """
        Read one complete MariaDB logical packet (may consist of multiple sub-packets)
        
        Returns:
            memoryview of the packet payload
            
        IMPORTANT: Data must be consumed before next read_payload() call
        """
        
        # Read first packet header
        header = await self.reader.readexactly(4)
        # Fast packet header parsing using struct
        header_int = _STRUCT_PKT_HDR.unpack(header)[0]
        pkt_len = header_int & 0xFFFFFF
        self.sequence[0] = (header_int >> 24) & 0xFF
        
        # Read first payload chunk
        self._ensure_read_capacity(pkt_len)
        payload = await self.reader.readexactly(pkt_len)
        self._readbuf[0:pkt_len] = payload
                
        # Fast path: single packet (99.9999% of cases)
        if pkt_len < MAX_PACKET_SIZE:
            return self._read_view[0:pkt_len]
        
        # Slow path: multiple packets (rare)
        result_len = pkt_len
        
        while True:
            # Read next packet header
            header = await self.reader.readexactly(4)
            # Fast packet header parsing using struct
            header_int = _STRUCT_PKT_HDR.unpack(header)[0]
            pkt_len = header_int & 0xFFFFFF
            self.sequence[0] = (header_int >> 24) & 0xFF
            
            # Ensure buffer has space for accumulated result + new chunk
            needed = result_len + pkt_len
            self._ensure_read_capacity(needed)
            
            # Read payload chunk directly after accumulated data
            payload = await self.reader.readexactly(pkt_len)
            self._readbuf[result_len:result_len + pkt_len] = payload
                        
            result_len += pkt_len
            
            # Continuation condition
            if pkt_len < MAX_PACKET_SIZE:
                break
        
        return self._read_view[0:result_len]
    
    # =========================================================================
    # Packet Writing
    # =========================================================================
    
    async def write_payload(self, payload: bytearray, packet_type: str = "", reset_sequence: bool = True) -> None:
        """Write payload with MariaDB packet framing (async version)"""
        if reset_sequence:
            self.sequence[0] = -1
        
        payload_len = len(payload) - 4  # Payload has 4 bytes reserved at start for header
        data_offset = 4  # Data starts after reserved header space
        
        if payload_len == 0:  # Handle empty payload - still need to send header
            self.sequence[0] = (self.sequence[0] + 1) % 256
            payload[0:3] = b'\x00\x00\x00'
            payload[3] = self.sequence[0]

            self.writer.write(payload[0:4])
            await self.writer.drain()
            return
        
        payload_view = memoryview(payload)  # Use memoryview to avoid buffer copies when slicing
        sent = 0  # Handle packet splitting for large payloads
        
        while sent < payload_len:
            chunk_size = min(MAX_PACKET_SIZE, payload_len - sent)
            self.sequence[0] = (self.sequence[0] + 1) % 256
            
            chunk_start = data_offset + sent  # Data for this chunk starts at data_offset + sent
            chunk_end = chunk_start + chunk_size
            
            header_pos = chunk_start - 4  # Write header directly into payload at chunk_start - 4
            payload[header_pos] = chunk_size & 0xFF
            payload[header_pos + 1] = (chunk_size >> 8) & 0xFF
            payload[header_pos + 2] = (chunk_size >> 16) & 0xFF
            payload[header_pos + 3] = self.sequence[0]
            
            self.writer.write(payload_view[header_pos:chunk_end])  # Send packet: header + chunk data using memoryview (no copy)
            sent += chunk_size
        
        await self.writer.drain()  # Flush all buffered data
        
        if payload_len % MAX_PACKET_SIZE == 0:  # If last packet was exactly MAX_PACKET_SIZE, send empty packet to signal end
            self.sequence[0] = (self.sequence[0] + 1) % 256
            header = b'\x00\x00\x00' + bytes([self.sequence[0]])
            self.writer.write(header)
            await self.writer.drain()
        
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
        await self.write_payload(message.payload(self.context), message.type(), False)

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
            query_packet = QueryPacket.from_sql(sql_command)
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
        await self.write_payload(message.payload(self.context), message.type(), False)

        try:
            # Import SSL utility
            from .ssl.ssl_utility import SSLUtility
            
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
            self.sequence[0] = 1
            
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
            await self.write_payload(message.payload(self.context), message.type(), True)

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
        parser = PayloadReader(packet)
        parser.skip(1)  # Skip 0xFE marker
        plugin_name = parser.read_null_terminated_string("ascii")
        auth_data = parser.read_remaining()
        # Get authentication plugin
        try:
            plugin_factory = AuthenticationPluginLoader.get(plugin_name, self.configuration)
            plugin = plugin_factory.initialize(self.configuration.password, auth_data, self.configuration, self.host_address)
            self.auth_plugin = plugin
            response: bytearray = await plugin.processAsync(self.read_payload, self.write_payload, self.context)
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
                    
                    query_packet = QueryPacket.from_sql(init_command)
                    
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
                await self.write_payload(message.payload(self.context), message.type(), True)
                return await self._read_result(message.is_binary(), config, buffered, prepare_stmt_packet, message.get_sql())
            except DatabaseError as e:
                raise e    
            except Exception as e:
                raise OperationalError(f"Execution failed: {e}")


    async def execute_stmt(self, sql: str, messages: List[ClientMessage], config: 'Configuration' = None, buffered: bool = True):
        """Execute SQL with prepared statements (with caching), handles prepare if needed"""
        with self.lock:
            if self.closed:
                raise OperationalError("Connection is closed")

            try:
                key = (self.context.database, sql)
                
                # Check cache first
                cached_stmt = self.prepared_statement_cache.get(key)
                if cached_stmt and cached_stmt.acquire():
                    with cached_stmt:
                        all_completions = []
                        for message in messages:
                            message.statement_id = cached_stmt.statement_id
                            await self.write_payload(message.payload(self.context), message.type(), True)
                            completions = await self._read_result(message.is_binary(), config, buffered, cached_stmt)
                            all_completions.append(completions)                        
                        return all_completions
                
                # Not in cache, prepare once and execute all
                from ..message.client.prepare_packet import PreparePacket
                prepare_message = PreparePacket(sql)
                
                # Check if pipelining is enabled and server supports BULK operations
                use_pipeline = (self.configuration.pipeline and 
                               self.context.has_capability(constants.CAPABILITY.BULK_OPERATIONS))
                
                prepareResult = None
                first_error = None
                all_completions = []
                
                try:
                    if use_pipeline:
                        # Pipeline mode: write prepare and all execute messages before reading
                        await self.write_payload(prepare_message.payload(self.context), prepare_message.type(), True)
                        
                        for message in messages:
                            await self.write_payload(message.payload(self.context), message.type(), True)
                        
                        try:
                            prepareResult = await self._parse_prepare_response(await self.read_payload(), sql)
                        except DatabaseError as e:
                            first_error = e
                        
                        # Read all execute results (even if prepare failed)
                        for message in messages:
                            try:
                                completions = await self._read_result(message.is_binary(), config, buffered, prepareResult)
                                all_completions.append(completions)
                            except DatabaseError as e:
                                if not first_error:
                                    first_error = e
                    else:
                        # Non-pipeline mode: read prepare response before writing execute messages
                        await self.write_payload(prepare_message.payload(self.context), prepare_message.type(), True)
                        
                        prepareResult = await self._parse_prepare_response(await self.read_payload(), sql)
                        
                        # Now write and read execute messages
                        for message in messages:
                            message.statement_id = prepareResult.statement_id
                            await self.write_payload(message.payload(self.context), message.type(), True)
                            try:
                                completions = await self._read_result(message.is_binary(), config, buffered, prepareResult)
                                all_completions.append(completions)
                            except DatabaseError as e:
                                if not first_error:
                                    first_error = e
                finally:
                    # Cache and close prepared statement
                    if prepareResult:
                        if self.configuration.cache_prep_stmts:
                            self.prepared_statement_cache[key] = prepareResult
                        prepareResult.close()
                
                if first_error:
                    raise first_error
                return all_completions    

            except DatabaseError as e:
                raise e
            except Exception as e:
                raise OperationalError(f"Execution failed: {e}")



    async def _read_result(self, is_binary: bool, config: 'Configuration' = None, buffered: bool = True, prepare_stmt_packet: Optional[PrepareStmtPacket] = None, sql: str = None) -> List[Completion]:
        # Move imports outside hot path
        from ..result import AsyncStreamingResult, AsyncCompleteResult
        
        results = []
        context = self.context
        ok_packet = self.OK_PACKET
        error_packet = self.ERROR_PACKET
        local_infile_packet = self.LOCAL_INFILE_PACKET
        more_results_mask = STATUS.MORE_RESULTS_EXIST
        
        while True:
            packet = await self.read_payload()
            packet_type = packet[0]
            if packet_type == ok_packet:
                results.append(OkPacket.decode(packet, context))
                if (context.server_status & more_results_mask) == 0:
                    break
                continue
            elif packet_type == error_packet:
                raise ErrorPacket.decode(packet, context).toError(self.exception_factory)
            elif packet_type == local_infile_packet:
                # LOAD DATA LOCAL INFILE request from server
                completion = await self._handle_local_infile(packet, sql)
                results.append(completion)
                if (context.server_status & more_results_mask) == 0:
                    break                
                continue
            
            """Parse result set with column definitions and row data"""
            # Parse column count from first packet
            parser = PayloadReader(packet)
            column_count = parser.read_length_encoded_int()

            # Cache EOF deprecated flag once
            eof_deprecated = context.isEofDeprecated()
            
            # Read column definitions
            columns: List[ColumnDefinitionPacket] = [None] * column_count
            if context.has_capability(constants.CAPABILITY.CACHE_METDATA) and parser.read_byte() == 0:
                # skip metadata
                columns = prepare_stmt_packet.columns
            else:
                for i in range(column_count):
                    col_packet = await self.read_payload()
                    columns[i] = ColumnDefinitionPacket.decode(col_packet, context)
                if prepare_stmt_packet is not None:
                    prepare_stmt_packet.columns = columns
            # Read EOF packet after column definitions (if not deprecated)
            if not eof_deprecated:
                await self.read_payload()  # Skip EOF packet
            
            # Select appropriate row parser based on protocol
            row_parser = self._parse_binary_row_data if is_binary else self._parse_text_row_data

            # If unbuffered, create streaming result
            if not buffered:
                streaming_result = AsyncStreamingResult(self.read_payload,
                    context,
                    columns,
                    column_count,
                    config,
                    row_parser
                )
                
                # Create completion with streaming result
                completion = OkPacket(0,0,0,0,b'')
                completion.result_set = streaming_result
                results.append(completion)
                return results
            
            # Read rows
            rows: List[tuple] = []
            
            # Pre-compute EOF/OK length threshold
            eof_length_threshold = 16777215 if eof_deprecated else 8
            
            while True:
                row_packet = await self.read_payload()
                packet_first_byte = row_packet[0]
                
                # Check for EOF/OK packet (0xFE with length constraint)
                if packet_first_byte == 0xFE and len(row_packet) < eof_length_threshold:
                    if eof_deprecated:
                        completion = OkPacket.decode(row_packet, context)
                    else:
                        completion = EofPacket.decode(row_packet, context)

                    # Apply converters to all rows at once
                    if config.converter:
                        rows = self._apply_converters_to_rows(rows, columns, config)

                    completion.result_set = AsyncCompleteResult(
                        columns,
                        column_count,
                        config,
                        rows
                    )
                    results.append(completion)
                    break
                elif packet_first_byte == error_packet:
                    raise ErrorPacket.decode(row_packet, context).toError(self.exception_factory)
                
                rows.append(row_parser(row_packet, columns, config))

            if (context.server_status & more_results_mask) == 0:
                break
        return results

    async def _handle_local_infile(self, packet: memoryview, sql: str = None) -> Completion:
        """Handle LOAD DATA LOCAL INFILE request from server (async)"""
        import os
        import re
        

        # Read filename from packet (skip 0xFB header)
        parser = PayloadReader(packet)
        parser.skip(1)  # Skip 0xFB
        filename = parser.read_null_terminated_string()
        
        
        # Check if local_infile is enabled
        if self.configuration.local_infile == False:
            # Send empty packet to keep connection state OK
            await self.write_payload(bytearray(4), reset_sequence=False)
            raise ProgrammingError(
                "LOAD DATA LOCAL INFILE is disabled. Set local_infile=True in connection parameters to enable it."
            )

        # Validate filename matches the SQL query (security check)
        if sql and not self._validate_local_filename(sql, filename):
            # Send empty packet to keep connection state OK
            await self.write_payload(bytearray(4), reset_sequence=False)
            raise OperationalError(
                f"LOAD DATA LOCAL INFILE asked for file '{filename}' that doesn't "
                f"correspond to initial query. Possible malicious proxy changing "
                f"server answer! Command interrupted"
            )
        
        # Try to open and send the file
        error = None
        try:
            with open(filename, 'rb') as f:
                # Read and send file in maximum MySQL packet sizes
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    # Send as MySQL packet (header will be added by write_payload)
                    payload = bytearray(4 + len(chunk))
                    payload[4:] = chunk
                    await self.write_payload(payload, reset_sequence=False)
        except FileNotFoundError as e:
            error = OperationalError(f"Could not send file: {e}")
        except Exception as e:
            error = OperationalError(f"Error reading file '{filename}': {e}")
        
        # Send empty packet to signal end of file transfer
        await self.write_payload(bytearray(4), reset_sequence=False)
        
        # Read server's response (OK or ERR packet)
        # This is necessary to keep connection state synchronized
        response = await self.read_payload()
        
        if response[0] == 0x00:  # OK packet
            ok = OkPacket.decode(response, self.context)
            if error:
                raise error
            return ok
       
        # Raise error after reading response if file operation failed
        if error:
            raise error
        
        # Check if server returned an error
        if response[0] == 0xFF:  # ERR packet
            from mariadb.impl.message.server import ErrorPacket
            from mariadb.impl.context import Context
            context = Context()
            raise ErrorPacket.decode(response, context).toError(self.exception_factory)
    
    def _validate_local_filename(self, sql: str, filename: str) -> bool:
        """Validate that filename matches LOAD DATA LOCAL INFILE query"""
        import re
        
        # Escape backslashes in filename for regex
        escaped_filename = re.escape(filename.replace("\\", "\\\\"))
        
        # Pattern to match LOAD DATA LOCAL INFILE with the specific filename
        pattern = (
            r"^((\s[--]|#).*(\r\n|\r|\n)|\s*/\*([^*]|\*[^/])*\*/|.)*"
            r"\s*LOAD\s+(DATA|XML)\s+((LOW_PRIORITY|CONCURRENT)\s+)?"
            r"LOCAL\s+INFILE\s+['\"]" + escaped_filename + r"['\"]"  
        )
        
        return bool(re.search(pattern, sql, re.IGNORECASE))

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
            
            self.prepared_statement_cache.clear()
            
            # Send COM_QUIT packet to gracefully close the connection
            if self.connected and self.writer:
                try:
                    message = QuitPacket()
                    await self.write_payload(message.payload(self.context), message.type(), True)

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
                self.writer.close()
                await asyncio.wait_for(self.writer.wait_closed(), timeout=1.0)
            except (asyncio.TimeoutError, ssl.SSLError, Exception):
                pass
            self.writer = None
        if hasattr(self, 'reader'):
            self.reader = None
        # Read buffer cleanup handled by garbage collection
    
    # =========================================================================
    # Prepared Statements
    # =========================================================================
 
    
    async def _parse_prepare_response(self, packet: memoryview, sql: str) -> PrepareStmtPacket:
        """Parse COM_STMT_PREPARE response packet asynchronously"""
        if len(packet) == 0:
            raise OperationalError("Empty prepare response packet")
        
        packet_type = packet[0]
        
        if packet_type == self.OK_PACKET:
            if self.configuration.cache_prep_stmts:
                prepare_stmt_packet = CachedPrepareStmtPacket.decode(packet, self.context, sql, self._close_prepared_statement)
            else:
                prepare_stmt_packet = PrepareStmtPacket.decode(packet, self.context, sql, self._close_prepared_statement)
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
    
    def _close_prepared_statement(self, stmt: PrepareStmtPacket) -> None:
        """Close prepared statement on server (for cache eviction callback) - sync wrapper"""
        # This is called from __exit__ which is sync, so we schedule the async close
        try:
            loop = asyncio.get_running_loop()
            # Schedule the async close as a task
            loop.create_task(self._close_prepared_statement_async(stmt))
        except RuntimeError:
            # No event loop running, can't close
            pass
    
    async def _close_prepared_statement_async(self, stmt: PrepareStmtPacket) -> None:
        """Async implementation of close prepared statement"""
        if stmt.is_closed():
            return
        
        try:
            if not self.closed:
                from ..message.client.stmt_close_packet import StmtClosePacket
                message = StmtClosePacket(stmt.statement_id)
                await self.write_payload(message.payload(self.context), message.type(), True)
        except:
            # Ignore errors when closing
            pass
