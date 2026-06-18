# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from __future__ import annotations

"""
Base Client abstract class for MariaDB connections

Contains all common logic shared between AsyncClient and SyncClient.
"""

import decimal
import datetime
import os
import stat
import struct
import sys
import ipaddress
import uuid
from abc import ABC, abstractmethod
from typing import List, Optional, Callable, Dict, Tuple, Any, TYPE_CHECKING, Union

# Protocol constants — mirror mysql_protocol_type from Connector/C mysql.h
PROTOCOL_DEFAULT = 0
PROTOCOL_TCP     = 1
PROTOCOL_SOCKET  = 2

# Default Unix socket path used when host='localhost' and no unix_socket
# was given.  Mirrors what libmariadb (the C connector) does: each distro
# packages libmariadb compiled with a single MARIADB_UNIX_ADDR value that
# matches where that distro's MariaDB/MySQL package puts its socket.  We
# detect the distro once at module load and pick the matching path.
#
# This is intentionally one path per system (not a probed list) so that
# behaviour matches the C extension byte-for-byte: same default everywhere,
# same failure mode (TCP fallback) if the socket isn't where it should be.
#
# Security: every path returned here lives under a root-owned directory
# (/run, /var/run, /var/lib), so a non-privileged attacker cannot plant a
# fake socket at the probed location.  We never probe '/tmp/mysql.sock'
# (which is libmariadb's upstream compile default but lives in a world-
# writable directory).  Users who genuinely need /tmp/mysql.sock must pass
# unix_socket='/tmp/mysql.sock' explicitly.

def _resolve_default_unix_socket() -> Optional[str]:
    """Pick the Unix socket path that libmariadb would have been compiled
    with on this platform.  Called once at module import.  Returns None on
    non-Linux platforms or unknown distros (caller falls back to TCP)."""
    if sys.platform != 'linux':
        return None
    try:
        with open('/etc/os-release', 'r', encoding='utf-8') as f:
            info: Dict[str, str] = {}
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, _, v = line.partition('=')
                info[k] = v.strip().strip('"').strip("'")
    except OSError:
        return None

    # ID is the canonical distro id; ID_LIKE lists ancestors (e.g. Ubuntu has
    # ID_LIKE="debian").  Combining both lets us match derivatives without
    # enumerating every downstream.
    family = (info.get('ID', '') + ' ' + info.get('ID_LIKE', '')).lower().split()

    # Paths verified against each distro's libmariadb-connector-c packaging
    # (compile-time MARIADB_UNIX_ADDR / INSTALL_UNIX_ADDRDIR) so this matches
    # what the C extension would resolve to via libmariadb on the same OS.
    if any(d in family for d in ('debian', 'ubuntu', 'raspbian', 'kali')):
        return '/run/mysqld/mysqld.sock'        # Debian libmariadb3 .deb
    if any(d in family for d in ('rhel', 'fedora', 'centos', 'rocky', 'almalinux')):
        return '/var/lib/mysql/mysql.sock'      # Fedora mariadb-connector-c.spec
    if 'arch' in family:
        return '/run/mysqld/mysqld.sock'        # Arch PKGBUILD
    if 'alpine' in family:
        return '/run/mysqld/mysqld.sock'        # Alpine APKBUILD
    if 'suse' in family or 'opensuse' in family or 'sles' in family:
        return '/run/mysql/mysql.sock'          # openSUSE OBS (note: 'mysql' not 'mysqld')
    return None

_DEFAULT_UNIX_SOCKET: Optional[str] = _resolve_default_unix_socket()

def _find_default_unix_socket() -> Optional[str]:
    """Return the per-distro default socket path if it exists and is a real
    socket file, else None.  Distro detection happens once at module load."""
    if _DEFAULT_UNIX_SOCKET is None:
        return None
    try:
        if stat.S_ISSOCK(os.stat(_DEFAULT_UNIX_SOCKET).st_mode):
            return _DEFAULT_UNIX_SOCKET
    except OSError:
        pass
    return None

if TYPE_CHECKING:
    from ..plugin.authentication_plugin import AuthenticationPlugin
    from .ssl.ssl_fingerprint_validator import SSLFingerprintValidator

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
from ..message.server.column_definition_packet import ColumnsDefinition
from .exception_factory import ExceptionFactory
from ...exceptions import OperationalError
from mariadb_shared.constants import FIELD_TYPE, FIELD_FLAG
from mariadb_shared import constants
from ..message.server.ok_packet import OkPacket
try:
    from cachetools import LRUCache
