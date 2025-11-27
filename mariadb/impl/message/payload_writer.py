# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
PayloadWriter - A write stream implementation that captures bytes to a buffer
without sending them over the network. Used for generating message payloads.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# Constants from write_stream
HEADER_SIZE = 4
SLASH_BYTE: int = b"\\"[0]
QUOTE_BYTE: int = b"'"[0]
DQUOTE_BYTE: int = b"\""[0]
NULL_BYTE: int = b"\0"[0]


class PayloadWriter:
    """A lightweight write stream that captures bytes to a buffer."""
    
    def __init__(self):
        """Initialize payload writer with empty buffer"""
        self._buffer: bytearray = bytearray(4)
    
    def get_payload(self) -> bytearray:
        """Return the accumulated payload as bytearray (avoids copy)"""
        return self._buffer
    
    def write_byte(self, value: int) -> None:
        """Write a single byte"""
        self._buffer.append(value)
    
    def write_bytes(self, data: bytes) -> None:
        """Write bytes"""
        self._buffer.extend(data)
    
    def write_string(self, text: str, encoding: str = 'utf-8') -> None:
        """Write string"""
        self._buffer.extend(text.encode(encoding))
    
    def write_uint16(self, data: int) -> None:
        """Write 16-bit unsigned integer (little-endian)"""
        self._buffer.extend(data.to_bytes(2, 'little'))
    
    def write_uint24(self, data: int) -> None:
        """Write 24-bit unsigned integer (little-endian)"""
        self._buffer.extend(data.to_bytes(3, 'little'))
    
    def write_uint32(self, data: int) -> None:
        """Write 32-bit unsigned integer (little-endian)"""
        self._buffer.extend(data.to_bytes(4, 'little'))
    
    def write_uint64(self, data: int) -> None:
        """Write 64-bit unsigned integer (little-endian)"""
        self._buffer.extend(data.to_bytes(8, 'little'))
    
    def write_escaped_bytes(self, data: bytes, no_backslash_escapes: bool) -> None:
        """Write escaped bytes for SQL string literals"""
        if not data:
            return
        
        if no_backslash_escapes:
            escaped = data.replace(b"'", b"''")
        else:
            escaped = data.replace(b"\\", b"\\\\") \
                          .replace(b"\0", b"\\\0") \
                          .replace(b"'", b"\\'") \
                          .replace(b'"', b'\\"')
        
        self._buffer.extend(escaped)
    
    def write_length_encoded_string(self, text: str, encoding: str = 'utf-8') -> None:
        """Write length-encoded string"""
        encoded = text.encode(encoding)
        self.write_length_encoded_int(len(encoded))
        self._buffer.extend(encoded)
    
    def write_length_encoded_bytes(self, data: bytes) -> None:
        """Write length-encoded bytes"""
        self.write_length_encoded_int(len(data))
        self._buffer.extend(data)
    
    def write_length_encoded_int(self, length: int) -> None:
        """Write length-encoded integer"""
        if length < 251:
            self._buffer.append(length)
        elif length < 65536:
            self._buffer.append(0xfc)
            self._buffer.extend(length.to_bytes(2, 'little'))
        elif length < 16777216:
            self._buffer.append(0xfd)
            self._buffer.extend(length.to_bytes(3, 'little'))
        else:
            self._buffer.append(0xfe)
            self._buffer.extend(length.to_bytes(8, 'little'))
