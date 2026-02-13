# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Column Definition parser for MariaDB protocol (CONPY-335).

Stores all column metadata as parallel arrays (object-of-arrays) for
cache-friendly access during row parsing. No per-column objects are created.
"""

import struct
from typing import TYPE_CHECKING, Optional, Tuple, List

if TYPE_CHECKING:
    from ...client.context import Context

_UNPACK_UINT16 = struct.Struct('<H').unpack_from
_UNPACK_FIXED_FIELDS = struct.Struct('<HIBHB').unpack_from  # charset(H), column_length(I), type(B), flags(H), decimals(B)


def _read_length_encoded_int(data, pos):
    """Read a length-encoded integer, return (value, new_pos)."""
    b = data[pos]
    if b < 251:
        return b, pos + 1
    if b == 0xFC:
        return _UNPACK_UINT16(data, pos + 1)[0], pos + 3
    if b == 0xFD:
        return struct.unpack('<I', bytes(data[pos + 1:pos + 4]) + b'\x00')[0], pos + 4
    # 0xFE
    return struct.Struct('<Q').unpack_from(data, pos + 1)[0], pos + 9


def _read_small_length_encoded_bytes(data, pos):
    """Read length-encoded bytes, return (bytes, new_pos)."""
    length = data[pos]
    pos += 1
    if length < 251:
        return bytes(data[pos:pos + length]), pos + length
    length = _UNPACK_UINT16(data, pos)[0]
    pos += 2
    return bytes(data[pos:pos + length]), pos + length


class ColumnsDefinition:
    """
    Object-of-arrays representation of column metadata (CONPY-335).

    Decodes column definition packets directly into parallel arrays.
    No intermediate per-column objects are created.

    Hot-path arrays (indexed by column number in row parsers):
        types, flags, charsets, special_formats, ext_type_names, ext_type_formats

    Cold-path arrays (decoded lazily for cursor.description / _build_metadata):
        _data_blobs, _sch_ranges, _tbl_ranges, _org_tbl_ranges,
        _name_ranges, _org_name_ranges, column_lengths, decimals_arr
    """
    __slots__ = (
        'count',
        # Hot-path: numeric arrays for row parsing
        'types',
        'flags',
        'charsets',
        'special_formats',
        'ext_type_names',
        'ext_type_formats',
        # Cold-path: single list for metadata / description
        '_meta',             # list[tuple] per column: (data_blob, sch_b, sch_e, tbl_b, tbl_e, org_tbl_b, org_tbl_e, name_b, name_e, org_name_b, org_name_e)
        'column_lengths',
        'decimals_arr',
    )

    def __init__(self, count: int):
        self.count = count
        _zero = [0] * count
        self.types = _zero[:]
        self.flags = _zero[:]
        self.charsets = _zero[:]
        self.special_formats = _zero[:]
        self.column_lengths = _zero[:]
        self.decimals_arr = _zero  # last use — no copy needed
        self.ext_type_names = [None] * count
        self.ext_type_formats = [None] * count
        self._meta = [None] * count

    def decode_column(self, index: int, data: memoryview, context: 'Context') -> None:
        """Decode a single column definition packet directly into parallel arrays."""
        pos = 0
        start_pos = 0

        # ---- Read 6 length-encoded string identifiers ----
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

        # Save raw identifier bytes + all ranges as a single tuple
        self._meta[index] = (
            data[start_pos:pos].tobytes(),
            sch_begin, sch_end,
            tbl_begin, tbl_end,
            org_tbl_begin, org_tbl_end,
            name_begin, name_end,
            org_name_begin, org_name_end,
        )

        # ---- Extended metadata ----
        ext_type_name = None
        ext_type_format = None
        special_format = 0

        if context.hasExtendedMetadata():
            ext_length = data[pos]; pos += 1
            if ext_length > 0:
                special_format = 1
                ext_end = pos + ext_length
                while pos < ext_end:
                    ext_type = data[pos]; pos += 1
                    if ext_type == 0:
                        ext_type_name, pos = _read_small_length_encoded_bytes(data, pos)
                    elif ext_type == 1:
                        ext_type_format, pos = _read_small_length_encoded_bytes(data, pos)
                    else:
                        _, pos = _read_small_length_encoded_bytes(data, pos)

        # ---- Fixed fields ----
        pos += 1  # skip 0x0C length byte
        charset, column_length, col_type, col_flags, col_decimals = _UNPACK_FIXED_FIELDS(data, pos)

        # ---- Store into pre-allocated arrays by index ----
        self.types[index] = col_type
        self.flags[index] = col_flags
        self.charsets[index] = charset
        self.special_formats[index] = special_format
        self.ext_type_names[index] = ext_type_name
        self.ext_type_formats[index] = ext_type_format
        self.column_lengths[index] = column_length
        self.decimals_arr[index] = col_decimals

    # =========================================================================
    # String accessors (lazy decode — cold path only)
    # =========================================================================

    def _decode_str(self, i: int, begin_idx: int) -> str:
        m = self._meta[i]
        b = m[begin_idx]
        e = m[begin_idx + 1]
        if e > b:
            return m[0][b:e].decode('utf-8', errors='replace')
        return ''

    def get_name(self, i: int) -> str:
        return self._decode_str(i, 7)  # name_begin, name_end

    def get_org_name(self, i: int) -> str:
        return self._decode_str(i, 9)  # org_name_begin, org_name_end

    def get_schema(self, i: int) -> str:
        return self._decode_str(i, 1)  # sch_begin, sch_end

    def get_table(self, i: int) -> str:
        return self._decode_str(i, 3)  # tbl_begin, tbl_end

    def get_org_table(self, i: int) -> str:
        return self._decode_str(i, 5)  # org_tbl_begin, org_tbl_end

    def get_catalog(self, i: int) -> str:
        return 'def'

    # =========================================================================
    # Protocol helpers
    # =========================================================================

    def __len__(self):
        return self.count

    @staticmethod
    def decode_all(packets, buf_mv, count: int, context: 'Context') -> 'ColumnsDefinition':
        """Decode a list of (start, end) packet positions into a ColumnsDefinition.

        Args:
            packets: list of (start, end) tuples into buf_mv
            buf_mv: memoryview of the receive buffer
            count: number of columns
            context: connection context
        """
        cols = ColumnsDefinition(count)
        for i in range(count):
            start, end = packets[i]
            cols.decode_column(i, buf_mv[start:end], context)
        return cols

