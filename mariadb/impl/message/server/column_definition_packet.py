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

_UNPACK_UINT16 = struct.Struct('<H').unpack_from
_UNPACK_FIXED_FIELDS = struct.Struct('<HIBHB').unpack_from  # charset(H), column_length(I), type(B), flags(H), decimals(B)

def read_qualified_identifiers(data: memoryview, pos: int) -> tuple:
    """
    Reads the 6 qualified length encoded identifiers from metadata.

    Returns: (data_bytes, pos, out0_begin, out0_end, out1_begin, out1_end, ...)
    Creates a single bytes object and returns position offsets for each field.
    """

    start_pos = pos
    
    # Field 0 (catalog): Skip, will use hardcoded "def"
    length = data[pos]
    pos += 1
    out0_begin = out0_end = 0
    pos += length

    # Field 1 (schema)
    length = data[pos]
    pos += 1
    if length > 0:
        if length >= 251:
            length = _UNPACK_UINT16(data, pos)[0]
            pos += 2
        out1_begin = pos - start_pos
        out1_end = out1_begin + length
        pos += length
    else:
        out1_begin = out1_end = 0

    # Field 2 (table)
    length = data[pos]
    pos += 1
    if length > 0:
        if length >= 251:
            length = _UNPACK_UINT16(data, pos)[0]
            pos += 2
        out2_begin = pos - start_pos
        out2_end = out2_begin + length
        pos += length
    else:
        out2_begin = out2_end = 0

    # Field 3 (org_table)
    length = data[pos]
    pos += 1
    if length > 0:
        if length >= 251:
            length = _UNPACK_UINT16(data, pos)[0]
            pos += 2
        out3_begin = pos - start_pos
        out3_end = out3_begin + length
        pos += length
    else:
        out3_begin = out3_end = 0

    # Field 4 (name)
    length = data[pos]
    pos += 1
    if length > 0:
        if length >= 251:
            length = _UNPACK_UINT16(data, pos)[0]
            pos += 2
        out4_begin = pos - start_pos
        out4_end = out4_begin + length
        pos += length
    else:
        out4_begin = out4_end = 0

    # Field 5 (org_name)
    length = data[pos]
    pos += 1
    if length > 0:
        if length >= 251:
            length = _UNPACK_UINT16(data, pos)[0]
            pos += 2
        out5_begin = pos - start_pos
        out5_end = out5_begin + length
        pos += length
    else:
        out5_begin = out5_end = 0
    
    # Create single bytes object from start to current position
    data_bytes = data[start_pos:pos].tobytes()
    
    return (data_bytes, pos, 
            out0_begin, out0_end,
            out1_begin, out1_end,
            out2_begin, out2_end,
            out3_begin, out3_end,
            out4_begin, out4_end,
            out5_begin, out5_end)


