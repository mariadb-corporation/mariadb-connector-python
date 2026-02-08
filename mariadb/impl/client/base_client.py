# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Base Client abstract class for MariaDB connections

Contains all common logic shared between AsyncClient and SyncClient.
"""

import decimal
import datetime
import struct
import ipaddress
import uuid
from abc import ABC, abstractmethod
from typing import List, Optional, Callable, Dict, Tuple, Any

# Cached unpack_from methods for row parsing performance (avoids attribute lookup overhead)
_unpack_H = struct.Struct('<H').unpack_from  # unsigned short (2 bytes)
_unpack_I = struct.Struct('<I').unpack_from  # unsigned int (4 bytes)
_unpack_Q = struct.Struct('<Q').unpack_from  # unsigned long long (8 bytes)
_unpack_b = struct.Struct('<b').unpack_from  # signed byte
_unpack_h = struct.Struct('<h').unpack_from  # signed short
_unpack_i = struct.Struct('<i').unpack_from  # signed int
_unpack_q = struct.Struct('<q').unpack_from  # signed long long
_unpack_f = struct.Struct('<f').unpack_from  # float
_unpack_d = struct.Struct('<d').unpack_from  # double
_unpack_HBB = struct.Struct('<HBB').unpack_from  # year, month, day for date
_unpack_HBBBBB = struct.Struct('<HBBBBB').unpack_from  # year, month, day, hour, min, sec for datetime (no micro)
_unpack_HBBBBBI = struct.Struct('<HBBBBBI').unpack_from  # year, month, day, hour, min, sec, microsec for datetime
_unpack_BIBBB = struct.Struct('<BIBBB').unpack_from  # negative, days, hour, min, sec for time (no micro)
_unpack_BIBBBI = struct.Struct('<BIBBBI').unpack_from  # negative, days, hour, min, sec, microsec for time
_unpack_DATE_TEXT = struct.Struct('4s1s2s1s2s').unpack_from  # YYYY-MM-DD text protocol
_unpack_DATETIME_TEXT = struct.Struct('4s1s2s1s2s1s2s1s2s1s2s').unpack_from  # YYYY-MM-DD HH:MM:SS text protocol

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

# text conversion functions 
def parse_date_text(s: bytes):
    # YYYY-MM-DD
    _int = int
    parts = _unpack_DATE_TEXT(s, 0)  # returns 5-tuple: year_b, sep1, month_b, sep2, day_b
    # convert numeric positions to int, skip separators
    year, month, day = (_int(parts[i]) for i in (0, 2, 4))

    if year == 0 or month == 0 or day == 0:
        return None
    return datetime.date(int(year), int(month), int(day))

def parse_time_text(s: bytes):
    _int = int
    negative = s[0] == 45  # ord('-')
    if negative:
        s = s[1:]
    parts = s.split(b':')
    if len(parts) != 3:
        return None
    hours = _int(parts[0])
    minutes = _int(parts[1])
    sec_parts = parts[2].split(b'.')
    seconds = _int(sec_parts[0])
    microseconds = _int(sec_parts[1].ljust(6, b'0')) if len(sec_parts) > 1 else 0
    td = datetime.timedelta(hours=hours, minutes=minutes, seconds=seconds, microseconds=microseconds)
    return -td if negative else td

def parse_datetime_text(s: bytes):
    """Convert YYYY-MM-DD HH:MM:SS[.ffffff] bytes to datetime.datetime, None for zero dates."""
    if len(s) < 19:
        return None

    _int = int

    parts = _unpack_DATETIME_TEXT(s, 0)  # 11 elements: y, _, m, _, d, _, h, _, mi, _, s
    year, month, day, hour, minute, second = (_int(parts[i]) for i in (0, 2, 4, 6, 8, 10))

    if year == 0 or month == 0 or day == 0:
        return None

    microseconds = 0
    if len(s) > 19 and s[19] == ord('.'):
        frac = s[20:]
        l = len(frac)
        if l >= 6:
            microseconds = _int(frac[:6])
        else:
            microseconds = _int(frac) * (10 ** (6 - l))

    return datetime.datetime(year, month, day, hour, minute, second, microseconds)

def parse_uuid_bytes(s: bytes):
    return uuid.UUID(s.decode('ascii'))

def parse_ip_bytes(s: bytes):
    return ipaddress.ip_address(s.decode('ascii'))

def parse_json_bytes(s: bytes):
    return s.decode('utf-8', errors='ignore')

def parse_string_bytes(s: bytes):
    return s.decode('utf-8', errors='ignore')

def parse_decimal_bytes(s: bytes):
    return decimal.Decimal(s.decode('ascii'))

def parse_null(_):
    return None

def txt_conversion_table(columns, config):
    table = []
    for col in columns:
        t = col.type
        charset = getattr(col, 'character_set', None)
        ext_type_name = getattr(col, 'ext_type_name', None)
        ext_type_format = getattr(col, 'ext_type_format', None)

        if t in (FIELD_TYPE.TINY, FIELD_TYPE.SHORT, FIELD_TYPE.LONG,
                 FIELD_TYPE.LONGLONG, FIELD_TYPE.INT24, FIELD_TYPE.YEAR):
            table.append(int)

        elif t in (FIELD_TYPE.FLOAT, FIELD_TYPE.DOUBLE):
            table.append(float)

        elif t in (FIELD_TYPE.DECIMAL, FIELD_TYPE.NEWDECIMAL):
            table.append(parse_decimal_bytes)

        elif t in (FIELD_TYPE.VARCHAR, FIELD_TYPE.STRING, FIELD_TYPE.VAR_STRING, FIELD_TYPE.GEOMETRY,
                   FIELD_TYPE.TINY_BLOB, FIELD_TYPE.MEDIUM_BLOB, FIELD_TYPE.LONG_BLOB, FIELD_TYPE.BLOB):

            # special formats first
            if ext_type_format == b'json':
                table.append(parse_json_bytes)
            elif ext_type_name in (b'inet4', b'inet6'):
                table.append(parse_ip_bytes if getattr(config, 'native_object', False) else parse_string_bytes)
            elif ext_type_name == b'uuid':
                table.append(parse_uuid_bytes if getattr(config, 'native_object', False) else parse_string_bytes)
            # binary check
            elif charset == 63:
                table.append(bytes)
            # fallback text
            else:
                table.append(parse_string_bytes)

        elif t in (FIELD_TYPE.DATE, FIELD_TYPE.NEWDATE):
            table.append(parse_date_text)

        elif t == FIELD_TYPE.TIME:
            table.append(parse_time_text)

        elif t in (FIELD_TYPE.DATETIME, FIELD_TYPE.TIMESTAMP):
            table.append(parse_datetime_text)

        elif t == FIELD_TYPE.NULL:
            table.append(parse_null)

        else:
            table.append(parse_string_bytes)

    return table


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
        self.cert_fingerprint_validator: Optional['SSLFingerprintValidator'] = None
        self.auth_plugin: Optional['AuthenticationPlugin'] = None
        self.txt_conversion_table = None
        
        # Track active streaming (unbuffered) result at client level
        # This prevents "Commands out of sync" when multiple cursors share the same connection
        self._active_streaming_result: Optional[Any] = None
        
        # Cached payload writer for packet generation (reused to avoid allocations)
        from ..message.payload_writer import PayloadWriter
        self._payload_writer = PayloadWriter()

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
        
        # Apply additional client_flag from configuration (for C extension compatibility)
        # This allows SQLAlchemy to set FOUND_ROWS and other flags
        if self.configuration.client_flag:
            capabilities |= self.configuration.client_flag
        
        # Only use capabilities that the server supports
        return capabilities & self.context.server_capabilities
    
    # =========================================================================
    # Result Set Parsing
    # =========================================================================

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

    def _set_txt_converters(self, columns, config):
        self.txt_conversion_table= txt_conversion_table(columns, config)

    # =========================================================================
    # Row Data Parsing Methods
    # =========================================================================

    def _parse_text_row_data(self, data: memoryview, columns: List[ColumnDefinitionPacket], config: 'Configuration', num_cols: int) -> tuple:
        """Parse text protocol row data packet with inlined decoding"""
        row_values = [None] * num_cols
        pos = 0
        data_bytes = data.tobytes()  # Convert once for faster access

        converters = self.txt_conversion_table

            # Read length-encoded integer for field length
        for i in range(num_cols):
            length_byte = data[pos]
            if (length_byte < 0xFB):
                length = length_byte
                pos += 1
            elif (length_byte == 0xFB):
                pos += 1
                continue
            elif length_byte == 0xFC:
                length = _unpack_H(data, pos + 1)[0]
                pos += 3
            elif length_byte == 0xFD:
                length = struct.unpack('<I', bytes(data[pos+ 1:pos+4]) + b'\x00')[0]
                pos += 4
            else:
                length = _unpack_Q(data, pos + 1)[0]
                pos += 9

            field_bytes = data_bytes[pos:pos+length]
            pos += length

            row_values[i] = converters[i](field_bytes)

        return tuple(row_values)

    def _parse_binary_row_data(self, data: memoryview, columns: List[ColumnDefinitionPacket], config: 'Configuration', num_cols: int) -> tuple:
        """Parse binary protocol row data packet with inlined decoding"""
        pos = 1  # Skip 0x00 header
        # Read NULL bitmap
        null_bitmap_length = (num_cols + 9) >> 3
        null_bitmap = data[pos:pos + null_bitmap_length]
        pos += null_bitmap_length
        
        # Parse column values with inlined decoding
        row_values = [None] * num_cols
        
        for i in range(num_cols):
            column = columns[i]

            if null_bitmap[(i + 2) >> 3] & (1 << ((i + 2) & 7)):
                continue

            # Decode based on field type
            field_type = column.type
            if field_type in (FIELD_TYPE.LONG, FIELD_TYPE.INT24):
                if (column.flags & FIELD_FLAG.UNSIGNED) != 0:
                    row_values[i] = _unpack_I(data, pos)[0]
                else:
                    row_values[i] = _unpack_i(data, pos)[0]
                pos += 4
            elif field_type == FIELD_TYPE.LONGLONG:
                if (column.flags & FIELD_FLAG.UNSIGNED) != 0:
                    row_values[i] = _unpack_Q(data, pos)[0]
                else:
                    row_values[i] = _unpack_q(data, pos)[0]
                pos += 8
            elif field_type in (FIELD_TYPE.VARCHAR, FIELD_TYPE.BIT, FIELD_TYPE.ENUM, FIELD_TYPE.SET, \
                                FIELD_TYPE.TINY_BLOB, FIELD_TYPE.MEDIUM_BLOB, FIELD_TYPE.LONG_BLOB, FIELD_TYPE.BLOB, FIELD_TYPE.VAR_STRING, \
                                FIELD_TYPE.STRING, FIELD_TYPE.GEOMETRY):
                # String types (VARCHAR, TEXT, BLOB, JSON, etc.) - length-encoded
                length = data[pos]

                if (length < 0xFB):
                    pos += 1
                elif length == 0xFC:
                    length = _unpack_H(data, pos + 1)[0]
                    pos += 3
                elif length == 0xFD:
                    length = struct.unpack('<I', data[pos+ 1:pos+4].tobytes() + b'\x00')[0]
                    pos += 4
                else:  # 0xFE
                    length = _unpack_Q(data, pos + 1)[0]
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
                    row_values[i] = val.decode('utf-8', errors='ignore')
                pos += length

            elif field_type == FIELD_TYPE.TINY:
                if (column.flags & FIELD_FLAG.UNSIGNED) != 0:
                    row_values[i] = data[pos]
                else:
                    row_values[i] = _unpack_b(data, pos)[0]
                pos += 1
            elif field_type in (FIELD_TYPE.SHORT, FIELD_TYPE.YEAR):
                if (column.flags & FIELD_FLAG.UNSIGNED) != 0:
                    row_values[i] = _unpack_H(data, pos)[0]
                else:
                    row_values[i] = _unpack_h(data, pos)[0]
                pos += 2
            elif field_type == FIELD_TYPE.FLOAT:
                row_values[i] = _unpack_f(data, pos)[0]
                pos += 4
            elif field_type == FIELD_TYPE.DOUBLE:
                row_values[i] = _unpack_d(data, pos)[0]
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
                    year, month, day = _unpack_HBB(data, pos)
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
                    negative, days, hours, minutes, seconds, microseconds = _unpack_BIBBBI(data, pos)
                    pos += 12
                    total_hours = days * 24 + hours
                    td = datetime.timedelta(hours=total_hours, minutes=minutes, seconds=seconds, microseconds=microseconds)
                    row_values[i] = -td if negative else td
                elif length_byte == 8:
                    # Time without microseconds
                    negative, days, hours, minutes, seconds = _unpack_BIBBB(data, pos)
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
                    year, month, day, hours, minutes, seconds, microseconds = _unpack_HBBBBBI(data, pos)
                    pos += 11
                    try:
                        row_values[i] = datetime.datetime(year, month, day, hours, minutes, seconds, microseconds)
                    except (ValueError):
                        row_values[i] = None
                elif length_byte == 7:
                    # Datetime without microseconds
                    year, month, day, hours, minutes, seconds = _unpack_HBBBBB(data, pos)
                    pos += 7
                    try:
                        row_values[i] = datetime.datetime(year, month, day, hours, minutes, seconds, 0)
                    except (ValueError):
                        row_values[i] = None
                elif length_byte == 4:
                    # Date only
                    year, month, day = _unpack_HBB(data, pos)
                    pos += 4
                    try:
                        row_values[i] = datetime.datetime(year, month, day, 0, 0, 0, 0)
                    except (ValueError):
                        row_values[i] = None
                else:
                    row_values[i] = None

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
    
