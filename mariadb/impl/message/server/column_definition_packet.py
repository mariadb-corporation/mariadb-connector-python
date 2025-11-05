# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Column Definition Packet parser for MariaDB protocol

Based on MySQL/MariaDB protocol column definition structure.
"""

import struct
from typing import TYPE_CHECKING, Optional
from ...client.socket.payload_parser import PayloadParser

if TYPE_CHECKING:
    from ...client.context import Context


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
    - 1 byte: column_type (field type)
    - 2 bytes: flags (little-endian)
    - 1 byte: decimals
    - 2 bytes: reserved (0x00 0x00)
    """
    
    def __init__(
        self,
        catalog: str,
        schema: str,
        table: str,
        org_table: str,
        name: str,
        org_name: str,
        character_set: int,
        column_length: int,
        column_type: int,
        flags: int,
        decimals: int,
        ext_type_name: Optional[str] = None,
        ext_type_format: Optional[str] = None
    ):
        """Initialize column definition with metadata fields"""
        self.catalog = catalog
        self.schema = schema
        self.table = table
        self.org_table = org_table
        self.name = name
        self.org_name = org_name
        self.character_set = character_set
        self.column_length = column_length
        self.column_type = column_type
        self.flags = flags
        self.decimals = decimals
        self.ext_type_name = ext_type_name
        self.ext_type_format = ext_type_format
    
    @staticmethod
    def decode(data: bytearray, context: 'Context') -> 'ColumnDefinitionPacket':
        """Decode column definition packet from bytearray with context"""
        parser = PayloadParser(data)
        
        # Read the 6 identifiers as per Java implementation
        catalog = parser.read_length_encoded_string()
        schema = parser.read_length_encoded_string()
        table = parser.read_length_encoded_string()
        org_table = parser.read_length_encoded_string()
        name = parser.read_length_encoded_string()
        org_name = parser.read_length_encoded_string()
        
        # Handle extended info only if EXTENDED_METADATA capability is enabled
        ext_type_name = None
        ext_type_format = None
        
        # Check if we have the length field (0x0C) or extended metadata
        if context.hasExtendedMetadata() and parser.has_remaining():
            next_byte = parser.packet[parser.pos]
            if next_byte != 0x0C and next_byte != 0:
                # Has extended info - read length-encoded buffer
                ext_length = parser.read_length_encoded_int()
                ext_end = parser.pos + ext_length
                
                while parser.pos < ext_end and parser.has_remaining():
                    ext_type = parser.read_byte()
                    
                    if ext_type == 0:
                        # Extended type name
                        ext_type_name = parser.read_length_encoded_string()
                    elif ext_type == 1:
                        # Extended type format
                        ext_type_format = parser.read_length_encoded_string()
                    else:
                        # Skip unknown extended data
                        skip_length = parser.read_length_encoded_int()
                        parser.skip(skip_length)
            elif next_byte == 0:
                # Skip the 0 byte
                parser.skip(1)
        
        # Skip length field (always 0x0C = 12)
        parser.skip(1)
        
        # Read fixed-length fields (10 bytes total)
        if parser.remaining_bytes() >= 10:
            # Unpack all fixed fields: charset(2), column_length(4), column_type(1), flags(2), decimals(1)
            fixed_data = parser.read_bytes(10)
            charset, column_length, column_type, flags, decimals = struct.unpack('<HIBHB', fixed_data)
        else:
            raise IOError("Column definition packet too short")
        
        return ColumnDefinitionPacket(
            catalog=catalog,
            schema=schema,
            table=table,
            org_table=org_table,
            name=name,
            org_name=org_name,
            character_set=charset,
            column_length=column_length,
            column_type=column_type,
            flags=flags,
            decimals=decimals,
            ext_type_name=ext_type_name,
            ext_type_format=ext_type_format
        )
    
    def to_dict(self) -> dict:
        """
        Convert to dictionary format (for backward compatibility)
        
        Returns:
            Dictionary with column information
        """
        return {
            'catalog': self.catalog,
            'schema': self.schema,
            'table': self.table,
            'org_table': self.org_table,
            'name': self.name,
            'org_name': self.org_name,
            'character_set': self.character_set,
            'column_length': self.column_length,
            'column_type': self.column_type,
            'flags': self.flags,
            'decimals': self.decimals,
            'ext_type_name': self.ext_type_name,
            'ext_type_format': self.ext_type_format
        }
    
    def __repr__(self) -> str:
        return (f"ColumnDefinitionPacket(name='{self.name}', "
                f"table='{self.table}', "
                f"type={self.column_type}, "
                f"length={self.column_length}, "
                f"flags=0x{self.flags:04X})")
    
    def __str__(self) -> str:
        type_name = self.ext_type_name or f"type_{self.column_type}"
        return f"{self.table}.{self.name} ({type_name})"
