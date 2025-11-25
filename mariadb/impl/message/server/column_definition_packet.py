# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Column Definition Packet parser for MariaDB protocol

Based on MySQL/MariaDB protocol column definition structure.
"""

import struct
from typing import TYPE_CHECKING, Optional, Tuple
# No longer need PacketBuffer import
if TYPE_CHECKING:
    from ...client.context import Context


def read_small_length_encoded_bytes(data: memoryview, pos: int) -> Tuple[bytes, int]:
    """Read length-encoded bytes and advance position"""
    length = data[pos]
    pos += 1
    
    if length >= 251:
        length = struct.unpack('<H', data[pos:pos+2])[0]
        pos += 2

    result = data[pos:pos+length].tobytes()
    return result, pos + length


class ColumnDefinitionPacket:
    """
    Column Definition Packet from MariaDB server
    
    Structure:
    - length-encoded string: catalog
    - length-encoded string: schema
    - length-encoded string: table
    - length-encoded string: org_table (original table name)
    - length-encoded string: name (column name)
    - length-encoded string: org_name (original column name)
    - [optional] extended metadata (if EXTENDED_METADATA capability enabled)
    - 1 byte: length of fixed fields (always 0x0C = 12)
    - 2 bytes: character_set (little-endian)
    - 4 bytes: column_length (little-endian)
    - 1 byte: type (field type)
    - 2 bytes: flags (little-endian)
    - 1 byte: decimals
    - 2 bytes: reserved (0x00 0x00)
    """
    __slots__ = (
        '_catalog_bytes',
        '_schema_bytes',
        '_table_bytes',
        '_org_table_bytes',
        '_name_bytes',
        '_org_name_bytes',
        'character_set',
        'column_length',
        'type',
        'flags',
        'decimals',
        'special_format',
        'ext_type_name',
        'ext_type_format',
    )
    def __init__(
        self,
        catalog_bytes: bytes,
        schema_bytes: bytes,
        table_bytes: bytes,
        org_table_bytes: bytes,
        name_bytes: bytes,
        org_name_bytes: bytes,
        character_set: int,
        column_length: int,
        type: int,
        flags: int,
        decimals: int,
        special_format: bool,
        ext_type_name: Optional[bytes] = None,
        ext_type_format: Optional[bytes] = None
    ):
        """Initialize column definition with metadata fields (strings stored as bytes)"""
        self._catalog_bytes = catalog_bytes
        self._schema_bytes = schema_bytes
        self._table_bytes = table_bytes
        self._org_table_bytes = org_table_bytes
        self._name_bytes = name_bytes
        self._org_name_bytes = org_name_bytes
        self.character_set = character_set
        self.column_length = column_length
        self.type = type
        self.flags = flags
        self.decimals = decimals
        self.special_format = special_format
        self.ext_type_name = ext_type_name
        self.ext_type_format = ext_type_format
    
    @property
    def catalog(self) -> str:
        """Lazily decode catalog name"""
        return self._catalog_bytes.decode('utf-8', errors='replace')
    
    @property
    def schema(self) -> str:
        """Lazily decode schema name"""
        return self._schema_bytes.decode('utf-8', errors='replace')
    
    @property
    def table(self) -> str:
        """Lazily decode table name"""
        return self._table_bytes.decode('utf-8', errors='replace')
    
    @property
    def org_table(self) -> str:
        """Lazily decode original table name"""
        return self._org_table_bytes.decode('utf-8', errors='replace')
    
    @property
    def name(self) -> str:
        """Lazily decode column name"""
        return self._name_bytes.decode('utf-8', errors='replace')
    
    @property
    def org_name(self) -> str:
        """Lazily decode original column name"""
        return self._org_name_bytes.decode('utf-8', errors='replace')
    
    @staticmethod
    def decode(data: memoryview, context: 'Context') -> 'ColumnDefinitionPacket':
        """Decode column definition packet from bytearray with context"""
        
        pos = 0
        
        catalog_bytes, pos = read_small_length_encoded_bytes(data, pos)
        schema_bytes, pos = read_small_length_encoded_bytes(data, pos)
        table_bytes, pos = read_small_length_encoded_bytes(data, pos)
        org_table_bytes, pos = read_small_length_encoded_bytes(data, pos)
        name_bytes, pos = read_small_length_encoded_bytes(data, pos)
        org_name_bytes, pos = read_small_length_encoded_bytes(data, pos)
        
        # Handle extended info only if EXTENDED_METADATA capability is enabled
        ext_type_name = None
        ext_type_format = None
        special_format = False

        # Check if we have the length field (0x0C) or extended metadata
        if context.hasExtendedMetadata():
            # Has extended info - read length-encoded buffer
            ext_length = data[pos]
            pos += 1
            ext_end = pos + ext_length
            while pos < ext_end and pos < len(data):
                ext_type = data[pos]
                pos += 1
                special_format = True
                if ext_type == 0:
                    # Extended type name
                    ext_type_name, pos = read_small_length_encoded_bytes(data, pos)
                elif ext_type == 1:
                    # Extended type format
                    ext_type_format, pos = read_small_length_encoded_bytes(data, pos)
                else:
                    # Skip unknown extended data
                    _, pos = read_small_length_encoded_bytes(data, pos)
        
        # Skip length field (always 0x0C = 12 for fixed fields)
        pos += 1
        charset, column_length, type, flags, decimals = struct.unpack('<HIBHB', data[pos:pos+10])

        return ColumnDefinitionPacket(
            catalog_bytes,
            schema_bytes,
            table_bytes,
            org_table_bytes,
            name_bytes,
            org_name_bytes,
            charset,
            column_length,
            type,
            flags,
            decimals,
            special_format,
            ext_type_name,
            ext_type_format
        )
    