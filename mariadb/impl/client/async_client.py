# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from __future__ import annotations

"""
Async Client implementation for MariaDB connections

Uses asyncio for non-blocking I/O operations.
"""

import asyncio
import contextlib
import socket
import ssl
import struct
import copy
import sys
from typing import List, Any, overload, cast

from mariadb.impl.message.server.ok_packet import OkPacket
from mariadb.impl.message.server.error_packet import ErrorPacket
from mariadb.impl.message.server.eof_packet import EofPacket
from mariadb.impl.message.server.prepare_stmt_packet import PrepareStmtPacket, CachedPrepareStmtPacket
from mariadb.impl.message.server.column_definition_packet import ColumnsDefinition
from .base_client import BaseClient, find_default_unix_socket, PROTOCOL_TCP, PROTOCOL_SOCKET
from ..message.server.ok_packet import CharsetMismatchError
from .context import Context
from ..message.payload_reader import PayloadReader
from ..configuration import Configuration
from ..message.client_message import ClientMessage
from ..message.client.handshake_response import HandshakeResponse
from ..message.client.query_packet import QueryPacket
from ..message.client.quit_packet import QuitPacket
from ..message.client.change_user_packet import ChangeUserPacket
from ..plugin.authentication_plugin_loader import AuthenticationPluginLoader
from ..completion import Completion
from ..result import AsyncResult, AsyncStreamingResult, AsyncCompleteResult
from ...exceptions import OperationalError, DatabaseError, ProgrammingError
from mariadb_shared.constants import STATUS
from mariadb_shared import constants

# Pre-compiled struct for packet header parsing (3 bytes length + 1 byte sequence)
_unpack_pkt_hdr = struct.Struct('<I').unpack_from
_pack_pkt_hdr = struct.Struct('<I').pack_into

