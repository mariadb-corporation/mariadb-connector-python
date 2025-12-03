# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Sync Client implementation for MariaDB connections

Uses blocking I/O operations.
"""

from re import M
import socket
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
from ..message.client.ping_packet import PingPacket
from ..message.client.quit_packet import QuitPacket
from ..message.client.prepare_packet import PreparePacket
from ..message.client.change_user_packet import ChangeUserPacket
from ..plugin.authentication_plugin_loader import AuthenticationPluginLoader
from ..completion import Completion
from ...exceptions import OperationalError, DatabaseError, ProgrammingError
from mariadb_shared.constants import STATUS
from mariadb_shared import constants

_STRUCT_PKT_HDR = struct.Struct('<I')

MAX_PACKET_SIZE = 0xFFFFFF

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
        
        # Read buffer management
        self._default_recv_buf: bytearray = bytearray(8192)
        self._recv_buf: bytearray = self._default_recv_buf
        self._recv_buf_mv = memoryview(self._recv_buf)
        self._recv_buf_capacity = 8192  # Cache buffer capacity
        self._recv_pos = 0
        self._recv_len = 0


    # =========================================================================
    # Packet Reading
    # =========================================================================
    def _ensure_space(self, needed):
        """
        Resize buffer if necessary.
        """
        ALIGN = 16384 
        if (self._recv_buf_capacity - self._recv_len >= needed):
            return
        grow_size = (needed + ALIGN - 1) & ~(ALIGN - 1)
        self._recv_buf = self._recv_buf + bytearray(grow_size)
        self._recv_buf_mv = memoryview(self._recv_buf)
        self._recv_buf_capacity += grow_size
                

    def _recv_into_buffer(self, size=0):
        """
        Reads data from a blocking socket into a memoryview.

        - If `size` is specified, it attempts to read exactly `size` bytes (blocking until done).
        - If `size` is None, it reads whatever is currently available in the socket buffer.

        Returns the number of bytes read.
        """
        

        received = 0

        # Keep trying to read until we have enough data or there's nothing left
        try:
            if size == 0:
                n = self.socket.recv_into(self._recv_buf_mv[self._recv_len + received:])
                if n == 0:
                    raise ConnectionError("Connection reset by peer")
                return n
            while received < size:
                n = self.socket.recv_into(self._recv_buf_mv[self._recv_len + received:], size - received)
                if n == 0:
                    raise ConnectionError("Connection reset by peer")
                received += n
            return received

        except socket.timeout:
            raise TimeoutError("Socket recv timed out")

        except ConnectionResetError:
            raise ConnectionError("Connection reset by peer")

        except OSError as e:
            # Generic socket error (broken pipe, network down, etc.)
            raise ConnectionError(f"Socket error: {e}") from e

    def read_payload(self):
        """
        Reads and returns a full packet from database server

        Returns a tuple which contains packet size and first offset
        of the buffer

        """
        # Constants for faster local lookup
        PKT_HDR_SIZE = 4
        MAX_PKT_SIZE = 0xFFFFFF

        # if everything was read - rewind buffer
        if self._recv_pos >= self._recv_len:
           self._recv_pos = 0
           self._recv_len = 0

        if self._recv_pos > 0 and self._recv_buf_capacity - self._recv_len < 1024:
            unread = self._recv_len - self._recv_pos
            if unread > 0:
                self._recv_buf[:unread] = self._recv_buf[self._recv_pos:self._recv_len]
            self._recv_len = unread
            self._recv_pos = 0

        first_pos = self._recv_pos
        total_size = 0
        packet_count = 0

        while True:
            bytes_in_buffer = self._recv_len - self._recv_pos

            if bytes_in_buffer > 0:
                # buffer must contain at least a packet header
                if bytes_in_buffer < PKT_HDR_SIZE:
                    missing = PKT_HDR_SIZE - bytes_in_buffer
                    self._ensure_space(missing)
                    self._recv_len += self._recv_into_buffer(missing)
                    continue

                # Fast packet header parsing using struct
                header_int = _STRUCT_PKT_HDR.unpack_from(self._recv_buf, self._recv_pos)[0]
                packet_length = header_int & 0xFFFFFF
                sequence = (header_int >> 24) & 0xFF
                self.sequence[0] = sequence

                # check if we have complete packet data
                packet_total = PKT_HDR_SIZE + packet_length
                if bytes_in_buffer < packet_total:
                    # Need to read more data
                    missing = packet_total - bytes_in_buffer
                    # For MAX_PKT_SIZE packets, also try to read next packet header
                    if packet_length == MAX_PKT_SIZE:
                        missing += PKT_HDR_SIZE
                    self._ensure_space(missing)
                    self._recv_len += self._recv_into_buffer(missing)
                    continue

                # We have complete packet (header + payload)
                packet_count += 1
                
                # Fast path: single packet (most common case)
                if packet_length < MAX_PKT_SIZE and packet_count == 1:
                    # Single packet fast path - no compaction needed
                    result_start = self._recv_pos + PKT_HDR_SIZE
                    result_end = self._recv_pos + packet_total
                    self._recv_pos = result_end
                    return self._recv_buf_mv[result_start:result_end]
                
                # Multi-packet handling (MAX_PKT_SIZE)
                if packet_count > 1:
                    # Compact by removing intermediate header
                    payload_src = self._recv_pos + PKT_HDR_SIZE
                    payload_dst = first_pos + PKT_HDR_SIZE + total_size
                    if payload_src != payload_dst:
                        # Calculate how much data is after this packet
                        data_after_packet = self._recv_len - (self._recv_pos + packet_total)
                        # Move this packet's payload
                        self._recv_buf[payload_dst:payload_dst + packet_length] = \
                            self._recv_buf[payload_src:payload_src + packet_length]
                        # Move any data after this packet
                        if data_after_packet > 0:
                            self._recv_buf[payload_dst + packet_length:payload_dst + packet_length + data_after_packet] = \
                                self._recv_buf[self._recv_pos + packet_total:self._recv_len]
                        # After compaction, adjust buffer length to account for removed header
                        self._recv_len -= PKT_HDR_SIZE
                
                total_size += packet_length

                # Check if this is the last packet
                if packet_length < MAX_PKT_SIZE:
                    # Last packet in multi-packet sequence - return complete result
                    result_start = first_pos + PKT_HDR_SIZE
                    result_end = first_pos + PKT_HDR_SIZE + total_size
                    self._recv_pos = result_end
                    return self._recv_buf_mv[result_start:result_end]

                # Multi-packet: advance to next packet header
                # After compaction, the next header is immediately after current payload
                if packet_count > 1:
                    # After compaction, next header is at: first_pos + PKT_HDR_SIZE + total_size
                    self._recv_pos = first_pos + PKT_HDR_SIZE + total_size
                else:
                    # First packet, no compaction yet
                    self._recv_pos += packet_total
            else:
                # No data in buffer, read more
                self._recv_len += self._recv_into_buffer(0)

    def reset_buffer(self):
        self._recv_buf = self._default_recv_buf
        self._recv_buf_mv = memoryview(self._recv_buf)
        self._recv_buf_capacity = len(self._default_recv_buf)
        self._recv_pos = 0
        self._recv_len = 0

    # =========================================================================
    # Packet Writing
    # =========================================================================
    
    def write_payload(self, payload: bytearray, packet_type: str = "", reset_sequence: bool = True) -> None:
        """Write payload with MariaDB packet framing (sync version)"""
        if reset_sequence:
            self.sequence[0] = -1
        
        payload_len = len(payload) - 4  # Payload has 4 bytes reserved at start for header
        data_offset = 4  # Data starts after reserved header space
        
        if payload_len == 0:  # Handle empty payload - still need to send header
            self.sequence[0] = (self.sequence[0] + 1) % 256
            payload[0:3] = b'\x00\x00\x00'
            payload[3] = self.sequence[0]
            
            self.socket.sendall(payload[0:4])
            return
        
        payload_view = memoryview(payload)  # Use memoryview to avoid buffer copies when slicing
        sent = 0  # Handle packet splitting for large payloads
        
        while sent < payload_len:
            chunk_size = min(MAX_PACKET_SIZE, payload_len - sent)
            self.sequence[0] = (self.sequence[0] + 1) % 256
            
            chunk_start = data_offset + sent  # Data for this chunk starts at data_offset + sent
            chunk_end = chunk_start + chunk_size
            
            header_pos = chunk_start - 4  # Write header 4 bytes before the chunk data
            payload[header_pos] = chunk_size & 0xFF
            payload[header_pos + 1] = (chunk_size >> 8) & 0xFF
            payload[header_pos + 2] = (chunk_size >> 16) & 0xFF
            payload[header_pos + 3] = self.sequence[0]
            
            self.socket.sendall(payload_view[header_pos:chunk_end])  # Send packet: header + chunk data using memoryview (no copy)
            sent += chunk_size
        
        if payload_len % MAX_PACKET_SIZE == 0:  # If last packet was exactly MAX_PACKET_SIZE, send empty packet to signal end
            self.sequence[0] = (self.sequence[0] + 1) % 256
            header = b'\x00\x00\x00' + bytes([self.sequence[0]])
            self.socket.sendall(header)

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
                self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

            if self.socket_timeout:
                self.socket.settimeout(self.socket_timeout)
            
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
        self.write_payload(message.payload(self.context), message.type(), False)
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
                query_packet = QueryPacket.from_sql(self.configuration.init_command)
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
        self.write_payload(message.payload(self.context), message.type(), False)
        
        try:
            # Import SSL utility
            from .ssl.ssl_utility import SSLUtility
            
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
            
            # Reset sequence after SSL upgrade
            self.sequence[0] = 1
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
        parser = PayloadReader(packet)
        parser.skip(1)  # Skip 0xFE marker
        plugin_name = parser.read_null_terminated_string("ascii")
        auth_data = parser.read_remaining()
        try:
            plugin_factory = AuthenticationPluginLoader.get(plugin_name, self.configuration)
            plugin = plugin_factory.initialize(self.configuration.password, auth_data, self.configuration, self.host_address)
            # Store plugin for fingerprint validation
            self.auth_plugin = plugin
            response = plugin.processSync(self.read_payload, self.write_payload, self.context)
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
                self.write_payload(message.payload(self.context), message.type(), True)
                self.reset_buffer()
                return self._read_result(message.is_binary(), config, buffered, prepare_stmt_packet, message.get_sql())
            except DatabaseError as e:
                raise e    
            except Exception as e:
                raise OperationalError(f"Execution failed: {e}")

    def execute_stmt(self, sql: str, messages: List[ClientMessage], config: 'Configuration' = None, buffered: bool = True):
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
                            self.write_payload(message.payload(self.context), message.type(), True)
                            self.reset_buffer()
                            completions = self._read_result(message.is_binary(), config, buffered, cached_stmt)
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
                        self.write_payload(prepare_message.payload(self.context), prepare_message.type(), True)
                        
                        for message in messages:
                            self.write_payload(message.payload(self.context), message.type(), True)
                        self.reset_buffer()
                        
                        try:
                            prepareResult = self._parse_prepare_response(self.read_payload(), sql)
                        except DatabaseError as e:
                            first_error = e
                        
                        # Read all execute results (even if prepare failed)
                        for message in messages:
                            try:
                                completions = self._read_result(message.is_binary(), config, buffered, prepareResult)
                                all_completions.append(completions)
                            except DatabaseError as e:
                                if not first_error:
                                    first_error = e
                    else:
                        # Non-pipeline mode: read prepare response before writing execute messages
                        self.write_payload(prepare_message.payload(self.context), prepare_message.type(), True)
                        self.reset_buffer()
                        
                        prepareResult = self._parse_prepare_response(self.read_payload(), sql)
                        
                        # Now write and read execute messages
                        for message in messages:
                            message.statement_id = prepareResult.statement_id
                            self.write_payload(message.payload(self.context), message.type(), True)
                            self.reset_buffer()
                            try:
                                completions = self._read_result(message.is_binary(), config, buffered, prepareResult)
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

    def _read_result(self, is_binary: bool, config: 'Configuration' = None, buffered: bool = True, prepare_stmt_packet: Optional[PrepareStmtPacket] = None, sql: str = None) -> List[Completion]:
        from ..result import SyncStreamingResult, SyncCompleteResult
        
        results = []
        # Cache locals for faster access
        context = self.context
        ok_packet = self.OK_PACKET
        error_packet = self.ERROR_PACKET
        local_infile_packet = self.LOCAL_INFILE_PACKET
        more_results_mask = STATUS.MORE_RESULTS_EXIST
        
        while True:
            packet = self.read_payload()
            packet_type = packet[0]
            if packet_type == ok_packet:
                results.append(OkPacket.decode(packet, context))
                if (context.server_status & more_results_mask) == 0:
                    break
                continue
            elif packet_type == error_packet:
                raise ErrorPacket.decode(packet, context).toError(self.exception_factory)
            elif packet_type == local_infile_packet:
                results.append(self._handle_local_infile(packet, sql))
                # After sending file, read the actual result
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
                    col_packet = self.read_payload()
                    columns[i] = ColumnDefinitionPacket.decode(col_packet, context)
                if prepare_stmt_packet is not None:
                    prepare_stmt_packet.columns = columns
            # Read EOF packet after column definitions (if not deprecated)
            if not eof_deprecated:
                self.read_payload()  # Skip EOF packet
            
            # Select appropriate row parser based on protocol
            row_parser = self._parse_binary_row_data if is_binary else self._parse_text_row_data

            # If unbuffered, create streaming result
            if not buffered:
                streaming_result = SyncStreamingResult(self.read_payload,
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
                row_packet = self.read_payload()
                packet_first_byte = row_packet[0]
                
                # Check for EOF/OK packet (0xFE with length constraint)
                if packet_first_byte == 0xFE and len(row_packet) < eof_length_threshold:
                    if eof_deprecated:
                        completion = OkPacket.decode(row_packet, context)
                    else:
                        completion = EofPacket.decode(row_packet, context)

                    if config.converter:
                        rows = self._apply_converters_to_rows(rows, columns, config)

                    completion.result_set = SyncCompleteResult(
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


    def _handle_local_infile(self, packet: memoryview, sql: str = None) -> Completion:
        """Handle LOAD DATA LOCAL INFILE request from server"""
        import os
        import re
        
        # Read filename from packet (skip 0xFB header)
        parser = PayloadReader(packet)
        parser.skip(1)  # Skip 0xFB
        filename = parser.read_null_terminated_string()
        
        # Check if local_infile is enabled
        if self.configuration.local_infile == False:
            # Send empty packet to keep connection state OK
            self.write_payload(bytearray(4), reset_sequence=False)
            raise ProgrammingError(
                "LOAD DATA LOCAL INFILE is disabled. Set local_infile=True in connection parameters to enable it."
            )

        # Validate filename matches the SQL query (security check)
        if sql and not self._validate_local_filename(sql, filename):
            # Send empty packet to keep connection state OK
            self.write_payload(bytearray(4), reset_sequence=False)
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
                    # Read up to MAX_PACKET_SIZE bytes
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    # Send as MySQL packet (header will be added by write_payload)
                    payload = bytearray(4 + len(chunk))
                    payload[4:] = chunk
                    self.write_payload(payload, reset_sequence=False)
        except FileNotFoundError as e:
            error = OperationalError(f"Could not send file: {e}")
        except Exception as e:
            error = OperationalError(f"Error reading file '{filename}': {e}")
        
        # Send empty packet to signal end of file transfer
        self.write_payload(bytearray(4), reset_sequence=False)
        
        # Read server's response (OK or ERR packet)
        # This is necessary to keep connection state synchronized
        response = self.read_payload()
        
        if response[0] == 0x00:  # OK packet
            ok = OkPacket.decode(packet, self.context)
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

    def ping(self) -> None:
        """Send ping command to server"""
        ping_packet = PingPacket()
        self.execute(ping_packet, self.configuration)

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
            self.write_payload(message.payload(self.context), message.type(), True)
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
            
            # Clear prepared statement cache
            self.prepared_statement_cache.clear()
            
            # Send COM_QUIT packet to gracefully close the connection
            if self.connected and self.socket:
                try:
                    message = QuitPacket()
                    self.write_payload(message.payload(self.context), message.type(), True)
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
            query_packet = QueryPacket.from_sql(sql_command)
            self.execute(query_packet)
    
    # =========================================================================
    # Prepared Statements
    # =========================================================================
  
    def _parse_prepare_response(self, packet: memoryview, sql: str) -> PrepareStmtPacket:
        """Parse COM_STMT_PREPARE response packet"""
        if len(packet) == 0:
            raise OperationalError("Empty prepare response packet")
        
        packet_type = packet[0]
        
        if packet_type == 0x00:
            if self.configuration.cache_prep_stmts:
                prepare_stmt_packet = CachedPrepareStmtPacket.decode(packet, self.context, sql, self._close_prepared_statement)
            else:
                prepare_stmt_packet = PrepareStmtPacket.decode(packet, self.context, sql, self._close_prepared_statement)

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
       
    def _close_prepared_statement(self, stmt: PrepareStmtPacket) -> None:
        """Close prepared statement on server (for cache eviction callback)"""
        if stmt.is_closed():
            return
        
        try:
            if not self.closed:
                from ..message.client.stmt_close_packet import StmtClosePacket
                message = StmtClosePacket(stmt.statement_id)
                self.write_payload(message.payload(self.context), message.type(), True)
        except:
            # Ignore errors when closing
            pass
    