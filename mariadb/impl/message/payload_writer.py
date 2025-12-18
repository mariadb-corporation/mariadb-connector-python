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
SLASH_BYTE: int = b"\\"[0]
QUOTE_BYTE: int = b"'"[0]
DQUOTE_BYTE: int = b"\""[0]
NULL_BYTE: int = b"\0"[0]


class PayloadWriter:
    """A lightweight write stream that captures bytes to a buffer."""
    
    def __init__(self, initial_size: int = 8192):
        """Initialize payload writer with pre-allocated buffer"""
        self._default_buffer: bytearray = bytearray(initial_size)
        self._buffer: bytearray = self._default_buffer
        self._pos: int = 4
    
    def get_payload(self) -> bytearray:
        """Return the accumulated payload as bytearray (avoids copy)"""
        return self._buffer[:self._pos]
    
    def reset(self) -> None:
        """Reset writer to default buffer"""
        self._buffer = self._default_buffer
        self._pos = 4
    
    def _ensure_capacity(self, needed: int) -> None:
        """Ensure buffer has enough capacity for needed bytes"""
        required = self._pos + needed
        if required > len(self._buffer):
            # Grow by at least 2x or required size, whichever is larger
            new_size = max(required, len(self._buffer) * 2)
            new_buffer = bytearray(new_size)
            new_buffer[:self._pos] = self._buffer[:self._pos]
            self._buffer = new_buffer
    
    def write_byte(self, value: int) -> None:
        """Write a single byte"""
        self._ensure_capacity(1)
        self._buffer[self._pos] = value
        self._pos += 1
    
    def write_bytes(self, data: bytes) -> None:
        """Write bytes"""
        data_len = len(data)
        self._ensure_capacity(data_len)
        self._buffer[self._pos:self._pos + data_len] = data
        self._pos += data_len
    
    def write_string(self, text: str, encoding: str = 'utf-8') -> None:
        """Write string"""
        encoded = text.encode(encoding)
        data_len = len(encoded)
        self._ensure_capacity(data_len)
        self._buffer[self._pos:self._pos + data_len] = encoded
        self._pos += data_len
    
    def write_uint16(self, data: int) -> None:
        """Write 16-bit unsigned integer (little-endian)"""
        self._ensure_capacity(2)
        self._buffer[self._pos:self._pos + 2] = data.to_bytes(2, 'little')
        self._pos += 2
    
    def write_uint24(self, data: int) -> None:
        """Write 24-bit unsigned integer (little-endian)"""
        self._ensure_capacity(3)
        self._buffer[self._pos:self._pos + 3] = data.to_bytes(3, 'little')
        self._pos += 3
    
    def write_uint32(self, data: int) -> None:
        """Write 32-bit unsigned integer (little-endian)"""
        self._ensure_capacity(4)
        self._buffer[self._pos:self._pos + 4] = data.to_bytes(4, 'little')
        self._pos += 4
    
    def write_uint64(self, data: int) -> None:
        """Write 64-bit unsigned integer (little-endian)"""
        self._ensure_capacity(8)
        self._buffer[self._pos:self._pos + 8] = data.to_bytes(8, 'little')
        self._pos += 8
    
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
        
        data_len = len(escaped)
        self._ensure_capacity(data_len)
        self._buffer[self._pos:self._pos + data_len] = escaped
        self._pos += data_len
    
    def write_length_encoded_string(self, text: str, encoding: str = 'utf-8') -> None:
        """Write length-encoded string"""
        encoded = text.encode(encoding)
        self.write_length_encoded_int(len(encoded))
        data_len = len(encoded)
        self._ensure_capacity(data_len)
        self._buffer[self._pos:self._pos + data_len] = encoded
        self._pos += data_len
    
    def write_length_encoded_bytes(self, data: bytes) -> None:
        """Write length-encoded bytes"""
        self.write_length_encoded_int(len(data))
        data_len = len(data)
        self._ensure_capacity(data_len)
        self._buffer[self._pos:self._pos + data_len] = data
        self._pos += data_len
    
    def write_length_encoded_int(self, length: int) -> None:
        """Write length-encoded integer"""
        if length < 251:
            self._ensure_capacity(1)
            self._buffer[self._pos] = length
            self._pos += 1
        elif length < 65536:
            self._ensure_capacity(3)
            self._buffer[self._pos] = 0xfc
            self._buffer[self._pos + 1:self._pos + 3] = length.to_bytes(2, 'little')
            self._pos += 3
        elif length < 16777216:
            self._ensure_capacity(4)
            self._buffer[self._pos] = 0xfd
            self._buffer[self._pos + 1:self._pos + 4] = length.to_bytes(3, 'little')
            self._pos += 4
        else:
            self._ensure_capacity(9)
            self._buffer[self._pos] = 0xfe
            self._buffer[self._pos + 1:self._pos + 9] = length.to_bytes(8, 'little')
            self._pos += 9
