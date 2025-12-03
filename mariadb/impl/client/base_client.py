# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Base Client abstract class for MariaDB connections

Contains all common logic shared between AsyncClient and SyncClient.
"""

import decimal
import datetime
import threading
import struct
import ipaddress
import uuid
from abc import ABC, abstractmethod
from typing import List, Optional, Callable

# Pre-compiled struct formats for row parsing performance
_STRUCT_H = struct.Struct('<H')  # unsigned short (2 bytes)
_STRUCT_I = struct.Struct('<I')  # unsigned int (4 bytes)
_STRUCT_Q = struct.Struct('<Q')  # unsigned long long (8 bytes)
_STRUCT_b = struct.Struct('<b')  # signed byte
_STRUCT_h = struct.Struct('<h')  # signed short
_STRUCT_i = struct.Struct('<i')  # signed int
_STRUCT_q = struct.Struct('<q')  # signed long long
_STRUCT_f = struct.Struct('<f')  # float
_STRUCT_d = struct.Struct('<d')  # double
_STRUCT_HBB = struct.Struct('<HBB')  # year, month, day for date
_STRUCT_HBBBBB = struct.Struct('<HBBBBB')  # year, month, day, hour, min, sec for datetime (no micro)
_STRUCT_HBBBBBI = struct.Struct('<HBBBBBI')  # year, month, day, hour, min, sec, microsec for datetime
_STRUCT_BIBBB = struct.Struct('<BIBBB')  # negative, days, hour, min, sec for time (no micro)
_STRUCT_BIBBBI = struct.Struct('<BIBBBI')  # negative, days, hour, min, sec, microsec for time
# Struct formats for text protocol date/datetime parsing (YYYY-MM-DD format)
_STRUCT_DATE_TEXT = struct.Struct('4s1s2s1s2s')  # year(4), dash, month(2), dash, day(2)
_STRUCT_DATETIME_TEXT = struct.Struct('4s1s2s1s2s1s2s1s2s1s2s')  # YYYY-MM-DD HH:MM:SS

# No longer need PacketBuffer import

from .context import Context
from ..message.payload_reader import PayloadReader
from ..configuration import Configuration
from ..host_address import HostAddress
from ..message.client_message import ClientMessage
from ..message.server.prepare_stmt_packet import PrepareStmtPacket
from ..completion import Completion
from ..message.server.column_definition_packet import ColumnDefinitionPacket
from .exception_factory import ExceptionFactory
from ...exceptions import OperationalError
from mariadb_shared.constants import FIELD_TYPE, FIELD_FLAG
from mariadb_shared import constants
from ..message.server.ok_packet import OkPacket
from cachetools import LRUCache

# Write stream constants
HEADER_SIZE = 4
MAX_PACKET_SIZE = 0xFFFFFF

class BaseClient(ABC):
    """
    Abstract base client for MariaDB connections
    
    Contains all common logic shared between async and sync implementations.    
    """
    
    # =========================================================================
    # Constants
    # =========================================================================
    
    # Packet type constants
    OK_PACKET = 0x00
    ERROR_PACKET = 0xFF
    EOF_PACKET = 0xFE
    AUTH_SWITCH_REQUEST_PACKET = 0xFE
    LOCAL_INFILE_PACKET = 0xFB
    
    # MariaDB replication hack prefix
    MARIADB_RPL_HACK_PREFIX = "5.5.5-"
    
    # Session tracking constants
    SESSION_TRACK_SYSTEM_VARIABLES = 0
    SESSION_TRACK_SCHEMA = 1
    SESSION_TRACK_STATE_CHANGE = 2
    SESSION_TRACK_GTIDS = 3
    SESSION_TRACK_TRANSACTION_CHARACTERISTICS = 4
    SESSION_TRACK_TRANSACTION_STATE = 5
    
    def __init__(self, configuration: Configuration) -> None:
        """
        Initialize base client
        
        Args:
            configuration: Connection configuration
            host_address: Host address to connect to
        """
        self.configuration: Configuration = configuration
        self.host_address: Optional[HostAddress] = None
        self.sequence = [0]
        self.context: Optional[Context] = None
        self.exception_factory = ExceptionFactory()
        self.closed = False
        self.socket_timeout = configuration.socket_timeout
        self.connect_timeout = configuration.connect_timeout
        self.lock = threading.Lock()
        self.cert_fingerprint_validator: Optional['SSLFingerprintValidator'] = None
        self.auth_plugin: Optional['AuthenticationPlugin'] = None

        # Connection state
        self.connected = False
        self.read_only = configuration.read_only
        
        # Prepared statement cache (LRU cache with eviction callback, configurable)
        cache_size = configuration.prep_stmt_cache_size if configuration.cache_prep_stmts else 0
        if cache_size > 0:
            # Create LRU cache that calls evicted_from_cache on eviction
            class PreparedStatementLRUCache(LRUCache):
                def popitem(self):
                    """Called when LRU evicts an item"""
                    key, value = super().popitem()
                    # Notify the statement it's been evicted
                    if hasattr(value, 'evicted_from_cache'):
                        value.evicted_from_cache()
                    return key, value
            
            self.prepared_statement_cache = PreparedStatementLRUCache(maxsize=cache_size)
        else:
            self.prepared_statement_cache = {}
    
    # =========================================================================
    # Write Stream Methods
    # =========================================================================
    
    def reset_sequence(self) -> None:
        """Reset packet sequence number"""
        self.sequence[0] = 0
    
    @abstractmethod
    def write_payload(self, payload: bytearray, packet_type: str = "", reset_sequence: bool = True) -> None:
        """
        Write payload with MariaDB packet framing
        
        Args:
            payload: Payload bytearray to send (first 4 bytes reserved for header)
            packet_type: Packet type for logging (e.g., "COM_QUERY")
            reset_sequence: Whether to reset sequence number before sending
        """
        ...
    
    # =========================================================================
    # Abstract Methods
    # =========================================================================
    
    @abstractmethod
    def connect(self) -> None:
        """Establish connection to MariaDB server"""
        ...
    
    @abstractmethod
    def _create_socket(self) -> None:
        """Create and configure socket connection"""
        ...
    
    @abstractmethod
    def _perform_handshake(self) -> None:
        """Perform MySQL handshake protocol"""
        ...
    
    @abstractmethod
    def _handle_ssl_connection(self, client_capabilities: int) -> None:
        """Handle SSL connection setup"""
        ...
    
    @abstractmethod
    def _handle_authentication(self) -> None:
        """Handle authentication process using plugin system"""
        ...
    
    @abstractmethod
    def _handle_auth_switch(self) -> None:
        """Handle authentication switch """
        ...
   
    @abstractmethod
    def execute(self, message: ClientMessage, config: 'Configuration', buffered: bool = True, prepare_stmt_packet: Optional['PrepareStmtPacket'] = None) -> List['Completion']:
        """Send client message and read result"""
        ...

    @abstractmethod
    def execute_stmt(self, sql: str, messages: 'List[ClientMessage]', config: 'Configuration' = None, buffered: bool = True) -> 'List[Completion] | List[List[Completion]]':
        """Execute SQL with prepared statements (with caching), handles prepare if needed. Returns List[Completion] for single message, List[List[Completion]] for multiple messages."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Close client connection"""
        ...
    
    @abstractmethod
    def _cleanup_connection(self) -> None:
        """Clean up connection resources"""
        ...
    
    @abstractmethod
    def get_ssl_cipher(self) -> Optional[tuple]:
        """
        Get current SSL cipher information
        
        Returns:
            Cipher tuple (name, version, bits) or None if not using SSL
        """
        ...
    
    @abstractmethod
    def get_ssl_version(self) -> Optional[str]:
        """
        Get current TLS/SSL version
        
        Returns:
            TLS version string (e.g., 'TLSv1.3') or None if not using SSL
        """
        ...
    
    @abstractmethod
    def get_peer_certificate(self) -> Optional[dict]:
        """
        Get peer SSL certificate information
        
        Returns:
            Certificate dict or None if not using SSL
        """
        ...
    
    
    # =========================================================================
    # Connection Type Checks
    # =========================================================================
    
    def is_local_connection(self) -> bool:
        """
        Determine if the current connection is to localhost.
        
        This method checks if the connection is considered "local" based on:
        - Unix domain sockets are always local
        - TCP connections to localhost addresses (127.0.0.1, ::1)
        
        On Windows, "localhost" hostname is also considered local for TCP connections
        to avoid false "self-signed certificate" errors with default configurations.
        
        Returns:
            True if connection is local, False otherwise
        """
        import platform
        
        # Unix domain sockets are always local
        if self.host_address and self.configuration.unix_socket:
            return True
        
        # If no host address, not local
        if not self.host_address or not self.host_address.host:
            return False
        
        hostname = self.host_address.host
        
        # Define local host names based on platform
        local_host_names = ["127.0.0.1", "::1"]
        
        # On Windows, also consider "localhost" as local for TCP connections
        if platform.system() == "Windows":
            local_host_names.append("localhost")
        
        # Check if hostname matches any local host name
        return hostname in local_host_names
    

    def validate_ssl_fingerprint(self, ok_packet: OkPacket) -> None:
        """
        Validate SSL certificate fingerprint using server-provided hash
        
        This implements MariaDB's self-signed certificate validation:
        - Server sends SHA256(hash(password) + seed + cert_fingerprint) in OK packet info
        - Client verifies by calculating the same hash and comparing
        
        Args:
            ok_packet: OK packet from server containing validation hash in info field
            
        Raises:
            OperationalError: If fingerprint validation fails
        """
        # Only validate if we have a fingerprint (self-signed cert scenario)
        if not self.cert_fingerprint_validator or not self.cert_fingerprint_validator.get_fingerprint():
            return
        
        # Skip validation for local and Unix domain sockets (MitM-proof by design)
        if self.is_local_connection() or self.configuration.unix_socket:
            return
        
        # Check if auth plugin is MitM-proof and has password
        if not self.auth_plugin:
            raise OperationalError(
                "Self signed certificates. Either set ssl_verify_cert=True, use password with a "
                "MitM-Proof authentication plugin or provide server certificate to client"
            )
        
        if not self.auth_plugin.is_mitm_proof():
            raise OperationalError(
                f"Cannot use authentication plugin {type(self.auth_plugin).__name__} with self signed certificates. "
                "Either set ssl_verify_cert=True, use password with a MitM-Proof authentication plugin "
                "or provide server certificate to client"
            )
        
        if self.configuration.password == None or self.configuration.password == "":
            raise OperationalError(
                "Self signed certificates require a password. Either set ssl_verify_cert=True, "
                "use password with a MitM-Proof authentication plugin or provide server certificate to client"
            )
        
        # Get auth plugin hash
        plugin_hash = self.auth_plugin.hash(self.configuration)
        if not plugin_hash:
            raise OperationalError(
                "Authentication plugin did not provide hash for fingerprint validation"
            )
        
        # Validate fingerprint using server's validation hash from OK packet info
        if not self.cert_fingerprint_validator.validate_fingerprint(
            plugin_hash,
            self.context.auth_data,
            ok_packet.info
        ):
            raise OperationalError(
                "Self signed certificates fingerprint validation failed. "
                "Either set ssl_verify_cert=True, use password with a MitM-Proof authentication plugin "
                "or provide server certificate to client"
            )

    # =========================================================================
    # Protocol Parsing
    # =========================================================================
    
    def _parse_handshake(self, packet: memoryview) -> Context:
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
            raise self.exception_factory.create_exception(
                "Invalid handshake packet: too short", 
                errno=2027, 
                sql_state='HY000'
            )
        
        parser = PayloadReader(packet)
        
        # Protocol version (1 byte)
        protocol_version = parser.read_byte()
        if protocol_version != 0x0a:
            raise OperationalError(f"Unexpected initial handshake protocol value [{protocol_version}]")
        
        # Server version (null-terminated string)
        server_version = parser.read_null_terminated_string()
        
        # Thread ID / Connection ID (4 bytes)
        thread_id = parser.read_uint32()
        
        # Auth plugin data part 1 - seed1 (8 bytes)
        seed1 = parser.read_bytes(8)
        
        # Skip filler (1 byte, should be 0x00)
        parser.read_byte()
        
        # Server capabilities first 2 bytes
        server_capabilities_2_first_bytes = parser.read_uint16()
        
        # Default collation (1 byte)
        default_collation = parser.read_byte()
        
        # Server status (2 bytes)
        server_status = parser.read_uint16()
        
        # Server capabilities upper 2 bytes
        server_capabilities_upper = 0
        if parser.remaining_bytes() >= 2:
            server_capabilities_upper = parser.read_uint16()
        
        server_capabilities_4_first_bytes = server_capabilities_2_first_bytes | (server_capabilities_upper << 16)
        
        # Salt length calculation
        salt_length = 0
        if (server_capabilities_4_first_bytes & constants.CAPABILITY.PLUGIN_AUTH) != 0:
            salt_length = max(12, parser.read_byte() - 9)
        else:
            # Skip 1 byte
            parser.read_byte()
        
        # Skip reserved bytes (6 bytes)
        if parser.remaining_bytes() >= 6:
            parser.skip(6)
        else:
            # Handle shorter packets gracefully
            parser.skip(parser.remaining_bytes())
        
        # MariaDB additional capabilities (4 bytes)
        # Filled only if MariaDB server 10.2+
        mariadb_additional_capacities = 0
        if parser.remaining_bytes() >= 4:
            mariadb_additional_capacities = parser.read_uint32()
        
        # Handle seed2 and combine with seed1
        seed2 = b''
        if (server_capabilities_4_first_bytes & constants.CAPABILITY.SECURE_CONNECTION) != 0:
            if salt_length > 0:
                # Read salt_length bytes for seed2
                available = min(salt_length, parser.remaining_bytes())
                seed2 = parser.read_bytes(available)
            else:
                # Read null-terminated seed2
                seed2 = parser.read_null_terminated_bytes()
            
            # Combine seed1 and seed2
            seed = bytes(seed1) + bytes(seed2)
        else:
            seed = bytes(seed1)
        
        # Skip null terminator if present
        if parser.has_remaining() and parser.get_byte() == 0x00:
            parser.read_byte()
        
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
            server_capabilities = (server_capabilities_4_first_bytes & 0xffffffff) | (mariadb_additional_capacities << 32)
            server_mariadb = True
        else:
            server_capabilities = server_capabilities_4_first_bytes & 0xffffffff
        
        # Auth plugin type (null-terminated string)
        auth_plugin_name = None
        if (server_capabilities_4_first_bytes & constants.CAPABILITY.PLUGIN_AUTH) != 0:
            if parser.has_remaining():
                auth_plugin_name = parser.read_null_terminated_string()
        
        # Create context with parsed information
        context = Context(
            server_version=server_version,
            connection_id=thread_id,
            protocol_version=protocol_version,
            server_capabilities=server_capabilities,
            server_status=server_status,
            auth_plugin=auth_plugin_name,
            auth_data=seed,
            is_mariadb=server_mariadb
        )
        return context
    
    def _calculate_client_capabilities(self) -> int:
        """
        Calculate client capabilities based on configuration
        
        Returns:
            Client capabilities flags
        """
        capabilities = (
            constants.CAPABILITY.IGNORE_SPACE |
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
            constants.CAPABILITY.CACHE_METDATA |
            constants.CAPABILITY.BULK_UNIT_RESULTS
        )
        
        # Add LOCAL_FILES capability only if local_infile is explicitly enabled
        if not (self.configuration.local_infile == False):
            capabilities |= constants.CAPABILITY.LOCAL_FILES
        
        # Add database capability if database specified and server supports it
        if self.configuration.database:
            capabilities |= constants.CAPABILITY.CONNECT_WITH_DB
        
        # Add SSL capability if SSL enabled and server supports it
        if self.configuration.ssl:
            capabilities |= constants.CAPABILITY.SSL
        
        # Only use capabilities that the server supports
        return capabilities & self.context.server_capabilities
    
    # =========================================================================
    # Result Set Parsing
    # =========================================================================
        
    def _is_null_bitmap(self, index: int, null_bitmap: bytes) -> bool:
        """
        Check if column is NULL using binary result set NULL bitmap
        
        Args:
            index: Column index
            null_bitmap: NULL bitmap bytes
            
        Returns:
            True if column is NULL
        """
        # Formula from Node.js connector: (nullBitmap[~~((index + 2) / 8)] & (1 << (index + 2) % 8)) > 0
        byte_pos = (index + 2) // 8
        bit_pos = (index + 2) % 8
        
        if byte_pos >= len(null_bitmap):
            return False
        
        return (null_bitmap[byte_pos] & (1 << bit_pos)) > 0

    def get_host_address(self) -> HostAddress:
        """Get host address"""
        return self.host_address

    # =========================================================================
    # Authentication Helper Methods
    # =========================================================================
    
    def _handle_plugin_auth_continue(self, packet: bytearray) -> None:
        """
        Handle plugin authentication continuation
        
        Args:
            packet: Authentication continuation packet
        """
        # For now, treat as successful authentication
        # This would need more sophisticated handling for multi-round auth
        OkPacket.decode(packet, self.context)

    def _apply_converters_to_rows(self, rows: List[tuple], columns: List[ColumnDefinitionPacket], config: 'Configuration') -> List[tuple]:
        """
        Apply converters to all rows at once
        
        Args:
            rows: List of row tuples
            columns: Column definitions
            config: Configuration with converter settings
            
        Returns:
            List of converted row tuples
        """

        # Build list of column indices that need conversion
        converter_map = config.converter
        num_cols = len(columns)
        converter_indices = []
        converter_funcs = []
        
        for i in range(num_cols):
            col_type = columns[i].type
            if col_type in converter_map:
                converter_indices.append(i)
                converter_funcs.append(converter_map[col_type])
        
        # If no converters needed, return as-is
        if not converter_indices:
            return rows

        # Fast path: all columns need conversion
        num_converters = len(converter_indices)
        if num_converters == num_cols:
            converted_rows = []
            for row in rows:
                converted_row = []
                for i in range(num_cols):
                    try:
                        converted_row.append(converter_funcs[i](row[i]))
                    except Exception:
                        converted_row.append(row[i])
                converted_rows.append(tuple(converted_row))
            return converted_rows

        # Partial conversion: only some columns need it
        converted_rows = []
        for row in rows:
            row_list = list(row)
            for i in range(num_converters):
                idx = converter_indices[i]
                try:
                    row_list[idx] = converter_funcs[i](row_list[idx])
                except Exception:
                    pass
            converted_rows.append(tuple(row_list))

        return converted_rows

    # =========================================================================
    # Row Data Parsing Methods
    # =========================================================================

    def _parse_text_row_data(self, data: memoryview, columns: List[ColumnDefinitionPacket], config: 'Configuration') -> tuple:
        """Parse text protocol row data packet with inlined decoding"""
        num_cols = len(columns)
        row_values = [None] * num_cols
        pos = 0
        data_bytes = data.tobytes()  # Convert once for faster access
        
        for i in range(num_cols):
            column = columns[i]
            # Read length-encoded integer for field length
            length_byte = data[pos]
            if (length_byte < 0xFB):
                length = length_byte
                pos += 1
            elif (length_byte == 0xFB):
                pos += 1                
                continue
            elif length_byte == 0xFC:
                length = _STRUCT_H.unpack_from(data, pos + 1)[0]
                pos += 3
            elif length_byte == 0xFD:
                length = struct.unpack('<I', bytes(data[pos+ 1:pos+4]) + b'\x00')[0]
                pos += 4
            else:
                length = _STRUCT_Q.unpack_from(data, pos + 1)[0]
                pos += 9
            
            col_type = column.type
            if col_type in (FIELD_TYPE.TINY, FIELD_TYPE.SHORT, FIELD_TYPE.LONG, FIELD_TYPE.LONGLONG, FIELD_TYPE.INT24, FIELD_TYPE.YEAR):
                row_values[i] = int(data_bytes[pos:pos + length])
            elif col_type in (FIELD_TYPE.FLOAT, FIELD_TYPE.DOUBLE):
                row_values[i] = float(data_bytes[pos:pos + length].decode('ascii'))
            elif col_type in (FIELD_TYPE.DECIMAL, FIELD_TYPE.NEWDECIMAL):
                row_values[i] = decimal.Decimal(data_bytes[pos:pos + length].decode('ascii'))
            elif col_type in (FIELD_TYPE.DATE, FIELD_TYPE.NEWDATE):
                # Fast date parsing: YYYY-MM-DD using struct
                if length == 10:
                    try:
                        year_b, _, month_b, _, day_b = _STRUCT_DATE_TEXT.unpack_from(data_bytes, pos)
                        row_values[i] = datetime.date(int(year_b), int(month_b), int(day_b))
                    except (ValueError, struct.error):
                        row_values[i] = None
                else:
                    row_values[i] = None
            elif col_type == FIELD_TYPE.TIME:
                time_str = data_bytes[pos:pos + length].decode('ascii')
                negative = time_str[0] == '-'
                if negative:
                    time_str = time_str[1:]
                parts = time_str.split(':')
                if len(parts) == 3:
                    hours = int(parts[0])
                    minutes = int(parts[1])
                    sec_parts = parts[2].split('.')
                    seconds = int(sec_parts[0])
                    microseconds = int(sec_parts[1].ljust(6, '0')) if len(sec_parts) > 1 else 0
                    td = datetime.timedelta(hours=hours, minutes=minutes, seconds=seconds, microseconds=microseconds)
                    row_values[i] = -td if negative else td
                else:
                    row_values[i] = None
            elif col_type in (FIELD_TYPE.DATETIME, FIELD_TYPE.TIMESTAMP):
                # Fast datetime parsing: YYYY-MM-DD HH:MM:SS[.ffffff] using struct
                if length >= 19:
                    try:
                        year_b, _, month_b, _, day_b, _, hour_b, _, min_b, _, sec_b = _STRUCT_DATETIME_TEXT.unpack_from(data_bytes, pos)
                        # Check for microseconds
                        if length > 19 and data_bytes[pos+19] == 46:  # '.'
                            microseconds = int(data_bytes[pos+20:pos+length].ljust(6, b'0'))
                        else:
                            microseconds = 0
                        row_values[i] = datetime.datetime(
                            int(year_b), int(month_b), int(day_b),
                            int(hour_b), int(min_b), int(sec_b), microseconds
                        )
                    except (ValueError, struct.error):
                        row_values[i] = None
                else:
                    row_values[i] = None
            elif col_type == FIELD_TYPE.NULL:
                row_values[i] = None
            elif col_type == FIELD_TYPE.JSON:
                row_values[i] = data_bytes[pos:pos + length].decode('utf-8', errors='replace')
            else:
                # String types and others
                if column.special_format:
                    if column.ext_type_format == b'json':
                        row_values[i] = data_bytes[pos:pos + length].decode('utf-8', errors='replace')
                    elif column.ext_type_name == b'inet6' or column.ext_type_name == b'inet4':
                        row_values[i] = data_bytes[pos:pos + length].decode('ascii')
                        if config.native_object:
                            row_values[i] = ipaddress.ip_address(row_values[i])
                    elif column.ext_type_name == b'uuid':
                        row_values[i] = data_bytes[pos:pos + length].decode('ascii')
                        if config.native_object:
                            row_values[i] = uuid.UUID(row_values[i])
                elif column.character_set == 63:  # Binary
                    row_values[i] = data_bytes[pos:pos + length]
                else:
                    row_values[i] = data_bytes[pos:pos + length].decode('utf-8', errors='replace')
            
            pos += length
        
        return tuple(row_values)

    def _parse_binary_row_data(self, data: memoryview, columns: List[ColumnDefinitionPacket], config: 'Configuration') -> tuple:
        """Parse binary protocol row data packet with inlined decoding"""
        pos = 1  # Skip 0x00 header
        
        # Read NULL bitmap
        num_columns = len(columns)
        null_bitmap_length = (num_columns + 9) >> 3
        null_bitmap = bytes(data[pos:pos + null_bitmap_length])
        pos += null_bitmap_length
        
        # Parse column values with inlined decoding
        row_values = [None] * num_columns
        
        for i in range(num_columns):
            column = columns[i]
            byte_pos = (i + 2) >> 3
            bit_pos = (i + 2) & 7
            if byte_pos < len(null_bitmap) and (null_bitmap[byte_pos] & (1 << bit_pos)):
                row_values[i] = None
                continue
            
            # Decode based on field type
            field_type = column.type
            
            if field_type == FIELD_TYPE.TINY:
                if (column.flags & FIELD_FLAG.UNSIGNED) != 0:
                    row_values[i] = data[pos]
                else:
                    row_values[i] = _STRUCT_b.unpack_from(data, pos)[0]
                pos += 1
            elif field_type in (FIELD_TYPE.SHORT, FIELD_TYPE.YEAR):
                if (column.flags & FIELD_FLAG.UNSIGNED) != 0:
                    row_values[i] = _STRUCT_H.unpack_from(data, pos)[0]
                else:
                    row_values[i] = _STRUCT_h.unpack_from(data, pos)[0]
                pos += 2
            elif field_type in (FIELD_TYPE.LONG, FIELD_TYPE.INT24):
                if (column.flags & FIELD_FLAG.UNSIGNED) != 0:
                    row_values[i] = _STRUCT_I.unpack_from(data, pos)[0]
                else:
                    row_values[i] = _STRUCT_i.unpack_from(data, pos)[0]
                pos += 4
            elif field_type == FIELD_TYPE.LONGLONG:
                if (column.flags & FIELD_FLAG.UNSIGNED) != 0:
                    row_values[i] = _STRUCT_Q.unpack_from(data, pos)[0]
                else:
                    row_values[i] = _STRUCT_q.unpack_from(data, pos)[0]
                pos += 8
            elif field_type == FIELD_TYPE.FLOAT:
                row_values[i] = _STRUCT_f.unpack_from(data, pos)[0]
                pos += 4
            elif field_type == FIELD_TYPE.DOUBLE:
                row_values[i] = _STRUCT_d.unpack_from(data, pos)[0]
                pos += 8
            elif field_type in (FIELD_TYPE.DECIMAL, FIELD_TYPE.NEWDECIMAL):
                # Decimal as length-encoded string
                length = data[pos]
                pos += 1
                if length > 0:
                    row_values[i] = decimal.Decimal(data[pos:pos + length].tobytes().decode('ascii'))
                    pos += length
                else:
                    row_values[i] = decimal.Decimal('0')
            elif field_type in (FIELD_TYPE.DATE, FIELD_TYPE.NEWDATE):
                length_byte = data[pos]
                pos += 1
                if length_byte >= 4:
                    year, month, day = _STRUCT_HBB.unpack_from(data, pos)
                    try:
                        row_values[i] = datetime.date(year, month, day)
                    except (ValueError):
                        row_values[i] = None
                    pos += 4
                else:
                    row_values[i] = None
            elif field_type == FIELD_TYPE.TIME:
                length_byte = data[pos]
                pos += 1
                if length_byte == 12:
                    # Time with microseconds
                    negative, days, hours, minutes, seconds, microseconds = _STRUCT_BIBBBI.unpack_from(data, pos)
                    pos += 12
                    total_hours = days * 24 + hours
                    td = datetime.timedelta(hours=total_hours, minutes=minutes, seconds=seconds, microseconds=microseconds)
                    row_values[i] = -td if negative else td
                elif length_byte == 8:
                    # Time without microseconds
                    negative, days, hours, minutes, seconds = _STRUCT_BIBBB.unpack_from(data, pos)
                    pos += 8
                    total_hours = days * 24 + hours
                    row_values[i] = -datetime.timedelta(hours=total_hours, minutes=minutes, seconds=seconds) if negative else datetime.timedelta(hours=total_hours, minutes=minutes, seconds=seconds)
                else:
                    row_values[i] = None
            elif field_type in (FIELD_TYPE.DATETIME, FIELD_TYPE.TIMESTAMP):
                length_byte = data[pos]
                pos += 1
                if length_byte == 11:
                    # Datetime with microseconds
                    year, month, day, hours, minutes, seconds, microseconds = _STRUCT_HBBBBBI.unpack_from(data, pos)
                    pos += 11
                    try:
                        row_values[i] = datetime.datetime(year, month, day, hours, minutes, seconds, microseconds)
                    except (ValueError):
                        row_values[i] = None
                elif length_byte == 7:
                    # Datetime without microseconds
                    year, month, day, hours, minutes, seconds = _STRUCT_HBBBBB.unpack_from(data, pos)
                    pos += 7
                    try:
                        row_values[i] = datetime.datetime(year, month, day, hours, minutes, seconds, 0)
                    except (ValueError):
                        row_values[i] = None
                elif length_byte == 4:
                    # Date only
                    year, month, day = _STRUCT_HBB.unpack_from(data, pos)
                    pos += 4
                    try:
                        row_values[i] = datetime.datetime(year, month, day, 0, 0, 0, 0)
                    except (ValueError):
                        row_values[i] = None
                else:
                    row_values[i] = None
            else:
                # String types (VARCHAR, TEXT, BLOB, JSON, etc.) - length-encoded
                length = data[pos]
                if (length < 0xFB):
                    pos += 1
                elif length == 0xFB:
                    pos += 1
                    continue
                elif length == 0xFC:
                    length = _STRUCT_H.unpack_from(data, pos + 1)[0]
                    pos += 3
                elif length == 0xFD:
                    length = struct.unpack('<I', data[pos+ 1:pos+4].tobytes() + b'\x00')[0]
                    pos += 4
                else:  # 0xFE
                    length = _STRUCT_Q.unpack_from(data, pos + 1)[0]
                    pos += 9

                val = bytes(data[pos:pos + length])
                if column.special_format:
                    if column.ext_type_format == b'json':
                        row_values[i] = val.decode('utf-8')
                    elif column.ext_type_name == b'inet6' or column.ext_type_name == b'inet4':
                        row_values[i] = val.decode('ascii')
                        if config.native_object:
                            row_values[i] = ipaddress.ip_address(row_values[i])
                    elif column.ext_type_name == b'uuid':
                        row_values[i] = val.decode('ascii')
                        if config.native_object:
                            row_values[i] = uuid.UUID(row_values[i])
                elif column.character_set == 63 and field_type != FIELD_TYPE.JSON:  # Binary
                    row_values[i] = val
                else:
                    row_values[i] = val.decode('utf-8', errors='replace')
                pos += length
        
        return tuple(row_values)

        
    @abstractmethod
    def get_ssl_cipher(self) -> Optional[tuple]:
        """Get current SSL cipher information"""
        ...
    
    @abstractmethod
    def get_ssl_version(self) -> Optional[str]:
        """Get current TLS/SSL version"""
        ...
    
    @abstractmethod
    def get_peer_certificate(self) -> Optional[dict]:
        """Get peer SSL certificate information"""
        ...
    