def read_small_length_encoded_bytes(data: memoryview, pos: int) -> Tuple[bytes, int]:
    """Read length-encoded bytes and advance position"""
    length = data[pos]
    pos += 1
    
    # Fast path: most lengths are < 251
    if length < 251:
        result = bytes(data[pos:pos+length])
        return result, pos + length
    
    # Slow path: 2-byte length
    length = _UNPACK_UINT16(data, pos)[0]
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
        '_data_bytes',
        '_sch_begin', '_sch_end',
        '_tbl_begin', '_tbl_end',
        '_org_tbl_begin', '_org_tbl_end',
        '_name_begin', '_name_end',
        '_org_name_begin', '_org_name_end',
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
        data_bytes: bytes,
        sch_begin: int, sch_end: int,
        tbl_begin: int, tbl_end: int,
        org_tbl_begin: int, org_tbl_end: int,
        name_begin: int, name_end: int,
        org_name_begin: int, org_name_end: int,
        character_set: int,
        column_length: int,
        type: int,
        flags: int,
        decimals: int,
        special_format: bool,
        ext_type_name: Optional[bytes] = None,
        ext_type_format: Optional[bytes] = None
    ):
        """Initialize column definition with single bytes object and field positions"""
        self._data_bytes = data_bytes
        self._sch_begin = sch_begin
        self._sch_end = sch_end
        self._tbl_begin = tbl_begin
        self._tbl_end = tbl_end
        self._org_tbl_begin = org_tbl_begin
        self._org_tbl_end = org_tbl_end
        self._name_begin = name_begin
        self._name_end = name_end
        self._org_name_begin = org_name_begin
        self._org_name_end = org_name_end
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
        return 'def'  # Hardcoded catalog

    @property
    def schema(self) -> str:
        """Lazily decode schema name from positions"""
        if self._sch_end > self._sch_begin:
            return self._data_bytes[self._sch_begin:self._sch_end].decode('utf-8', errors='replace')
        return ''

    @property
    def table(self) -> str:
        """Lazily decode table name from positions"""
        if self._tbl_end > self._tbl_begin:
            return self._data_bytes[self._tbl_begin:self._tbl_end].decode('utf-8', errors='replace')
        return ''

    @property
    def org_table(self) -> str:
        """Lazily decode original table name from positions"""
        if self._org_tbl_end > self._org_tbl_begin:
            return self._data_bytes[self._org_tbl_begin:self._org_tbl_end].decode('utf-8', errors='replace')
        return ''

    @property
    def name(self) -> str:
        """Lazily decode column name from positions"""
        if self._name_end > self._name_begin:
            return self._data_bytes[self._name_begin:self._name_end].decode('utf-8', errors='replace')
        return ''

    @property
    def org_name(self) -> str:
        """Lazily decode original column name from positions"""
        if self._org_name_end > self._org_name_begin:
            return self._data_bytes[self._org_name_begin:self._org_name_end].decode('utf-8', errors='replace')
        return ''

    @staticmethod
    def decode(data: memoryview, context: 'Context') -> 'ColumnDefinitionPacket':
        """Decode column definition packet"""

        pos = 0
        start_pos = 0

        # Field 0 (catalog): skip
        length = data[pos]; pos += 1; pos += length

        # Field 1 (schema)
        length = data[pos]; pos += 1
        if length > 0:
            if length >= 251:
                length = _UNPACK_UINT16(data, pos)[0]; pos += 2
            sch_begin = pos - start_pos; sch_end = sch_begin + length; pos += length
        else:
            sch_begin = sch_end = 0

        # Field 2 (table)
        length = data[pos]; pos += 1
        if length > 0:
            if length >= 251:
                length = _UNPACK_UINT16(data, pos)[0]; pos += 2
            tbl_begin = pos - start_pos; tbl_end = tbl_begin + length; pos += length
        else:
            tbl_begin = tbl_end = 0

        # Field 3 (org_table)
        length = data[pos]; pos += 1
        if length > 0:
            if length >= 251:
                length = _UNPACK_UINT16(data, pos)[0]; pos += 2
            org_tbl_begin = pos - start_pos; org_tbl_end = org_tbl_begin + length; pos += length
        else:
            org_tbl_begin = org_tbl_end = 0

        # Field 4 (name)
        length = data[pos]; pos += 1
        if length > 0:
            if length >= 251:
                length = _UNPACK_UINT16(data, pos)[0]; pos += 2
            name_begin = pos - start_pos; name_end = name_begin + length; pos += length
        else:
            name_begin = name_end = 0

        # Field 5 (org_name)
        length = data[pos]; pos += 1
        if length > 0:
            if length >= 251:
                length = _UNPACK_UINT16(data, pos)[0]; pos += 2
            org_name_begin = pos - start_pos; org_name_end = org_name_begin + length; pos += length
        else:
            org_name_begin = org_name_end = 0

        # Single bytes copy for all identifier data
        data_bytes = data[start_pos:pos].tobytes()

        # ---- Extended metadata ----
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
                        _, pos = read_small_length_encoded_bytes(data, pos)

        pos += 1
        charset, column_length, col_type, col_flags, col_decimals = _UNPACK_FIXED_FIELDS(data, pos)

        return ColumnDefinitionPacket(
            data_bytes,
            sch_begin, sch_end,
            tbl_begin, tbl_end,
            org_tbl_begin, org_tbl_end,
            name_begin, name_end,
            org_name_begin, org_name_end,
            charset,
            column_length,
            col_type,
            col_flags,
            col_decimals,
            special_format,
            ext_type_name,
            ext_type_format
        )