except ImportError:
    LRUCache = None

# Frozenset type constants for O(1) lookup in row parsers (text protocol)
_TEXT_INT_TYPES = frozenset((
    FIELD_TYPE.TINY, FIELD_TYPE.SHORT, FIELD_TYPE.LONG,
    FIELD_TYPE.LONGLONG, FIELD_TYPE.INT24, FIELD_TYPE.YEAR,
))
_TEXT_STRING_TYPES = frozenset((
    FIELD_TYPE.VARCHAR, FIELD_TYPE.BIT, FIELD_TYPE.ENUM, FIELD_TYPE.SET,
    FIELD_TYPE.TINY_BLOB, FIELD_TYPE.MEDIUM_BLOB, FIELD_TYPE.LONG_BLOB,
    FIELD_TYPE.BLOB, FIELD_TYPE.VAR_STRING, FIELD_TYPE.STRING, FIELD_TYPE.GEOMETRY,
    FIELD_TYPE.VECTOR,
))
_TEXT_FLOAT_TYPES = frozenset((FIELD_TYPE.FLOAT, FIELD_TYPE.DOUBLE))
_TEXT_DECIMAL_TYPES = frozenset((FIELD_TYPE.DECIMAL, FIELD_TYPE.NEWDECIMAL))
_TEXT_DATE_TYPES = frozenset((FIELD_TYPE.DATE, FIELD_TYPE.NEWDATE))
_TEXT_DATETIME_TYPES = frozenset((FIELD_TYPE.DATETIME, FIELD_TYPE.TIMESTAMP))

