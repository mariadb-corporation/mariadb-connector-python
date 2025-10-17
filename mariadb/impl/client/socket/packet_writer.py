#
# Copyright (C) 2020-2021 Georg Richter and MariaDB Corporation AB

# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Library General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.

# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Library General Public License for more details.

# You should have received a copy of the GNU Library General Public
# License along with this library; if not see <http://www.gnu.org/licenses>
# or write to the Free Software Foundation, Inc.,
# 51 Franklin St., Fifth Floor, Boston, MA 02110, USA
#

"""
Packet Writer for MariaDB protocol

Equivalent to the Java StandardPacketWriter.
"""

import struct
from typing import Optional, Union

from ....constants import CAPABILITY

from .stream.stream import Stream
from ...debug_utils import log_socket_data
from .mutable_int import MutableInt


class PacketWriter:
    
    SLASH_BYTE: int = b"\\"[0]
    QUOTE_BYTE: int = b"'"[0]
    DQUOTE_BYTE: int = b"\""[0]
    NULL_BYTE: int = b"\0"[0]

    """
    Packet writer for MariaDB protocol
    
    Equivalent to the Java StandardPacketWriter.
    """
    
    def __init__(self, stream: Stream, debug: bool = False):
        """
        Initialize writer
        
        Args:
            stream: stream to write to (may be wrapped with CompressStream)
            buffer_size: Initial buffer size
            debug: Enable debug logging
        """
        self.stream: Stream = stream
        self.buffer: bytearray = bytearray(8192)
        self.position: int = 0
        self.max_packet_size: int = 16777215  # 16MB - 1 (0xffffff)
        self.debug: bool = debug
        
    def pos(self) -> int:
        """Get current buffer position"""
        return self.position
    
    def buf(self) -> bytearray:
        """Get current buffer"""
        return self.buffer
    
    def set_pos(self, pos: int) -> None:
        """Set current buffer position"""
        if pos > len(self.buffer):
            self._grow_buffer(pos)
        self.position = pos
    
    
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
        """
        Write MySQL length-encoded integer
        
        Args:
            value: Integer value to encode
        """
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
    
    def write_length_encoded_string(self, value: Optional[str], encoding: str = 'utf-8') -> None:
        """
        Write MySQL length-encoded string
        
        Args:
            value: String to write (None for NULL)
            encoding: Character encoding
        """
        if value is None:
            self.write_byte(0xFB)  # NULL marker
            return
        
        data = value.encode(encoding)
        self.write_length_encoded_int(len(data))
        self.write_bytes(data)
    
    def write_null_terminated_string(self, value: str, encoding: str = 'utf-8') -> None:
        """
        Write null-terminated string
        
        Args:
            value: String to write
            encoding: Character encoding
        """
        if value:
            self.write_string(value, encoding)
        self.write_byte(0)
    
    def start_payload(self, reset_sequence: bool = True) -> None:
        """
        Start payload mode - all subsequent writes go to payload buffer
        
        Args:
            reset_sequence: If True, reset sequence to 0 for command packets.
                           If False, continue with current sequence (for handshake, SSL request)
        """
        self.buffer = bytearray()
        self.position = 0
        if reset_sequence:
            self.stream.reset()
    
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
                if byte == self.QUOTE_BYTE:
                    self.write_byte(self.QUOTE_BYTE)
                self.write_byte(byte)
        else:    
            for byte in data:
                if byte == self.QUOTE_BYTE or byte == self.DQUOTE_BYTE or byte == self.NULL_BYTE or byte == self.SLASH_BYTE:
                    self.write_byte(self.SLASH_BYTE)
                self.write_byte(byte)

    def write_string(self, value: str, encoding: str = 'utf-8') -> None:
        """Write string to buffer or payload"""
        if value is None:
            return
            
        data = value.encode(encoding)
        self.write_bytes(data)
    
    def write_length_encoded_string(self, value: str, encoding: str = 'utf-8') -> None:
        """Write length-encoded string"""
        if value is None:
            self.write_byte(0xFB)  # NULL marker
            return
        
        data = value.encode(encoding)
        self.write_length_encoded_int(len(data))
        self.write_bytes(data)
    
    def write_length_encoded_bytes(self, data: bytes) -> None:
        """Write length-encoded bytes"""
        if data is None:
            self.write_byte(0xFB)  # NULL marker
            return
        
        self.write_length_encoded_int(len(data))
        self.write_bytes(data)
    
    def write_length_encoded_int(self, value: int) -> None:
        """Write length-encoded integer"""
        if value < 251:
            self.write_byte(value)
        elif value < 65536:
            self.write_byte(0xFC)
            self.write_bytes(struct.pack('<H', value))
        elif value < 16777216:
            self.write_byte(0xFD)
            self.write_bytes(struct.pack('<I', value)[:3])
        else:
            self.write_byte(0xFE)
            self.write_bytes(struct.pack('<Q', value))
    
    def send_payload(self, packet_type: str) -> None:
        """
        Send payload with automatic packet chunking.
        
        Handles packets larger than 0xffffff by splitting into multiple packets.
        If a packet is exactly 0xffffff bytes, sends an additional empty packet.
        """
        payload_length = self.position
        offset = 0
        
        while offset < payload_length:
            # Calculate chunk size (max 0xffffff bytes)
            chunk_size = min(self.max_packet_size, payload_length - offset)
            chunk_data = self.buffer[offset:offset + chunk_size]
            
            # Send packet with header
            self._send_packet_chunk(chunk_data, packet_type)
            
            offset += chunk_size
            
            # If this chunk was exactly max size and there's no more data,
            # send an empty packet to indicate end
            if chunk_size == self.max_packet_size and offset == payload_length:
                self._send_packet_chunk(b'', packet_type)
        
        # If payload was empty, still send one packet
        if payload_length == 0:
            self._send_packet_chunk(b'', packet_type)
    
    def _send_packet_chunk(self, chunk_data: bytes, packet_type: str) -> None:
        """
        Send a single packet chunk with header
        
        Args:
            chunk_data: Data to send (max 0xffffff bytes)
        """
        chunk_length = len(chunk_data)
        
        # Prepare packet with header
        packet = bytearray()
        
        # Write 3-byte length (little-endian)
        packet.append(chunk_length & 0xFF)
        packet.append((chunk_length >> 8) & 0xFF)
        packet.append((chunk_length >> 16) & 0xFF)
        
        # Write sequence ID
        packet.append(self.stream.sequence.get_and_increment() & 0xFF)
        
        # Write chunk data
        packet.extend(chunk_data)
        
        # Log and send
        if self.debug:
            log_socket_data(packet, "SEND", packet_type)
        self.stream.sendall(packet)

    def close(self) -> None:
        """Close writer and stream"""
        self.stream.close()

    def _ensure_capacity(self, additional_bytes: int) -> None:
        """
        Ensure buffer has capacity for additional bytes
        
        Args:
            additional_bytes: Number of additional bytes needed
        """
        required_size = self.position + additional_bytes
        if required_size > len(self.buffer):
            self._grow_buffer(required_size)
    
    def _grow_buffer(self, min_size: int) -> None:
        """
        Grow buffer to accommodate minimum size
        
        Args:
            min_size: Minimum required size
        """
        current_size = len(self.buffer)
        new_size = max(int(current_size * 1.5), min_size)
        
        new_buffer = bytearray(new_size)
        new_buffer[:current_size] = self.buffer
        self.buffer = new_buffer
