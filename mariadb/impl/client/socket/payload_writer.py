# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

import struct
from typing import Union

SLASH_BYTE: int = b"\\"[0]
QUOTE_BYTE: int = b"'"[0]
DQUOTE_BYTE: int = b"\""[0]
NULL_BYTE: int = b"\0"[0]

class PayloadWriter:
    
    """
    Writer utility for MariaDB protocol
    """
    
    def __init__(self, buffer_size: int = 8192):
        """Initialize payload writer with initial buffer size"""
        self.buffer: bytearray = bytearray(buffer_size)
        self.position: int = 0
        self.max_packet_size: int = 16777215  # 16MB - 1 (0xffffff)
        self._buffer_len: int = buffer_size
        
    def write_short(self, value: int) -> None:
        """Write 2-byte little-endian short"""
        self._ensure_capacity(2)
        struct.pack_into('<H', self.buffer, self.position, value & 0xFFFF)
        self.position += 2
    
    def write_int(self, value: int) -> None:
        """Write 4-byte little-endian int"""
        self._ensure_capacity(4)
        struct.pack_into('<I', self.buffer, self.position, value & 0xFFFFFFFF)
        self.position += 4
    
    def write_long(self, value: int) -> None:
        """Write 8-byte little-endian long"""
        self._ensure_capacity(8)
        struct.pack_into('<Q', self.buffer, self.position, value & 0xFFFFFFFFFFFFFFFF)
        self.position += 8
    
    
    def write_length_encoded_int(self, value: int) -> None:
        """Write MySQL length-encoded integer"""
        if value < 251:
            self.write_byte(value)
        elif value < 65536:
            self.write_byte(0xFC)
            self.write_short(value)
        elif value < 16777216:
            self.write_byte(0xFD)
            self.write_int24(value)
        else:
            self.write_byte(0xFE)
            self.write_long(value)
    
    def write_int24(self, value: int) -> None:
        """Write 3-byte little-endian int"""
        self._ensure_capacity(3)
        self.buffer[self.position] = value & 0xFF
        self.buffer[self.position + 1] = (value >> 8) & 0xFF
        self.buffer[self.position + 2] = (value >> 16) & 0xFF
        self.position += 3

    def write_null_terminated_string(self, value: str, encoding: str = 'utf-8') -> None:
        """Write null-terminated string with optional encoding"""
        if value:
            self.write_string(value, encoding)
        self.write_byte(0)
    
    def start_payload(self) -> None:
        """Start building a new payload by resetting position"""
        self.position = 0
    
    def get_payload(self) -> bytearray:
        """Get current payload as bytearray from position 0 to current position"""
        return self.buffer[0:self.position]
    
    def write_byte(self, value: int) -> None:
        """Write single byte to buffer or payload"""
        self._ensure_capacity(1)
        self.buffer[self.position] = value & 0xFF
        self.position += 1
    
    def write_bytes(self, data: Union[bytes, bytearray]) -> None:
        """Write byte array to buffer or payload"""
        if not data:
            return
            
        data_len = len(data)
        pos = self.position
        new_pos = pos + data_len
        
        if new_pos > self._buffer_len:
            self._ensure_capacity(data_len)
        self.buffer[self.position:self.position + data_len] = data
        self.position += data_len
    
    def write_escaped_bytes(self, data: Union[bytes, bytearray], no_backslash_escapes: bool) -> None:
        """Write escaped byte array to buffer or payload"""
        if not data:
            return

        self._ensure_capacity(len(data) * 2)
        
        if no_backslash_escapes:
            for byte in data:
                if byte == QUOTE_BYTE:
                    self.write_byte(QUOTE_BYTE)
                self.write_byte(byte)
        else:
            for byte in data:
                if byte == QUOTE_BYTE or byte == QUOTE_BYTE or byte == NULL_BYTE or byte == SLASH_BYTE:
                    self.write_byte(SLASH_BYTE)
                self.write_byte(byte)

    def write_string(self, value: str, encoding: str = 'utf-8') -> None:
        """Write string to buffer or payload"""
        data = value.encode(encoding)
        self.write_bytes(data)
    
    def write_length_encoded_string(self, value: str, encoding: str = 'utf-8') -> None:
        """Write length-encoded string"""
        data = value.encode(encoding)
        self.write_length_encoded_int(len(data))
        self.write_bytes(data)
    
    def write_length_encoded_bytes(self, data: bytes) -> None:
        """Write length-encoded bytes"""
        self.write_length_encoded_int(len(data))
        self.write_bytes(data)

    def _ensure_capacity(self, additional_bytes: int) -> None:
        """Ensure buffer has capacity for additional bytes"""
        required_size = self.position + additional_bytes
        if required_size > self._buffer_len:
            self._grow_buffer(required_size)
    
    def _grow_buffer(self, min_size: int) -> None:
        """Grow buffer to accommodate minimum size"""
        current_size = self._buffer_len
        new_size = max(int(current_size * 1.5), min_size)
        
        new_buffer = bytearray(new_size)
        new_buffer[:current_size] = self.buffer
        self.buffer = new_buffer
        self._buffer_len = new_size
