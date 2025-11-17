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
from typing import List, Optional, Any, Dict

from .context import Context
from .socket.payload_parser import PayloadParser
from .socket.mutable_int import MutableInt
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
from ..message.server.error_packet import ErrorPacket


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
        self.configuration = configuration
        self.host_address: Optional[HostAddress] = None
        self.sequence = MutableInt(0)  # Shared sequence number
        self.context: Optional[Context] = None
        self.exception_factory = ExceptionFactory()
        self.closed = False
        self.socket_timeout = configuration.socket_timeout
        self.connect_timeout = configuration.connect_timeout
        self.lock = threading.RLock()
        
        # Connection state
        self.connected = False
        self.read_only = configuration.read_only
    
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
    def _send_message(self, message: ClientMessage) -> None:
        """Send client message to server"""
        ...
    
    @abstractmethod
    def execute(self, message: ClientMessage, config: 'Configuration', can_redo: bool = False, buffered: bool = True, prepare_stmt_packet: Optional['PrepareStmtPacket'] = None) -> List['Completion']:
        """Send client message and read result"""
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
    def close_prepared_statement(self, stmt: PrepareStmtPacket) -> None:
        """Close a prepared statement"""
        ...
    
    @abstractmethod
    def set_socket_timeout(self, milliseconds: int) -> None:
        """Set socket timeout"""
        ...
    
    @abstractmethod
    def reset(self) -> None:
        """Reset connection"""
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
    
    @abstractmethod
    def get_socket_ip(self) -> Optional[str]:
        """Get socket IP address"""
        ...
    
    # =========================================================================
    # Protocol Parsing
    # =========================================================================
    
    def _parse_handshake(self, packet: bytes) -> Context:
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
        
        pos = 0
        
        # Protocol version (1 byte)
        protocol_version = packet[pos]
        pos += 1

        if protocol_version != 0x0a:
            raise OperationalError(f"Unexpected initial handshake protocol value [{protocol_version}]")
        
        # Server version (null-terminated string)
        version_end = bytes(packet).find(0, pos)
        server_version = packet[pos:version_end].decode('utf-8')
        pos = version_end + 1

        thread_id = struct.unpack('<I', packet[pos:pos + 4])[0]
        pos += 4
        
        # Auth plugin data part 1 - seed1 (8 bytes)
        seed1 = packet[pos:pos + 8]
        pos += 8
        
        # Skip filler (1 byte, should be 0x00)
        pos += 1
        
        # Server capabilities first 2 bytes
        server_capabilities_2_first_bytes = struct.unpack('<H', packet[pos:pos + 2])[0]
        pos += 2
        
        # Default collation (1 byte)
        default_collation = packet[pos]
        pos += 1
        
        # Server status (2 bytes)
        server_status = struct.unpack('<H', packet[pos:pos + 2])[0]
        pos += 2
        
        # Server capabilities 4 first bytes (combine lower and upper 2 bytes)
        server_capabilities_upper = 0
        if pos + 2 <= len(packet):
            server_capabilities_upper = struct.unpack('<H', packet[pos:pos + 2])[0]
            pos += 2
        
        server_capabilities_4_first_bytes = server_capabilities_2_first_bytes + (server_capabilities_upper << 16)
        
        # Salt length calculation
        salt_length = 0
        if (server_capabilities_4_first_bytes & constants.CAPABILITY.PLUGIN_AUTH) != 0:
            salt_length = max(12, packet[pos] - 9)
            pos += 1
        else:
            # Skip 1 byte
            pos += 1
        
        # Skip reserved bytes (6 bytes)
        if pos + 6 <= len(packet):
            pos += 6
        else:
            # Handle shorter packets gracefully
            pos = min(pos + 6, len(packet))
        
        # MariaDB additional capabilities (4 bytes)
        # Filled only if MariaDB server 10.2+
        mariadb_additional_capacities = 0
        if pos + 4 <= len(packet):
            mariadb_additional_capacities = struct.unpack('<I', packet[pos:pos + 4])[0]
            pos += 4
        
        # Handle seed2 and combine with seed1
        seed = seed1
        if (server_capabilities_4_first_bytes & constants.CAPABILITY.SECURE_CONNECTION) != 0:
            if salt_length > 0:
                # Read salt_length bytes for seed2
                if pos + salt_length <= len(packet):
                    seed2 = packet[pos:pos + salt_length]
                    pos += salt_length
                else:
                    # Read what's available
                    seed2 = packet[pos:]
                    pos = len(packet)
            else:
                # Read null-terminated seed2
                seed2_end = packet.find(0, pos)
                if seed2_end != -1:
                    seed2 = packet[pos:seed2_end]
                    pos = seed2_end + 1
                else:
                    seed2 = packet[pos:]
                    pos = len(packet)
            
            # Combine seed1 and seed2
            seed = seed1 + seed2
        
        # Skip null terminator if present
        pos += 1
        
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
            server_capabilities = (server_capabilities_4_first_bytes & 0xffffffff) + (mariadb_additional_capacities << 32)
            server_mariadb = True
        else:
            server_capabilities = server_capabilities_4_first_bytes & 0xffffffff
        
        # Auth plugin type (null-terminated string)
        auth_plugin_name = None
        if (server_capabilities_4_first_bytes & constants.CAPABILITY.PLUGIN_AUTH) != 0:
            plugin_end = packet.find(0, pos)
            if plugin_end != -1:
                auth_plugin_name = packet[pos:plugin_end].decode('utf-8')
            else:
                auth_plugin_name = packet[pos:].decode('utf-8')
        
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
            constants.CAPABILITY.CACHE_METDATA
        )
        
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
    
    # ========================================================================
    # Synchronous parsing methods (no I/O, shared between Async and Sync)
    # ========================================================================
    
    def _handle_plugin_auth_continue(self, packet: bytearray) -> None:
        """
        Handle plugin authentication continuation
        
        Args:
            packet: Authentication continuation packet
        """
        # For now, treat as successful authentication
        # This would need more sophisticated handling for multi-round auth
        OkPacket.decode(packet, self.context)
    
    def _apply_converters(self, row_values: list, columns: List[Dict[str, Any]], config: 'Configuration') -> tuple:
        """
        Apply converters to row values
        
        Args:
            row_values: List of parsed row values
            columns: Column definitions
            config: Configuration with converter settings
            
        Returns:
            Tuple of converted values
        """
        if not config.converter:
            return tuple(row_values)
        
        converted_values = []
        for i, value in enumerate(row_values):
            if columns[i].column_type in config.converter:
                converter_func = config.converter[columns[i].column_type]
                try:
                    value = converter_func(value)
                except Exception:
                    # If conversion fails, keep original value
                    pass
            converted_values.append(value)
        return tuple(converted_values)

    def _parse_row_data(self, packet: bytes, columns: List[ColumnDefinitionPacket], config: 'Configuration', is_binary: bool = False) -> tuple:
        """
        Parse row data packet
        
        Args:
            packet: Row data packet
            columns: Column definitions
            
        Returns:
            Tuple of row values
        """
        try:
            if is_binary:
                return self._parse_binary_row_data(packet, columns, config)
            
            pos = 0
            row_values = []
            
            for column in columns:
                match column.column_type:
                    case (FIELD_TYPE.TINY | FIELD_TYPE.SHORT | FIELD_TYPE.LONG | 
                          FIELD_TYPE.LONGLONG | FIELD_TYPE.INT24 | FIELD_TYPE.YEAR):
                        # Read as string and convert to integer (simpler and more reliable)
                        val, pos = PayloadParser.read_length_encoded_string_at(packet, pos)
                        try:
                            value = int(val) if val is not None else None
                        except (ValueError, TypeError):
                            value = None
                    case FIELD_TYPE.FLOAT | FIELD_TYPE.DOUBLE:
                        # Read as string and convert to float
                        val, pos = PayloadParser.read_length_encoded_string_at(packet, pos)
                        value = float(val) if val is not None else None
                    case FIELD_TYPE.DATE | FIELD_TYPE.NEWDATE:
                        # Parse DATE as datetime.date
                        val, pos = PayloadParser.read_length_encoded_string_at(packet, pos)
                        if val is not None:
                            try:
                                year, month, day = map(int, val.split('-'))
                                value = datetime.date(year, month, day)
                            except (ValueError, AttributeError) as e:
                                value = None  # Fallback to None if parsing fails
                        else:
                            value = None
                    case FIELD_TYPE.TIME:
                        # Parse TIME as datetime.timedelta
                        val, pos = PayloadParser.read_length_encoded_string_at(packet, pos)
                        if val is not None:
                            try:
                                # Handle TIME format: HH:MM:SS[.ffffff] or HHH:MM:SS[.ffffff] (can be > 24 hours)
                                # Can also be negative: -HH:MM:SS[.ffffff]
                                is_negative = val.startswith('-')
                                if is_negative:
                                    val = val[1:]
                                
                                parts = val.split(':')
                                if len(parts) >= 3:
                                    hours = int(parts[0])
                                    minutes = int(parts[1])
                                    # Handle fractional seconds: "24.051" -> seconds=24, microseconds=51000
                                    seconds_parts = parts[2].split('.')
                                    seconds = int(seconds_parts[0])
                                    microseconds = 0
                                    
                                    if len(seconds_parts) > 1:
                                        # Pad or truncate to 6 digits for microseconds
                                        frac_str = seconds_parts[1].ljust(6, '0')[:6]
                                        microseconds = int(frac_str)
                                    
                                    td = datetime.timedelta(hours=hours, minutes=minutes, seconds=seconds, microseconds=microseconds)
                                    value = -td if is_negative else td
                                else:
                                    value = val  # Fallback to string
                            except (ValueError, AttributeError):
                                value = val  # Fallback to string if parsing fails
                        else:
                            value = None
                    case (FIELD_TYPE.DATETIME | FIELD_TYPE.TIMESTAMP):
                        # Parse DATETIME as datetime.datetime
                        val, pos = PayloadParser.read_length_encoded_string_at(packet, pos)
                        if val is not None:
                            try:
                                # Handle DATETIME format: YYYY-MM-DD HH:MM:SS[.ffffff]
                                if ' ' in val:
                                    date_part, time_part = val.split(' ', 1)
                                    year, month, day = map(int, date_part.split('-'))
                                    
                                    time_parts = time_part.split(':')
                                    hours = int(time_parts[0])
                                    minutes = int(time_parts[1])
                                    # Handle fractional seconds: "24.123456" -> seconds=24, microseconds=123456
                                    seconds_parts = time_parts[2].split('.')
                                    seconds = int(seconds_parts[0])
                                    microseconds = 0
                                    
                                    if len(seconds_parts) > 1:
                                        # Pad or truncate to 6 digits for microseconds
                                        frac_str = seconds_parts[1].ljust(6, '0')[:6]
                                        microseconds = int(frac_str)
                                    
                                    value = datetime.datetime(year, month, day, hours, minutes, seconds, microseconds)
                                else:
                                    # Date only
                                    year, month, day = map(int, val.split('-'))
                                    value = datetime.datetime(year, month, day)
                            except (ValueError, AttributeError):
                                value = val  # Fallback to string if parsing fails
                        else:
                            value = None
                    case (FIELD_TYPE.DECIMAL | FIELD_TYPE.NEWDECIMAL):
                        # DECIMAL types must return decimal.Decimal
                        val, pos = PayloadParser.read_length_encoded_string_at(packet, pos, encoding='ascii')
                        value = decimal.Decimal(val) if val is not None else None
                    case FIELD_TYPE.JSON:
                        value, pos = PayloadParser.read_length_encoded_string_at(packet, pos)
                    case FIELD_TYPE.NULL:
                        # NULL type - read length-encoded value (will be None)
                        value, pos = PayloadParser.read_length_encoded_string_at(packet, pos)
                    case _:
                        if (column.ext_type_format == 'json'):
                            value, pos = PayloadParser.read_length_encoded_string_at(packet, pos)
                        else:
                            match column.ext_type_name:
                                case ('inet6' | 'inet4'):
                                    value, pos = PayloadParser.read_length_encoded_string_at(packet, pos)
                                    if config.native_object:
                                        value = ipaddress.ip_address(value)
                                case 'uuid':
                                    value, pos = PayloadParser.read_length_encoded_string_at(packet, pos)
                                    if config.native_object:
                                        value = uuid.UUID(value)
                                case _:
                                    # Default case for VARCHAR, STRING, etc.
                                    # Check if BINARY flag is set to determine if we should read as bytes or string
                                    if ((column.flags & FIELD_FLAG.BINARY) > 0) or (column.character_set == 63):
                                        # Binary data - read as bytes
                                        value, pos = PayloadParser.read_length_encoded_bytes_at(packet, pos)
                                    else:
                                        # Text data - read as string
                                        value, pos = PayloadParser.read_length_encoded_string_at(packet, pos)


                row_values.append(value)
            
            # Apply converters if configured (after parsing all values)
            return self._apply_converters(row_values, columns, config)
            
        except Exception as e:
            # Return tuple with None values if parsing fails
            return tuple(None for _ in columns)
    
    def _parse_binary_row_data(self, packet: bytes, columns: List[ColumnDefinitionPacket], config: 'Configuration') -> tuple:
        """
        Parse binary row data packet (from COM_STMT_EXECUTE)
        
        Args:
            packet: Binary row data packet
            columns: Column definitions
            
        Returns:
            Tuple of row values
        """
        if len(packet) == 0:
            return tuple(None for _ in columns)
        
        pos = 1
        
        # Read NULL bitmap
        null_bitmap_length = (len(columns) + 9) // 8
        null_bitmap = packet[pos:pos + null_bitmap_length]
        pos += null_bitmap_length
        
        # Parse column values
        row_values = []
        
        for i, column in enumerate(columns):
            # Check if column is NULL using bitmap
            if self._is_null_bitmap(i, null_bitmap):
                row_values.append(None)
                continue
            
            # Parse non-NULL value based on column type
            value, pos = self._parse_binary_column_value(packet, pos, column, config)
            row_values.append(value)
        
        # Apply converters if configured (after parsing all values)
        return self._apply_converters(row_values, columns, config)
    
    # _is_null_bitmap() is inherited from BaseClient (synchronous, no I/O)
    
    def _parse_binary_column_value(self, packet: bytes, pos: int, column: ColumnDefinitionPacket, config: 'Configuration') -> tuple[Any, int]:
        """
        Parse binary column value
        
        Args:
            packet: Packet data
            pos: Current position
            column: Column definition
            
        Returns:
            Tuple of (value, new_position)
        """
        match column.column_type:
            case FIELD_TYPE.TINY:
                if pos + 1 > len(packet):
                    return None, pos
                if column.flags & FIELD_FLAG.UNSIGNED:
                    value = struct.unpack('<B', packet[pos:pos + 1])[0]
                else:
                    value = struct.unpack('<b', packet[pos:pos + 1])[0]
                return value, pos + 1
                
            case (FIELD_TYPE.SHORT | FIELD_TYPE.YEAR):
                if pos + 2 > len(packet):
                    return None, pos
                if column.flags & FIELD_FLAG.UNSIGNED:
                    value = struct.unpack('<H', packet[pos:pos + 2])[0]
                else:
                    value = struct.unpack('<h', packet[pos:pos + 2])[0]
                return value, pos + 2
                
            case FIELD_TYPE.LONG | FIELD_TYPE.INT24:
                if pos + 4 > len(packet):
                    return None, pos
                if column.flags & FIELD_FLAG.UNSIGNED:
                    value = struct.unpack('<I', packet[pos:pos + 4])[0]
                else:
                    value = struct.unpack('<i', packet[pos:pos + 4])[0]
                return value, pos + 4
                
            case FIELD_TYPE.LONGLONG:
                if pos + 8 > len(packet):
                    return None, pos
                if column.flags & FIELD_FLAG.UNSIGNED:
                    value = struct.unpack('<Q', packet[pos:pos + 8])[0]
                else:
                    value = struct.unpack('<q', packet[pos:pos + 8])[0]
                return value, pos + 8
                
            case FIELD_TYPE.FLOAT:
                if pos + 4 > len(packet):
                    return None, pos
                value = struct.unpack('<f', packet[pos:pos + 4])[0]
                return value, pos + 4
                
            case FIELD_TYPE.DOUBLE:
                if pos + 8 > len(packet):
                    return None, pos
                value = struct.unpack('<d', packet[pos:pos + 8])[0]
                return value, pos + 8
                
            case (FIELD_TYPE.DATE | FIELD_TYPE.NEWDATE):
                # Binary DATE format: 1 + 4 bytes (length + year + month + day)
                length_byte = packet[pos] if pos < len(packet) else 0
                pos += 1

                if length_byte == 0:
                    return None, pos
                elif length_byte >= 4:
                    if pos + 4 > len(packet):
                        return None, pos
                    year = struct.unpack('<H', packet[pos:pos + 2])[0]
                    month = packet[pos + 2]
                    day = packet[pos + 3]
                    try:
                        value = datetime.date(year, month, day)
                    except ValueError as e:
                        value = None
                    return value, pos + length_byte
                else:
                    return None, pos + length_byte
                    
            case FIELD_TYPE.TIME:
                # Binary TIME format: 1 + 8 or 12 bytes
                length_byte = packet[pos] if pos < len(packet) else 0
                pos += 1
                
                if length_byte == 0:
                    return None, pos
                elif length_byte >= 8:
                    if pos + 8 > len(packet):
                        return None, pos
                    negative = packet[pos]
                    days = struct.unpack('<I', packet[pos + 1:pos + 5])[0]
                    hours = packet[pos + 5]
                    minutes = packet[pos + 6]
                    seconds = packet[pos + 7]
                    microseconds = 0
                    
                    if length_byte == 12 and pos + 12 <= len(packet):
                        microseconds = struct.unpack('<I', packet[pos + 8:pos + 12])[0]
                    
                    # Calculate total hours
                    total_hours = days * 24 + hours
                    
                    try:
                        # Use timedelta for TIME values >= 24 hours
                        value = datetime.timedelta(hours=total_hours, minutes=minutes, seconds=seconds, microseconds=microseconds)
                        if negative:
                            value = -value
                    except ValueError:
                        value = None
                        
                    return value, pos + length_byte
                else:
                    return None, pos + length_byte
                    
            case FIELD_TYPE.DATETIME | FIELD_TYPE.NEWDATE | FIELD_TYPE.TIMESTAMP:
                # Binary DATETIME format: 1 + 4, 7, or 11 bytes
                length_byte = packet[pos] if pos < len(packet) else 0
                pos += 1
                
                if length_byte == 0:
                    return None, pos
                elif length_byte >= 4:
                    if pos + 4 > len(packet):
                        return None, pos
                    year = struct.unpack('<H', packet[pos:pos + 2])[0]
                    month = packet[pos + 2]
                    day = packet[pos + 3]
                    
                    hours = minutes = seconds = microseconds = 0
                    
                    if length_byte >= 7 and pos + 7 <= len(packet):
                        hours = packet[pos + 4]
                        minutes = packet[pos + 5]
                        seconds = packet[pos + 6]
                        
                    if length_byte == 11 and pos + 11 <= len(packet):
                        microseconds = struct.unpack('<I', packet[pos + 7:pos + 11])[0]
                    
                    try:
                        value = datetime.datetime(year, month, day, hours, minutes, seconds, microseconds)
                    except ValueError:
                        value = None
                        
                    return value, pos + length_byte
                else:
                    return None, pos + length_byte
                
            case (FIELD_TYPE.DECIMAL | FIELD_TYPE.NEWDECIMAL):
                # DECIMAL types must return decimal.Decimal
                val, pos = PayloadParser.read_length_encoded_string_at(packet, pos)
                value = decimal.Decimal(val) if val is not None else None
                return value, pos
            case FIELD_TYPE.JSON:
                return PayloadParser.read_length_encoded_string_at(packet, pos)
            case (FIELD_TYPE.BLOB | FIELD_TYPE.TINY_BLOB | FIELD_TYPE.MEDIUM_BLOB | FIELD_TYPE.LONG_BLOB):
                if (column.ext_type_format == 'json'):
                    return PayloadParser.read_length_encoded_string_at(packet, pos)
                # BLOB types must return bytes
                return PayloadParser.read_length_encoded_bytes_at(packet, pos)
                
            case (FIELD_TYPE.VAR_STRING | FIELD_TYPE.STRING | FIELD_TYPE.VARCHAR):
                match (column.ext_type_name):
                    case ("inet6" | "inet4"):
                        value, pos = PayloadParser.read_length_encoded_bytes_at(packet, pos)
                        if config.native_object:
                            value = ipaddress.ip_address(value)
                        return value, pos
                    case "uuid":
                        value, pos = PayloadParser.read_length_encoded_bytes_at(packet, pos)
                        if config.native_object:
                            value = uuid.UUID(value)
                        return value, pos
                    case _:
                        # String types - check BINARY flag or binary charset (63)
                        # MySQL uses charset 63 for OUT parameters instead of BINARY flag
                        if (column.flags & FIELD_FLAG.BINARY) or (column.character_set == 63):
                            # Binary string - return bytes
                            return PayloadParser.read_length_encoded_bytes_at(packet, pos)
                        else:
                            # Text string - return string
                            return PayloadParser.read_length_encoded_string_at(packet, pos)
                
            case _:
                # Default to length-encoded string
                return PayloadParser.read_length_encoded_string_at(packet, pos)

    # _parse_error_packet() is inherited from BaseClient (synchronous, no I/O)
    

    @abstractmethod
    def get_ssl_cipher(self) -> Optional[tuple]:
        """
        Get current SSL cipher information
        
        Returns:
            Cipher tuple (name, version, bits) or None if not using SSL
        """
        pass
    
    @abstractmethod
    def get_ssl_version(self) -> Optional[str]:
        """
        Get current TLS/SSL version
        
        Returns:
            TLS version string (e.g., 'TLSv1.3') or None if not using SSL
        """
        pass
    
    @abstractmethod
    def get_peer_certificate(self) -> Optional[dict]:
        """
        Get peer SSL certificate information
        
        Returns:
            Certificate dict or None if not using SSL
        """
        pass
    