# Frozenset type constants for O(1) lookup in row parsers (binary protocol)
_BIN_INT32_TYPES = frozenset((FIELD_TYPE.LONG, FIELD_TYPE.INT24))
_BIN_STRING_TYPES = frozenset((
    FIELD_TYPE.VARCHAR, FIELD_TYPE.BIT, FIELD_TYPE.ENUM, FIELD_TYPE.SET,
    FIELD_TYPE.TINY_BLOB, FIELD_TYPE.MEDIUM_BLOB, FIELD_TYPE.LONG_BLOB,
    FIELD_TYPE.BLOB, FIELD_TYPE.VAR_STRING, FIELD_TYPE.STRING,
    FIELD_TYPE.GEOMETRY, FIELD_TYPE.JSON, FIELD_TYPE.VECTOR,
))
_BIN_SHORT_TYPES = frozenset((FIELD_TYPE.SHORT, FIELD_TYPE.YEAR))
_BIN_DECIMAL_TYPES = frozenset((FIELD_TYPE.DECIMAL, FIELD_TYPE.NEWDECIMAL))
_BIN_DATE_TYPES = frozenset((FIELD_TYPE.DATE, FIELD_TYPE.NEWDATE))
_BIN_DATETIME_TYPES = frozenset((FIELD_TYPE.DATETIME, FIELD_TYPE.TIMESTAMP))

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
        self.host_address: HostAddress = None  # type: ignore[assignment]
        self.sequence = [0]
        self.context: Context = Context()
        self.exception_factory = ExceptionFactory()
        self.closed = False
        self.socket_timeout = configuration.socket_timeout
        self.connect_timeout = configuration.connect_timeout
        self.cert_fingerprint_validator: Optional[SSLFingerprintValidator] = None
        self.auth_plugin: Optional[AuthenticationPlugin] = None

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
        # None means caching disabled
        cache_size = configuration.prep_stmt_cache_size if configuration.cache_prep_stmts else 0
        if cache_size > 0 and LRUCache is not None:
            # Create LRU cache that calls evicted_from_cache on eviction
            class PreparedStatementLRUCache(LRUCache):
                def popitem(self) -> tuple[Any, Any]:
                    """Called when LRU evicts an item"""
                    key, value = super().popitem()
                    # Notify the statement it's been evicted
                    if hasattr(value, 'evicted_from_cache'):
                        value.evicted_from_cache()
                    return key, value

            self.prepared_statement_cache: Any = PreparedStatementLRUCache(maxsize=cache_size)
        else:
            self.prepared_statement_cache = None

    # =========================================================================
    # Write Stream Methods
    # =========================================================================

    def reset_sequence(self) -> None:
        """Reset packet sequence number"""
        self.sequence[0] = 0

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
        if self._uses_unix_socket():
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


    def _uses_unix_socket(self) -> bool:
        """True only if this connection actually runs over a unix socket.

        A unix_socket configured together with protocol='TCP' is ignored, the
        connection falls back to TCP (see _connect), so the bare config flag is
        not a reliable transport indicator for the security checks below.
        """
        return (bool(self.configuration.unix_socket)
                and self.configuration.protocol != PROTOCOL_TCP)


    def check_auth_switch_allowed(self, plugin_name: str, plugin_factory: Any, plugin: Any) -> None:
        """Gate a server-requested authentication plugin (auth switch) against two
        MitM risks, *before* the plugin transmits any credential.

        The plugin name on an authentication-switch request is fully
        server-controlled, so a hostile/MitM server can request any registered
        plugin. Two checks must pass first:

        1. A plugin that sends secrets in clear text (``require_ssl``) may only run
           over a secure transport (TLS or a local connection) never remote plain TCP.
        2. When the server's identity rests solely on self-signed-certificate
           fingerprint validation, only a MitM-proof plugin with a non-empty
           password may run. Otherwise a MitM could harvest the credential before
           the post-auth fingerprint check (validate_ssl_fingerprint) rejects the
           connection (e.g. caching_sha2_password sends the password in clear over
           TLS and is not MitM-proof).

        A local connection (unix socket or loopback) is treated as secure /
        MitM-proof, matching Connector/C (``is_local_connection`` in my_auth.c,
        which relaxes verification for loopback and unix-socket transports).
        """
        # 1. clear-text plugins require a secure transport (TLS or local)
        secure_transport = bool(self.configuration.ssl) or self.is_local_connection()
        if plugin_factory.require_ssl() and not secure_transport:
            raise OperationalError(
                f"Cannot use authentication plugin '{plugin_name}' over an insecure "
                "connection: a clear-text password plugin requires TLS or a local connection."
            )

        # 2. fingerprint-only connections require a MitM-proof plugin + password
        fingerprint_only = (
            self.cert_fingerprint_validator is not None
            and self.cert_fingerprint_validator.get_fingerprint()
            and not self.is_local_connection()
        )
        if fingerprint_only and (not plugin.is_mitm_proof() or not self.configuration.password):
            raise OperationalError(
                f"Cannot use authentication plugin '{plugin_name}' with self-signed "
                "certificates validated only by fingerprint. Either set "
                "ssl_verify_cert=True, use a password with a MitM-proof authentication "
                "plugin, or provide the server certificate to the client."
            )


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
        # The fingerprint pins the self-signed certificate at the INITIAL connect
        # A later re-authentication (change_user) runs over that same.
        if self.connected:
            return

        # Only validate if we have a fingerprint (self-signed cert scenario)
        if not self.cert_fingerprint_validator or not self.cert_fingerprint_validator.get_fingerprint():
            return

        # Always enforce the certificate validity period -- even on this
        # self-signed / fingerprint path, which runs over an unverified TLS
        # context that never checks the certificate dates. libmariadb checks the
        # period on every path (an expired certificate hard-fails there), so we do
        # the same, before the local-connection exemption, to be at least as
        # strict as the C connector.
        period_error = self.cert_fingerprint_validator.check_certificate_period()
        if period_error:
            raise OperationalError(f"TLS certificate validation failed: {period_error}.")

        # Skip the remaining (fingerprint-hash) validation for local and Unix
        # domain sockets (MitM-proof by design)
        if self.is_local_connection():
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

        if not self.configuration.password:
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
            self.context.auth_data,  # type: ignore[arg-type]
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
        if self.configuration.local_infile is not False:
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
        OkPacket.decode(packet, self.context)  # type: ignore[arg-type]

    def _apply_converters_to_rows(self, rows: List[tuple], columns: 'ColumnsDefinition', config: 'Configuration') -> List[tuple]:
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

        col_types = columns.types
        for i in range(num_cols):
            col_type = col_types[i]
            if converter_map and col_type in converter_map:
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

    def _parse_text_row_data(self, data: memoryview, columns: 'ColumnsDefinition', config: 'Configuration', num_cols: int) -> tuple:
        """Parse text protocol row data using parallel arrays from ColumnsDefinition.

        Uses columns.types[], columns.charsets[], columns.special_formats[] etc.
        directly from arrays — no per-column object attribute lookups.
        """
        row_values: list[Any] = [None] * num_cols
        pos = 0
        data_bytes = data.tobytes()  # Convert once for faster access

        # Local references to parallel arrays
        col_types = columns.types
        col_charsets = columns.charsets
        col_special_formats = columns.special_formats
        col_ext_type_formats = columns.ext_type_formats
        col_ext_type_names = columns.ext_type_names

        for i in range(num_cols):
            # Read length-encoded integer for field length
            length_byte = data_bytes[pos]
            if (length_byte < 0xFB):
                length = length_byte
                pos += 1
            elif (length_byte == 0xFB):
                pos += 1
                continue
            elif length_byte == 0xFC:
                length = _unpack_H(data_bytes, pos + 1)[0]
                pos += 3
            elif length_byte == 0xFD:
                length = _unpack_I(data_bytes, pos + 1)[0] & 0xFFFFFF
                pos += 4
            else:
                length = _unpack_Q(data_bytes, pos + 1)[0]
                pos += 9

            col_type = col_types[i]
            if col_type in _TEXT_INT_TYPES:
                row_values[i] = int(data_bytes[pos:pos + length])
            elif col_type in _TEXT_STRING_TYPES:
                val = data_bytes[pos:pos + length]
                if col_special_formats[i]:
                    ext_fmt = col_ext_type_formats[i]
                    if ext_fmt == b'json':
                        row_values[i] = val.decode('utf-8', errors='ignore')
                    else:
                        ext_name = col_ext_type_names[i]
                        if ext_name == b'inet6' or ext_name == b'inet4':
                            row_values[i] = val.decode('ascii')
                            if config.native_object:
                                row_values[i] = ipaddress.ip_address(row_values[i])
                        elif ext_name == b'uuid':
                            row_values[i] = val.decode('ascii')
                            if config.native_object:
                                row_values[i] = uuid.UUID(row_values[i])
                elif col_charsets[i] == 63:  # Binary charset
                    row_values[i] = val
                else:
                    row_values[i] = val.decode('utf-8', errors='ignore')
            elif col_type in _TEXT_FLOAT_TYPES:
                row_values[i] = float(data_bytes[pos:pos + length].decode('ascii'))
            elif col_type in _TEXT_DECIMAL_TYPES:
                row_values[i] = decimal.Decimal(data_bytes[pos:pos + length].decode('ascii'))
            elif col_type in _TEXT_DATE_TYPES:
                if length == 10:
                    try:
                        year_b, _, month_b, _, day_b = _unpack_DATE_TEXT(data_bytes, pos)
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
            elif col_type in _TEXT_DATETIME_TYPES:
                if length >= 19:
                    try:
                        year_b, _, month_b, _, day_b, _, hour_b, _, min_b, _, sec_b = _unpack_DATETIME_TEXT(data_bytes, pos)
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
                row_values[i] = data_bytes[pos:pos + length].decode('utf-8', errors='ignore')

            pos += length

        return tuple(row_values)

    def _parse_binary_row_data(self, data: memoryview, columns: 'ColumnsDefinition', config: 'Configuration', num_cols: int) -> tuple:
        """Parse binary protocol row data using parallel arrays from ColumnsDefinition.

        Uses columns.types[], columns.flags[], columns.charsets[] etc.
        directly from arrays — no per-column object attribute lookups.
        """
        pos = 1  # Skip 0x00 header
        # Read NULL bitmap
        null_bitmap_length = (num_cols + 9) >> 3
        null_bitmap = data[pos:pos + null_bitmap_length]
        pos += null_bitmap_length

        # Local references to parallel arrays
        col_types = columns.types
        col_flags = columns.flags
        col_charsets = columns.charsets
        col_special_formats = columns.special_formats
        col_ext_type_formats = columns.ext_type_formats
        col_ext_type_names = columns.ext_type_names
        _UNSIGNED = FIELD_FLAG.UNSIGNED

        # Parse column values with inlined decoding
        row_values: list[Any] = [None] * num_cols

        for i in range(num_cols):
            if null_bitmap[(i + 2) >> 3] & (1 << ((i + 2) & 7)):
                continue

            # Decode based on field type
            field_type = col_types[i]
            if field_type in _BIN_INT32_TYPES:
                if (col_flags[i] & _UNSIGNED) != 0:
                    row_values[i] = _unpack_I(data, pos)[0]
                else:
                    row_values[i] = _unpack_i(data, pos)[0]
                pos += 4
            elif field_type == FIELD_TYPE.LONGLONG:
                if (col_flags[i] & _UNSIGNED) != 0:
                    row_values[i] = _unpack_Q(data, pos)[0]
                else:
                    row_values[i] = _unpack_q(data, pos)[0]
                pos += 8
            elif field_type in _BIN_STRING_TYPES:
                # String types (VARCHAR, TEXT, BLOB, JSON, etc.) - length-encoded
                length = data[pos]

                if (length < 0xFB):
                    pos += 1
                elif length == 0xFC:
                    length = _unpack_H(data, pos + 1)[0]
                    pos += 3
                elif length == 0xFD:
                    length = _unpack_I(data, pos + 1)[0] & 0xFFFFFF
                    pos += 4
                else:  # 0xFE
                    length = _unpack_Q(data, pos + 1)[0]
                    pos += 9

                val = bytes(data[pos:pos + length])
                if col_special_formats[i]:
                    if col_ext_type_formats[i] == b'json':
                        row_values[i] = val.decode('utf-8')
                    elif col_ext_type_names[i] == b'inet6' or col_ext_type_names[i] == b'inet4':
                        row_values[i] = val.decode('ascii')
                        if config.native_object:
                            row_values[i] = ipaddress.ip_address(row_values[i])
                    elif col_ext_type_names[i] == b'uuid':
                        row_values[i] = val.decode('ascii')
                        if config.native_object:
                            row_values[i] = uuid.UUID(row_values[i])
                elif field_type != FIELD_TYPE.JSON and col_charsets[i] == 63:  # Binary charset
                    row_values[i] = val
                else:
                    row_values[i] = val.decode('utf-8', errors='ignore')
                pos += length

            elif field_type == FIELD_TYPE.TINY:
                if (col_flags[i] & _UNSIGNED) != 0:
                    row_values[i] = data[pos]
                else:
                    row_values[i] = _unpack_b(data, pos)[0]
                pos += 1
            elif field_type in _BIN_SHORT_TYPES:
                if (col_flags[i] & _UNSIGNED) != 0:
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
            elif field_type in _BIN_DECIMAL_TYPES:
                # Decimal as length-encoded string
                length = data[pos]
                pos += 1
                if length > 0:
                    row_values[i] = decimal.Decimal(data[pos:pos + length].tobytes().decode('ascii'))
                    pos += length
                else:
                    row_values[i] = decimal.Decimal('0')
            elif field_type in _BIN_DATE_TYPES:
                length_byte = data[pos]
                pos += 1
                if length_byte >= 4:
                    year, month, day = _unpack_HBB(data, pos)
                    try:
                        row_values[i] = datetime.date(year, month, day)
                    except ValueError:
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
            elif field_type in _BIN_DATETIME_TYPES:
                length_byte = data[pos]
                pos += 1
                if length_byte == 11:
                    # Datetime with microseconds
                    year, month, day, hours, minutes, seconds, microseconds = _unpack_HBBBBBI(data, pos)
                    pos += 11
                    try:
                        row_values[i] = datetime.datetime(year, month, day, hours, minutes, seconds, microseconds)
                    except ValueError:
                        row_values[i] = None
                elif length_byte == 7:
                    # Datetime without microseconds
                    year, month, day, hours, minutes, seconds = _unpack_HBBBBB(data, pos)
                    pos += 7
                    try:
                        row_values[i] = datetime.datetime(year, month, day, hours, minutes, seconds, 0)
                    except ValueError:
                        row_values[i] = None
                elif length_byte == 4:
                    # Date only
                    year, month, day = _unpack_HBB(data, pos)
                    pos += 4
                    try:
                        row_values[i] = datetime.datetime(year, month, day, 0, 0, 0, 0)
                    except ValueError:
                        row_values[i] = None
                else:
                    row_values[i] = None

        return tuple(row_values)


