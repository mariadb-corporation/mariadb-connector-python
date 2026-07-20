# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Column Definition parser for MariaDB protocol (CONPY-335).

Stores all column metadata as parallel arrays (object-of-arrays) for
cache-friendly access during row parsing. No per-column objects are created.
"""

import struct
from typing import TYPE_CHECKING, Any, List

if TYPE_CHECKING:
    from ...client.context import Context

_UNPACK_UINT16 = struct.Struct('<H').unpack_from
_UNPACK_FIXED_FIELDS = struct.Struct('<HIBHB').unpack_from  # charset(H), column_length(I), type(B), flags(H), decimals(B)


def _read_small_length_encoded_bytes(data: memoryview, pos: int) -> tuple[bytes, int]:
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
        self.ext_type_names: List[bytes | None] = [None] * count
        self.ext_type_formats: List[bytes | None] = [None] * count
        # Per column: raw identifier bytes (schema..org_name), lazily replaced by
        # the split list[bytes] of the 5 identifiers on first get_*() access.
        self._meta: List[Any] = [None] * count

    def decode_column(self, index: int, data: memoryview, context: 'Context') -> None:
        """Decode a single column definition packet directly into parallel arrays.

        Only the hot-path fixed fields (type/flags/charset/length/decimals) are
        parsed eagerly. The string identifiers (schema/table/org_table/name/
        org_name) are kept as a single raw byte copy in ``_meta`` and decoded
        lazily by the ``get_*`` accessors, because most queries fetch rows
        without ever reading ``cursor.description``.
        """
        pos = 0

        # ---- Skip the 6 length-encoded string identifiers ----
        # Field 0 (catalog): always the constant "def", never surfaced.
        length = data[pos]; pos += 1; pos += length
        # Fields 1..5 (schema, table, org_table, name, org_name): keep the raw
        # region and defer per-field parsing to the get_*() accessors. Unrolled
        # (no range() iterator) since this runs once per column of every result.
        id_start = pos
        length = data[pos]; pos += 1
        if length >= 251:
            length = _UNPACK_UINT16(data, pos)[0]; pos += 2
        pos += length
        length = data[pos]; pos += 1
        if length >= 251:
            length = _UNPACK_UINT16(data, pos)[0]; pos += 2
        pos += length
        length = data[pos]; pos += 1
        if length >= 251:
            length = _UNPACK_UINT16(data, pos)[0]; pos += 2
        pos += length
        length = data[pos]; pos += 1
        if length >= 251:
            length = _UNPACK_UINT16(data, pos)[0]; pos += 2
        pos += length
        length = data[pos]; pos += 1
        if length >= 251:
            length = _UNPACK_UINT16(data, pos)[0]; pos += 2
        pos += length
        self._meta[index] = data[id_start:pos].tobytes()

        # ---- Extended metadata ----
        ext_type_name = None
        ext_type_format = None
        special_format = 0

        if context.extended_metadata:
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
        self.column_lengths[index] = column_length
        self.decimals_arr[index] = col_decimals
        # special_formats/ext_type_* are pre-filled with 0/None in __init__, so
        # only the rare extended-metadata columns need to overwrite them.
        if special_format:
            self.special_formats[index] = special_format
            self.ext_type_names[index] = ext_type_name
            self.ext_type_formats[index] = ext_type_format

    # =========================================================================
    # String accessors (lazy decode — cold path only)
    # =========================================================================

    def _fields(self, i: int) -> List[bytes]:
        """Lazily split the stored identifier region into its 5 fields
        (schema, table, org_table, name, org_name), caching the result so a
        full cursor.description read parses each column only once."""
        m = self._meta[i]
        if type(m) is bytes:
            pos = 0
            fields: List[bytes] = []
            for _ in range(5):
                length = m[pos]; pos += 1
                if length >= 251:
                    length = _UNPACK_UINT16(m, pos)[0]; pos += 2
                fields.append(m[pos:pos + length]); pos += length
            self._meta[i] = fields
            return fields
        # m is already the cached list[bytes] from a previous call
        return m  # type: ignore[no-any-return]

    def _decode_str(self, i: int, field_idx: int) -> str:
        raw = self._fields(i)[field_idx]
        if raw:
            return raw.decode('utf-8', errors='replace')
        return ''

    def get_schema(self, i: int) -> str:
        return self._decode_str(i, 0)

    def get_table(self, i: int) -> str:
        return self._decode_str(i, 1)

    def get_org_table(self, i: int) -> str:
        return self._decode_str(i, 2)

    def get_name(self, i: int) -> str:
        return self._decode_str(i, 3)

    def get_org_name(self, i: int) -> str:
        return self._decode_str(i, 4)

    def get_catalog(self, i: int) -> str:
        return 'def'

    # =========================================================================
    # Protocol helpers
    # =========================================================================

    def __len__(self) -> int:
        return self.count
