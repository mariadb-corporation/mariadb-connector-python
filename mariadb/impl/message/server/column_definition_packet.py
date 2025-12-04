# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Column Definition Packet parser for MariaDB protocol

Based on MySQL/MariaDB protocol column definition structure.
"""

import struct
from typing import TYPE_CHECKING, Optional, Tuple

if TYPE_CHECKING:
    from ...client.context import Context

# Pre-compile struct formats for faster unpacking
_STRUCT_UINT16 = struct.Struct('<H')
_STRUCT_FIXED_FIELDS = struct.Struct('<HIBHB')  # charset(H), column_length(I), type(B), flags(H), decimals(B)

def read_qualified_identifiers(data: memoryview, pos: int) -> tuple:
    """
    Reads the 6 qualified length endoded identifiers from metadata.

    Returns a tuple of 6 qualified identifiers and as last sequence member read position.
    Note: An empty qualifier is represented as None.
    """

    _unpack16 = _STRUCT_UINT16.unpack_from
    out0 = out1 = out2 = out3 = out4 = out5 = None

    for _idx in range(6):
        length = data[pos]
        pos += 1

        if length >= 251:
            length = _unpack16(data, pos)[0]
            pos += 2
        if length > 0:
           chunk= data[pos:pos+length].tobytes()
        pos += length

        if length > 0:
            if _idx == 0: out0 = chunk
            elif _idx == 1: out1 = chunk
            elif _idx == 2: out2 = chunk
            elif _idx == 3: out3 = chunk
            elif _idx == 4: out4 = chunk
            elif _idx == 5: out5 = chunk

    return out0, out1, out2, out3, out4, out5, pos


def read_small_length_encoded_bytes(data: memoryview, pos: int) -> Tuple[bytes, int]:
    """Read length-encoded bytes and advance position"""
    length = data[pos]
    pos += 1
    
    # Fast path: most lengths are < 251
    if length < 251:
        result = bytes(data[pos:pos+length])
        return result, pos + length
    
    # Slow path: 2-byte length
    length = _STRUCT_UINT16.unpack_from(data, pos)[0]
    pos += 2
    result = bytes(data[pos:pos+length])
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
        return (self._catalog_bytes or b'').decode('utf-8', errors='replace')

    @property
    def schema(self) -> str:
        """Lazily decode schema name"""
        return (self._schema_bytes or b'').decode('utf-8', errors='replace')

    @property
    def table(self) -> str:
        """Lazily decode table name"""
        return (self._table_bytes or b'').decode('utf-8', errors='replace')

    @property
    def org_table(self) -> str:
        """Lazily decode original table name"""
        return (self._org_table_bytes or b'').decode('utf-8', errors='replace')

    @property
    def name(self) -> str:
        """Lazily decode column name"""
        return (self._name_bytes or b'').decode('utf-8', errors='replace')

    @property
    def org_name(self) -> str:
        """Lazily decode original column name"""
        return (self._org_name_bytes or b'').decode('utf-8', errors='replace')

    @staticmethod
    def decode(data: memoryview, context: 'Context') -> 'ColumnDefinitionPacket':
        """Decode column definition packet"""

        pos = 0

        # qualified identifiers will be stored as bytes or None - if application
        # calls cursor.description we will do lazy encoding
        (catalog_bytes,
         schema_bytes,
         table_bytes,
         org_table_bytes,
         name_bytes,
         org_name_bytes, pos) = read_qualified_identifiers(data, pos)

        # Fast path: no extended metadata (most common case)
        ext_type_name = None
        ext_type_format = None
        special_format = False

        if context.hasExtendedMetadata():
            ext_length = data[pos]
            pos += 1

            if ext_length > 0:
                special_format = True
                ext_end = pos + ext_length

                while pos < ext_end:
                    ext_type = data[pos]
                    pos += 1

                    if ext_type == 0:
                        ext_type_name, pos = read_small_length_encoded_bytes(data, pos)
                    elif ext_type == 1:
                        ext_type_format, pos = read_small_length_encoded_bytes(data, pos)
                    else:
                        # Skip unknown extended data
                        _, pos = read_small_length_encoded_bytes(data, pos)

        # Skip length field (0x0C) and unpack fixed fields using pre-compiled struct
        pos += 1
        charset, column_length, type, flags, decimals = _STRUCT_FIXED_FIELDS.unpack_from(data, pos)

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