# Cache packet decode methods for faster access
_decode_ok_packet = OkPacket.decode
_decode_error_packet = ErrorPacket.decode
_decode_eof_packet = EofPacket.decode
_MORE_RESULTS_EXIST = STATUS.MORE_RESULTS_EXIST

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

        # Override threading.Lock with asyncio.Lock for async operations
        self.lock : asyncio.Lock = asyncio.Lock()

        # Async-specific attributes
        self.reader: asyncio.StreamReader = None  # type: ignore[assignment]
        self.writer: asyncio.StreamWriter = None  # type: ignore[assignment]

        # Read buffer management
        self._recv_buf: bytearray = bytearray(16384)
        self._default_recv_buf: bytearray = self._recv_buf
        self._recv_buf_mv: memoryview = memoryview(self._recv_buf)
        self._default_recv_buf_mv: memoryview = self._recv_buf_mv
        self._recv_buf_capacity: int = 16384
        self._recv_pos: int = 0  # Current read position in buffer
        self._recv_len: int = 0  # Amount of valid data in buffer
        self.max_allowed_packet: int = 0xFFFFFF

    # =========================================================================
    # Packet Reading
    # =========================================================================

    def _ensure_space(self, needed: int) -> None:
        """Ensure buffer has space for additional data"""
        required = self._recv_len + needed
        if required > self._recv_buf_capacity:
            new_capacity = max(required, min(self.max_allowed_packet + 4, self._recv_buf_capacity * 2))
            new_buf = bytearray(new_capacity)
            new_buf[:self._recv_len] = self._recv_buf[:self._recv_len]
            self._recv_buf = new_buf
            self._recv_buf_mv = memoryview(self._recv_buf)
            self._recv_buf_capacity = new_capacity

    async def _recv_into_buffer(self, min_bytes: int) -> int:
        """Read at least min_bytes into buffer, return actual bytes read."""
        received = 0
        write_pos = self._recv_len
        buf = self._recv_buf
        capacity = self._recv_buf_capacity
        while received < min_bytes:
            # Read as much as the buffer can hold, but at least min_bytes
            max_read = max(capacity - write_pos - received, min_bytes - received)
            data = await self.reader.read(max_read)
            data_len = len(data)
            if data_len == 0:
                return received
            buf[write_pos + received:write_pos + received + data_len] = data
            received += data_len
        return received

    @overload
    async def read_payload(self, packet_count: None = None) -> memoryview: ...
    @overload
    async def read_payload(self, packet_count: int) -> list[tuple[int, int]]: ...

    async def read_payload(self, packet_count: int | None = None) -> memoryview | list[tuple[int, int]]:
        """
        Reads one or more complete packets from database server.

        Args:
            packet_count: Number of packets to read
                None (default): Read 1 packet, return as memoryview
                >= 1 or -1: Read multiple packets, return as list of (start, end) tuples

        Returns:
            packet_count == None: memoryview
            packet_count >= 1 or -1: list of (start, end) tuples
        """
        # --- 1. Top-Level Buffer Maintenance ---
        # Shift data ONLY at the start of the call to protect caller references.
        is_multi = (packet_count is not None)
        if self._recv_pos >= self._recv_len:
            self._recv_pos = 0
            self._recv_len = 0
        elif self._recv_pos > 0 and (is_multi or self._recv_buf_capacity - self._recv_len < 1024):
            unread = self._recv_len - self._recv_pos
            if unread > 0:
                self._recv_buf[:unread] = self._recv_buf[self._recv_pos:self._recv_len]
            self._recv_len = unread
            self._recv_pos = 0

        results: list[tuple[int, int]] = []
        # Convert None to 1 for packet reading logic
        if packet_count is None:
            packet_count = 1

        while True:
            first_pos = self._recv_pos
            total_size = 0
            pkt_seen = 0

            # --- 2. Primary Packet Assembly ---
            while True:
                bytes_in_buffer = self._recv_len - self._recv_pos

                if bytes_in_buffer < 4:
                    if self._recv_len == self._recv_buf_capacity:
                        self._ensure_space(4)

                    got = await self._recv_into_buffer(4 - bytes_in_buffer)
                    if got == 0:  # Connection lost
                        raise ConnectionError("Connection lost during read")
                    self._recv_len += got
                    bytes_in_buffer = self._recv_len - self._recv_pos

                header_int = _unpack_pkt_hdr(self._recv_buf, self._recv_pos)[0]
                packet_length = header_int & 0xFFFFFF
                self.sequence[0] = (header_int >> 24) & 0xFF
                packet_total = 4 + packet_length

                if bytes_in_buffer < packet_total:
                    missing = packet_total - bytes_in_buffer
                    if packet_length == 0xFFFFFF:
                        missing += 4

                    if self._recv_len + missing > self._recv_buf_capacity:
                        self._ensure_space(missing)

                    got = await self._recv_into_buffer(missing)
                    if got == 0:
                        raise ConnectionError("Connection lost during read")
                    self._recv_len += got
                    bytes_in_buffer = self._recv_len - self._recv_pos

                pkt_seen += 1

                # Chained Fragment Compaction logic (> 16MB)
                if pkt_seen > 1:
                    payload_src = self._recv_pos + 4
                    payload_dst = first_pos + 4 + total_size
                    if payload_src != payload_dst:
                        data_after = self._recv_len - (self._recv_pos + packet_total)
                        self._recv_buf[payload_dst:payload_dst + packet_length] = \
                            self._recv_buf[payload_src:payload_src + packet_length]
                        if data_after > 0:
                            # Avoid overlap issues using a temporary slice
                            tmp = self._recv_buf[self._recv_pos + packet_total:self._recv_len]
                            self._recv_buf[payload_dst + packet_length:
                                           payload_dst + packet_length + data_after] = tmp
                        self._recv_len -= 4

                total_size += packet_length

                if packet_length < 0xFFFFFF: # Final fragment seen
                    p_start = first_pos + 4
                    p_end = p_start + total_size
                    self._recv_pos = p_end
                    break

                if not self.connected:
                    raise OperationalError(
                        "Multipart packet (>16 MB) received before authentication "
                        "completed; aborting to prevent unbounded memory allocation"
                    )

                # Move to next fragment header
                if pkt_seen > 1:
                    self._recv_pos = first_pos + 4 + total_size
                else:
                    self._recv_pos += packet_total

            # --- 3. Result Handling ---
            if not is_multi:
                return self._recv_buf_mv[p_start : p_end]

            # Store the (start, end) tuple
            results.append((p_start, p_end))

            # Terminator Logic (0xFE = EOF/OK, 0xFF = ERR)
            first_byte = self._recv_buf[p_start]
            if first_byte >= 0xFE:
                if first_byte == 0xFF or (p_end - p_start) < 0xFFFFFF:
                    return results

            # Reached requested count
            if packet_count > 0 and len(results) >= packet_count:
                return results

            # Stop if buffer exhausted and not in slurp mode
            if self._recv_pos >= self._recv_len and packet_count != -1:
                return results

    def reset_buffer(self) -> None:
        if self._recv_buf is not self._default_recv_buf:
            self._recv_buf = self._default_recv_buf
            self._recv_buf_mv = self._default_recv_buf_mv
            self._recv_buf_capacity = 16384
        self._recv_pos = 0
        self._recv_len = 0

    # =========================================================================
    # Packet Writing
    # =========================================================================

    async def write_payload(self, payload: bytearray, packet_type: str = "", reset_sequence: bool = True) -> None:
        """Write payload with MariaDB packet framing (async version)"""
        if reset_sequence:
            self.sequence[0] = -1

        payload_len = len(payload) - 4  # Payload has 4 bytes reserved at start for header

        if payload_len == 0:  # Handle empty payload - still need to send header
            self.sequence[0] = (self.sequence[0] + 1) % 256
            payload[0:3] = b'\x00\x00\x00'
            payload[3] = self.sequence[0]

            self.writer.write(payload[0:4])
            await self.writer.drain()
            return

        # Fast path: single packet (< 16MB) - avoids memoryview, min(), loop overhead
        if payload_len < 0xFFFFFF:
            self.sequence[0] = (self.sequence[0] + 1) % 256
            _pack_pkt_hdr(payload, 0, payload_len | (self.sequence[0] << 24))
            self.writer.write(payload)
            await self.writer.drain()
            return

        # Slow path: large payload requiring packet splitting
        data_offset = 4
        payload_view = memoryview(payload)
        sent = 0

        while sent < payload_len:
            chunk_size = min(0xFFFFFF, payload_len - sent)
            self.sequence[0] = (self.sequence[0] + 1) % 256

            chunk_start = data_offset + sent
            chunk_end = chunk_start + chunk_size

            self.writer.write(struct.pack('<I', chunk_size | (self.sequence[0] << 24)))
            self.writer.write(payload_view[chunk_start:chunk_end])
            sent += chunk_size

        await self.writer.drain()

        if payload_len % 0xFFFFFF == 0:
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
            unix_socket = self.configuration.unix_socket
            if (not unix_socket
                    and self.configuration.protocol != PROTOCOL_TCP
                    and not sys.platform.startswith('win')
                    and self.host_address.host == 'localhost'):
                unix_socket = find_default_unix_socket()
                if unix_socket:
                    self.configuration.unix_socket = unix_socket
                elif self.configuration.protocol == PROTOCOL_SOCKET:
                    # protocol=SOCKET is a hard request for a Unix socket; do not
                    # silently fall back to TCP
                    raise OperationalError(
                        "protocol=SOCKET requires a Unix socket but none was found "
                        "for this platform; pass unix_socket=<path> explicitly."
                    )

            if unix_socket and self.configuration.protocol != PROTOCOL_TCP:
                if self.connect_timeout:
                    self.reader, self.writer = await asyncio.wait_for(
                        asyncio.open_unix_connection(unix_socket),
                        timeout=self.connect_timeout
                    )
                else:
                    self.reader, self.writer = await asyncio.open_unix_connection(
                        unix_socket
                    )
            else:
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
                _sock = self.writer.get_extra_info('socket')
                if _sock is not None:
                    _sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

        except OperationalError:
            # A deliberate, already-explanatory error (e.g. protocol=SOCKET with
            # no available socket)
            raise
        except Exception as e:
            if self.writer:
                self.writer.close()
                # Best-effort close during error cleanup; the original failure is
                # re-raised below, so any wait_closed error is intentionally ignored.
                try:
                    await self.writer.wait_closed()
                except:  # nosec B110
                    pass
            self.reader = None  # type: ignore[assignment]
            self.writer = None  # type: ignore[assignment]
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
            raise _decode_error_packet(handshake_packet).toError(self.exception_factory)

        self.context = self._parse_handshake(handshake_packet, self.host_address)

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
        self.auth_plugin = NativePasswordPlugin(self.configuration.password, self.context.auth_data)  # type: ignore[arg-type]

        # Create and send handshake response
        message = HandshakeResponse(self.configuration, self.context)
        await self.write_payload(message.payload(self.context, self._payload_writer), message.type(), False)

        # Handle authentication (may involve multiple rounds)
        auth_result = await self.read_payload()
        await self._handle_authentication(auth_result)

        self.connected = True

    async def _ensure_default(self) -> None:
        """Ensure autocommit and charset are correctly set"""
        sql_commands: List[str] = []
        if ((self.context.server_status & constants.STATUS.AUTOCOMMIT) > 0) != self.configuration.autocommit:
            sql_commands.append('autocommit = ' + str(int(self.configuration.autocommit)))
        if (self.context.charset != 'utf8mb4'):
            sql_commands.append('NAMES utf8mb4')
            self.context.charset = 'utf8mb4'

        if len(sql_commands) > 0:
            sql_command = 'SET ' + ', '.join(sql_commands)
            query_packet = QueryPacket.from_sql(sql_command)
            await self.execute(query_packet, self.configuration)


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
        await self.write_payload(message.payload(self.context, self._payload_writer), message.type(), False)

        # Get the transport and protocol from the writer
        transport = self.writer.transport
        protocol = transport.get_protocol()
        try:
            # Import SSL utility
            from .ssl.ssl_utility import SSLUtility

            # Prepare SSL context with optional fingerprint validation
            ssl_context, self.cert_fingerprint_validator = SSLUtility.prepare_ssl_context(
                self.configuration,
                self.context,
                self.is_local_connection()
            )

            # Get the event loop
            loop = asyncio.get_event_loop()

            # Determine server hostname for SSL verification
            server_hostname = None
            if self.configuration.ssl_verify_cert and not self.cert_fingerprint_validator:
                server_hostname = self.host_address.host

            # Perform the in-band TLS upgrade.
            #
            # Python 3.11+ exposes StreamWriter.start_tls(), which does the
            # upgrade and re-syncs the streams for us (it drains, then calls
            # protocol._replace_transport(), which retargets the transport and
            # sets _over_ssl). On version before that we call loop.start_tls() and replicate
            # that fixup by hand on the internal attributes.
            if hasattr(self.writer, "start_tls"):  # Python 3.11+
                await self.writer.start_tls(
                    ssl_context,
                    server_hostname=server_hostname,
                )
            else:  # Python 3.10 fallback
                new_transport = await loop.start_tls(
                    transport,
                    protocol,
                    ssl_context,
                    server_side=False,
                    server_hostname=server_hostname,
                )
                self.writer._transport = new_transport     # type: ignore[attr-defined]
                protocol._transport = new_transport         # type: ignore[attr-defined]
                protocol._over_ssl = True                   # type: ignore[attr-defined]

            # Capture fingerprint if using fingerprint validation. The writer
            # now targets the SSL transport, so read the ssl_object off it.
            if self.cert_fingerprint_validator:
                ssl_socket = self.writer.get_extra_info('ssl_object')
                if ssl_socket:
                    self.cert_fingerprint_validator.capture_fingerprint(ssl_socket)

            # Update the stream sequence for the next packet
            self.sequence[0] = 1

        except ssl.SSLError as e:
            # SSL-specific error - close transport immediately to avoid cleanup issues
            # Best-effort transport close; the SSL error is re-raised below, so any
            # close failure is intentionally ignored.
            try:
                transport.close()
            except:  # nosec B110
                pass
            raise OperationalError(f"SSL handshake failed: {e}")
        except Exception as e:
            raise OperationalError(f"Failed to upgrade socket to SSL: {e}")


    async def change_user(self, user: str | None, password: str | None, database: str | None) -> None:
        """Change current user and database"""
        old_conf = self.configuration
        try:
            new_conf = copy.copy(self.configuration)
            new_conf.user = user if user is not None else self.configuration.user
            new_conf.password = password if password is not None else self.configuration.password
            new_conf.database = database if database is not None else self.context.database
            self.configuration = new_conf

            message = ChangeUserPacket(new_conf.user or '', new_conf.password, new_conf.database)
            # Disarm charset enforcement during re-authentication; _ensure_default re-arms it.
            self.context.charset = ''
            await self.write_payload(message.payload(self.context, self._payload_writer), message.type(), True)

            # Read initial authentication result
            auth_result = await self.read_payload()
            await self._handle_authentication(auth_result)
            await self._ensure_default()

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
            ok_packet = _decode_ok_packet(auth_result, self.context)
            # Validate SSL fingerprint if needed
            self.validate_ssl_fingerprint(ok_packet)
        elif packet_type == self.ERROR_PACKET:
            # Error packet - authentication failed
            raise _decode_error_packet(auth_result, self.context).toError(self.exception_factory)
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
            # Reject unsafe plugins before any credential is transmitted
            self.check_auth_switch_allowed(plugin_name, plugin_factory, plugin)
            response: memoryview = await plugin.processAsync(self.read_payload, self.write_payload, self.context)
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

    async def execute(self, message: ClientMessage, config: Configuration, buffered: bool = True, prepare_stmt_packet: PrepareStmtPacket | None = None) -> List[Completion]:
        """Execute command and return list of completion results"""
        async with self.lock:
            if self.closed:
                raise OperationalError("Invalid connection or not connected")

            # Drain any active streaming result before executing new command
            if self._active_streaming_result is not None:
                with contextlib.suppress(Exception):
                    await self._active_streaming_result.fetch_remaining()
                self._active_streaming_result = None

            try:
                await self.write_payload(message.payload(self.context, self._payload_writer))
                self.reset_buffer()
                return await self._read_result(message.is_binary(), config, buffered, prepare_stmt_packet, message.get_sql())
            except DatabaseError as e:
                if isinstance(e, CharsetMismatchError):
                    await self._cleanup_connection()
                    self.closed = True
                raise e
            except Exception as e:
                raise OperationalError(f"Execution failed: {e}")


    async def execute_stmt(self, sql: str, messages: List[ClientMessage], config: Configuration, buffered: bool = True, stmt_cache: Any = None) -> List[List[Completion]]:
        """Execute SQL with prepared statements (with caching), handles prepare if needed

        *stmt_cache* lets a caller (a cursor) supply its own prepared-statement
        cache instead of the shared connection-level one. This is used for
        per-cursor single-statement reuse when the connection cache is disabled.
        """
        async with self.lock:
            if self.closed:
                raise OperationalError("Invalid connection or not connected")

            cache = stmt_cache if stmt_cache is not None else self.prepared_statement_cache

            try:
                key = (self.context.database, sql)

                # Check cache first
                cached_stmt = cache.get(key) if cache is not None else None
                if cached_stmt and cached_stmt.acquire():
                    with cached_stmt:
                        all_completions: List[List[Completion]] = []
                        for message in messages:
                            message.statement_id = cached_stmt.statement_id  # type: ignore[attr-defined]
                            await self.write_payload(message.payload(self.context, self._payload_writer), message.type(), True)
                            self.reset_buffer()
                            completions = await self._read_result(message.is_binary(), config, buffered, cached_stmt, sql)
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
                        await self.write_payload(prepare_message.payload(self.context, self._payload_writer), prepare_message.type(), True)

                        for message in messages:
                            await self.write_payload(message.payload(self.context, self._payload_writer), message.type(), True)
                        self.reset_buffer()

                        try:
                            prepareResult = await self._parse_prepare_response(await self.read_payload(), sql, cache)
                        except DatabaseError as e:
                            first_error = e

                        # Read all execute results (even if prepare failed)
                        for message in messages:
                            try:
                                completions = await self._read_result(message.is_binary(), config, buffered, prepareResult, sql)
                                all_completions.append(completions)
                            except DatabaseError as e:
                                if not first_error:
                                    first_error = e
                    else:
                        # Non-pipeline mode: read prepare response before writing execute messages
                        await self.write_payload(prepare_message.payload(self.context, self._payload_writer), prepare_message.type(), True)
                        self.reset_buffer()

                        prepareResult = await self._parse_prepare_response(await self.read_payload(), sql, cache)

                        # Now write and read execute messages
                        for message in messages:
                            message.statement_id = prepareResult.statement_id  # type: ignore[attr-defined]
                            await self.write_payload(message.payload(self.context, self._payload_writer), message.type(), True)
                            self.reset_buffer()
                            try:
                                completions = await self._read_result(message.is_binary(), config, buffered, prepareResult, sql)
                                all_completions.append(completions)
                            except DatabaseError as e:
                                if not first_error:
                                    first_error = e
                finally:
                    # Cache and close prepared statement
                    if prepareResult:
                        if cache is not None:
                            cache[key] = prepareResult
                        prepareResult.close()

                if first_error:
                    raise first_error
                return all_completions

            except DatabaseError as e:
                raise e
            except Exception as e:
                raise OperationalError(f"Execution failed: {e}")



    async def _read_result(self, is_binary: bool, config: Configuration, buffered: bool = True, prepare_stmt_packet: PrepareStmtPacket | None = None, sql: str | None = None) -> List[Completion]:
        results : List[Completion] = []
        packets : list[tuple[int, int]] | None = None
        # Cache frequently accessed attributes as locals
        context : Context = self.context
        read_payload = self.read_payload

        while True:
            # Use packets from previous resultset if available
            if packets:
                packet = self._recv_buf_mv[packets[0][0]:packets[0][1]]
                packets = packets[1:] if len(packets) > 1 else None
            else:
                packet = await read_payload()

            packet_type = packet[0]
            if packet_type == self.OK_PACKET:
                results.append(_decode_ok_packet(packet, context))
                if (context.server_status & _MORE_RESULTS_EXIST) == 0:
                    break
                continue
            elif packet_type == self.ERROR_PACKET:
                raise _decode_error_packet(packet, context).toError(self.exception_factory)
            elif packet_type == self.EOF_PACKET:
                # EOF packet at top level (e.g. COM_DEBUG response)
                eof_completion = _decode_eof_packet(packet, context)
                results.append(eof_completion)
                if (context.server_status & _MORE_RESULTS_EXIST) == 0:
                    break
                continue
            elif packet_type == self.LOCAL_INFILE_PACKET:
                # LOAD DATA LOCAL INFILE request from server
                infile_completion, packets = await self._handle_local_infile(packet, sql, packets)
                results.append(infile_completion)
                if (context.server_status & _MORE_RESULTS_EXIST) == 0:
                    break
                continue

            """Parse result set with column definitions and row data"""
            # Parse column count from first packet
            parser = PayloadReader(packet)
            column_count = parser.read_length_encoded_int()
            if not (column_count is not None):
                raise AssertionError
            self._check_column_count(column_count)

            # Cache EOF deprecated flag once
            eof_deprecated = context.isEofDeprecated()

            # Read column definitions
            if context.has_capability(constants.CAPABILITY.CACHE_METDATA) and parser.read_byte() == 0:
                # skip metadata - use cached ColumnsDefinition
                columns: ColumnsDefinition = prepare_stmt_packet.columns  # type: ignore[union-attr, assignment]
            else:
                col_idx = 0
                if not packets:
                    packets = await read_payload(column_count)

                # Decode columns inside collection loop to avoid buffer
                # invalidation when read_payload is called multiple times
                columns = ColumnsDefinition(column_count)
                while col_idx < column_count:
                    if col_idx >= len(packets):
                        packets.extend(await read_payload(column_count - col_idx))
                    start, end = packets[col_idx]
                    columns.decode_column(col_idx, self._recv_buf_mv[start:end], context)
                    col_idx += 1

                packets = packets[column_count:] if len(packets) > column_count else None

                if prepare_stmt_packet is not None:
                    prepare_stmt_packet.columns = columns

            # Read EOF packet after column definitions (if not deprecated)
            if not eof_deprecated:
                if packets:
                    packets = packets[1:] if len(packets) > 1 else None
                else:
                    await read_payload()  # Skip EOF packet

            # Select appropriate row parser based on protocol
            row_parser = self._parse_binary_row_data if is_binary else self._parse_text_row_data

            # If unbuffered, create streaming result
            if not buffered:
                streaming_result = AsyncStreamingResult(read_payload,
                    context,
                    columns,
                    column_count,
                    config,
                    row_parser
                )

                # Register streaming result with client for tracking
                self._active_streaming_result = streaming_result

                # Create completion with streaming result
                streaming_completion: OkPacket = OkPacket(0,0,0,0,b'')
                streaming_completion.result_set = streaming_result
                results.append(streaming_completion)
                return results

            # Read rows
            rows: List[tuple[Any, ...]] = []

            # Pre-compute EOF/OK length threshold
            eof_length_threshold = 16777215 if eof_deprecated else 8

            packets = None
            while True:
                packets = packets if packets else await read_payload(-1)

                # Loop through the batch of packets
                finish_result = False
                packet_idx = 0
                for packet_idx, p in enumerate(packets):
                    row_packet = self._recv_buf_mv[p[0]:p[1]]
                    packet_first_byte = row_packet[0]

                    # Check for EOF/OK packet terminator
                    if packet_first_byte == 0xFE and len(row_packet) < eof_length_threshold:
                        result_completion: OkPacket | EofPacket
                        if eof_deprecated:
                            result_completion = _decode_ok_packet(row_packet, context)
                        else:
                            result_completion = _decode_eof_packet(row_packet, context)

                        if config and config.converter:
                            rows = self._apply_converters_to_rows(rows, columns, config)

                        result_completion.result_set = AsyncCompleteResult(
                            columns,
                            column_count,
                            config,
                            rows
                        )
                        results.append(result_completion)
                        finish_result = True

                        # Save any remaining packets for next result set
                        if packet_idx + 1 < len(packets):
                            packets = packets[packet_idx + 1:]
                        else:
                            packets = None
                        break

                    # Check for Error packet
                    elif packet_first_byte == self.ERROR_PACKET:
                        raise _decode_error_packet(row_packet, context).toError(self.exception_factory)

                    # Regular data row
                    rows.append(row_parser(row_packet, columns, config, column_count))

                if finish_result:
                    break

            if (context.server_status & _MORE_RESULTS_EXIST) == 0:
                break
        return results

    async def read_next_result(self, is_binary: bool, config: Configuration,
                               prepare_stmt_packet: PrepareStmtPacket | None = None,
                               sql: str | None = None) -> Completion | None:
        """Read exactly one further result set from the wire."""
        async with self.lock:
            if self.closed:
                raise OperationalError("Invalid connection or not connected")

            context = self.context
            read_payload = self.read_payload
            try:
                packet = await read_payload()
                packet_type = packet[0]

                if packet_type == self.OK_PACKET:
                    return _decode_ok_packet(packet, context)
                elif packet_type == self.ERROR_PACKET:
                    raise _decode_error_packet(packet, context).toError(self.exception_factory)
                elif packet_type == self.EOF_PACKET:
                    return _decode_eof_packet(packet, context)
                elif packet_type == self.LOCAL_INFILE_PACKET:
                    completion, _packets = await self._handle_local_infile(packet, sql, None)
                    return completion

                parser = PayloadReader(packet)
                column_count = parser.read_length_encoded_int()
                if not (column_count is not None):
                    raise AssertionError
                self._check_column_count(column_count)
                eof_deprecated = context.isEofDeprecated()

                if context.has_capability(constants.CAPABILITY.CACHE_METDATA) and parser.read_byte() == 0:
                    if prepare_stmt_packet is None or prepare_stmt_packet.columns is None:
                        raise OperationalError(
                            "Server omitted result-set metadata for a subsequent "
                            "result set and no cached metadata is available")
                    columns: ColumnsDefinition = prepare_stmt_packet.columns
                else:
                    packets = await read_payload(column_count)
                    columns = ColumnsDefinition(column_count)
                    col_idx = 0
                    while col_idx < column_count:
                        if col_idx >= len(packets):
                            packets.extend(await read_payload(column_count - col_idx))
                        start, end = packets[col_idx]
                        columns.decode_column(col_idx, self._recv_buf_mv[start:end], context)
                        col_idx += 1
                    if prepare_stmt_packet is not None:
                        prepare_stmt_packet.columns = columns

                if not eof_deprecated:
                    await read_payload()

                row_parser = self._parse_binary_row_data if is_binary else self._parse_text_row_data

                streaming_result = AsyncStreamingResult(read_payload,
                    context, columns, column_count, config, row_parser)
                self._active_streaming_result = streaming_result
                streaming_completion: OkPacket = OkPacket(0, 0, 0, 0, b'')
                streaming_completion.result_set = streaming_result
                return streaming_completion
            except DatabaseError as e:
                raise e
            except Exception as e:
                raise OperationalError(f"Reading next result set failed: {e}")

    async def drain_streaming_result(self, result: AsyncResult | None, is_binary: bool, first_only: bool) -> None:
        """Drain a streaming result when a cursor is closed mid-stream."""
        if (result is self._active_streaming_result
                and isinstance(result, AsyncStreamingResult)):
            with contextlib.suppress(Exception):
                await result.fetch_remaining()
                if first_only:
                    return
                while not is_binary and (self.context.server_status & _MORE_RESULTS_EXIST) != 0:
                    completion = await self.read_next_result(False, self.configuration)
                    next_result = completion.result_set if (completion is not None and completion.has_result_set()) else None
                    if not isinstance(next_result, AsyncStreamingResult):
                        break
                    await next_result.fetch_remaining()
            self._active_streaming_result = None

    async def _handle_local_infile(self, packet: memoryview, sql: str | None, remaining_packets: list[tuple[int, int]] | None) -> tuple[OkPacket, list[tuple[int, int]] | None]:
        """Handle LOAD DATA LOCAL INFILE request from server (async)

        Returns:
            tuple: (Completion, remaining_packets)
        """

        # Read filename from packet (skip 0xFB header)
        parser = PayloadReader(packet)
        parser.skip(1)  # Skip 0xFB
        filename = parser.read_null_terminated_string()


        # Check if local_infile is enabled
        if self.configuration.local_infile is False:
            # Send empty packet to keep connection state OK
            await self.write_payload(bytearray(4), reset_sequence=False)
            raise ProgrammingError(
                "LOAD DATA LOCAL INFILE is disabled. Set local_infile=True in connection parameters to enable it."
            )

        # Validate filename matches the LOAD ... LOCAL INFILE in the client's own
        # statement. Fail closed: a request with no SQL context to validate against
        # (e.g. the prepared-statement path) must be rejected, never trusted — a
        # malicious/MitM server could otherwise read an arbitrary client file.
        if not sql or not self._validate_local_filename(sql, filename):
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
                    chunk = f.read(16384)
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
        if remaining_packets:
            response = self._recv_buf_mv[remaining_packets[0][0]:remaining_packets[0][1]]
            remaining_packets = remaining_packets[1:] if len(remaining_packets) > 1 else None
        else:
            response = await self.read_payload()

        if response[0] == 0x00:  # OK packet
            ok = _decode_ok_packet(response, self.context)
            if error:
                raise error
            return ok, remaining_packets

        # Raise error after reading response if file operation failed
        if error:
            raise error

        # Check if server returned an error
        if response[0] == 0xFF:  # ERR packet
            raise _decode_error_packet(response, self.context).toError(self.exception_factory)

        raise OperationalError(f"Unexpected packet type during LOCAL INFILE: 0x{response[0]:02x}")

    def _validate_local_filename(self, sql: str, filename: str) -> bool:
        """Validate that filename matches LOAD DATA LOCAL INFILE query"""
        import re

        # Escape backslashes in filename for regex
        escaped_filename = re.escape(filename.replace("\\", "\\\\"))

        # Pattern to match LOAD DATA LOCAL INFILE with the specific filename.
        # The SQL keywords are matched case-insensitively, but the filename is
        # wrapped in a (?-i:...) group so it is matched case-SENSITIVELY
        pattern = (
            r"^((\s[--]|#).*(\r\n|\r|\n)|\s*/\*([^*]|\*[^/])*\*/|.)*"
            r"\s*LOAD\s+(DATA|XML)\s+((LOW_PRIORITY|CONCURRENT)\s+)?"
            r"LOCAL\s+INFILE\s+['\"](?-i:" + escaped_filename + r")['\"]"
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
        async with self.lock:
            if self.closed:
                return

            if self.prepared_statement_cache is not None:
                self.prepared_statement_cache.clear()

            # Send COM_QUIT packet to gracefully close the connection
            if self.connected and self.writer:
                # Ignore errors when sending quit - connection may already be broken
                with contextlib.suppress(Exception):
                    message = QuitPacket()
                    await self.write_payload(message.payload(self.context, self._payload_writer), message.type(), True)

                    await self.writer.drain()
            self.closed = True
            self.connected = False
            await self._cleanup_connection()

    # =========================================================================
    # SSL/TLS Information
    # =========================================================================

    def get_ssl_cipher(self) -> tuple[str, str, int] | None:
        """Get the negotiated TLS cipher as (name, protocol_version, secret_bits).
        """
        if self.writer:
            ssl_object = self.writer.get_extra_info('ssl_object')
            if ssl_object is not None:
                try:
                    return cast(ssl.SSLObject, ssl_object).cipher()
                except Exception:
                    return None
        return None

    def get_ssl_version(self) -> str | None:
        """Get current TLS/SSL version string"""
        if self.writer:
            ssl_object = self.writer.get_extra_info('ssl_object')
            if ssl_object is not None:
                try:
                    return cast(ssl.SSLObject, ssl_object).version()
                except Exception:
                    return None
        return None

    def get_peer_certificate(self) -> dict[str, Any] | None:
        """Get the peer's certificate as the decoded dict from ssl.getpeercert()
        , or None when no peer cert is available."""
        if self.writer:
            ssl_object = self.writer.get_extra_info('ssl_object')
            if ssl_object is not None:
                try:
                    return cast(ssl.SSLObject, ssl_object).getpeercert()
                except Exception:
                    return None
        return None

    def _abort_connection(self) -> None:
        """Close the connection without sending COM_QUIT.

        StreamWriter.close() is the synchronous part of the shutdown, so no
        await is needed: the transport is closed by the event loop and
        wait_closed() is skipped.
        """
        self.closed = True
        self.connected = False
        if hasattr(self, 'writer') and self.writer:
            with contextlib.suppress(Exception):
                self.writer.close()
            self.writer = None  # type: ignore[assignment]
        self.reader = None  # type: ignore[assignment]

    async def _cleanup_connection(self) -> None:
        """Cleanup socket and stream resources asynchronously"""
        if hasattr(self, 'writer') and self.writer:
            try:
                self.writer.close()
                await asyncio.wait_for(self.writer.wait_closed(), timeout=1.0)
            except (asyncio.TimeoutError, ssl.SSLError, Exception):
                pass
            self.writer = None  # type: ignore[assignment]
        if hasattr(self, 'reader'):
            self.reader = None  # type: ignore[assignment]
        # Read buffer cleanup handled by garbage collection

    # =========================================================================
    # Prepared Statements
    # =========================================================================


    async def _parse_prepare_response(self, packet: memoryview, sql: str, cache: Any = None) -> PrepareStmtPacket:
        """Parse COM_STMT_PREPARE response packet asynchronously

        *cache* is the prepared-statement cache the result will be stored in
        (per-cursor or connection-level); a reference-counted
        CachedPrepareStmtPacket is produced when a cache is in play, a plain
        PrepareStmtPacket otherwise.
        """
        if len(packet) == 0:
            raise OperationalError("Empty prepare response packet")

        packet_type = packet[0]

        effective_cache = cache if cache is not None else self.prepared_statement_cache

        if packet_type == self.OK_PACKET:
            if effective_cache is not None:
                prepare_stmt_packet = CachedPrepareStmtPacket.decode(packet, self.context, sql, self._close_prepared_statement)
            else:
                prepare_stmt_packet = PrepareStmtPacket.decode(packet, self.context, sql, self._close_prepared_statement)  # type: ignore[assignment]
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
                col_count = prepare_stmt_packet.column_count
                self._check_column_count(col_count)
                columns = ColumnsDefinition(col_count)
                for i in range(col_count):
                    columns.decode_column(i, await self.read_payload(), self.context)
                prepare_stmt_packet.columns = columns

                # Read EOF packet after columns (if not deprecated)
                if not self.context.isEofDeprecated():
                    await self.read_payload()  # Skip EOF packet

            return prepare_stmt_packet
        elif packet_type == self.ERROR_PACKET:
            # Error packet
            raise _decode_error_packet(packet, self.context).toError(self.exception_factory)
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
        """Async implementation of close prepared statement.

        Invoked (via a scheduled task) from PrepareStmtPacket.close(), which marks
        the statement closed *before* calling the callback — so we must not bail
        out on stmt.is_closed() (always True here), which would skip COM_STMT_CLOSE
        and leak the statement server-side until disconnect.

        The write is serialized under the connection lock so the COM_STMT_CLOSE is
        never interleaved mid-sequence with another in-flight command.
        """
        # Ignore errors when closing
        with contextlib.suppress(Exception):
            async with self.lock:
                if not self.closed:
                    from ..message.client.stmt_close_packet import StmtClosePacket
                    message = StmtClosePacket(stmt.statement_id)
                    await self.write_payload(message.payload(self.context, self._payload_writer), message.type(), True)
