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
Packet Reader for MariaDB protocol

Equivalent to the Java StandardPacketReader.
"""

import socket
import struct
import sys
from typing import Optional, Tuple

from .stream.stream import Stream
from ...debug_utils import log_socket_data


class PacketReader:
    """
    Packet reader for MariaDB protocol
    
    Equivalent to the Java StandardPacketReader.
    """
    
    def __init__(self, stream: Stream, debug: bool = False, connection_id: int = -1):
        """
        Initialize reader
        
        Args:
            stream: stream to read from (may be wrapped with CompressStream)
            sequence: Shared sequence number tracker (optional, will create new if None)
            debug: Enable debug logging
            connection_id: Connection ID for debug output
        """
        self.stream: Stream = stream
        self.debug: bool = debug
        self.connection_id: int = connection_id
        
    def read_packet(self) -> bytes:
        """
        Read a complete MySQL packet
        
        Returns:
            Complete packet data (without 4-byte header)
            
        Raises:
            IOError: If socket error occurs or packet is invalid
        """
        # Read 4-byte header (compression is handled transparently by CompressStream if enabled)
        header = self._read_exactly(4)
        
        # Parse header: 3 bytes length + 1 byte sequence
        packet_length = struct.unpack('<I', header[:3] + b'\x00')[0]
        # Set sequence for next outgoing packet (received + 1)
        self.stream.sequence.set((header[3] + 1) % 256)
        
        # Read packet payload
        if packet_length == 0:
            payload = b''
        else:
            payload = self._read_exactly(packet_length)
        
        # Log complete packet (header + payload) if debug is enabled
        complete_packet = header + payload
        if self.debug:
            log_socket_data(complete_packet, "RECV", connection_id=self.connection_id)
        
        # Handle multi-packet messages (packets of exactly 16MB)
        if packet_length == 0xFFFFFF:
            # This is part of a larger message, read next packet
            next_packet = self.read_packet()
            payload += next_packet
        
        return payload
    
    def read_byte(self) -> int:
        """
        Read single byte from socket
        
        Returns:
            Byte value (0-255)
            
        Raises:
            IOError: If socket error occurs
        """
        data = self._read_exactly(1)
        return data[0]
    
    def read_short(self) -> int:
        """
        Read 2-byte little-endian short from socket
        
        Returns:
            Short value
            
        Raises:
            IOError: If socket error occurs
        """
        data = self._read_exactly(2)
        return struct.unpack('<H', data)[0]
    
    def read_int(self) -> int:
        """
        Read 4-byte little-endian int from socket
        
        Returns:
            Int value
            
        Raises:
            IOError: If socket error occurs
        """
        data = self._read_exactly(4)
        return struct.unpack('<I', data)[0]
    
    def read_long(self) -> int:
        """
        Read 8-byte little-endian long from socket
        
        Returns:
            Long value
            
        Raises:
            IOError: If socket error occurs
        """
        data = self._read_exactly(8)
        return struct.unpack('<Q', data)[0]
    
    def read_length_encoded_int(self, packet: bytes, pos: int) -> Tuple[int, int]:
        """
        Read MySQL length-encoded integer from packet
        
        Args:
            packet: Packet data
            pos: Current position in packet
            
        Returns:
            Tuple of (value, new_position)
            
        Raises:
            IOError: If packet is too short
        """
        if pos >= len(packet):
            raise IOError("Packet too short for length-encoded integer")
        
        first_byte = packet[pos]
        
        if first_byte < 251:
            return first_byte, pos + 1
        elif first_byte == 0xFC:
            if pos + 3 > len(packet):
                raise IOError("Packet too short for 2-byte length-encoded integer")
            value = struct.unpack('<H', packet[pos + 1:pos + 3])[0]
            return value, pos + 3
        elif first_byte == 0xFD:
            if pos + 4 > len(packet):
                raise IOError("Packet too short for 3-byte length-encoded integer")
            value = struct.unpack('<I', packet[pos + 1:pos + 4] + b'\x00')[0]
            return value, pos + 4
        elif first_byte == 0xFE:
            if pos + 9 > len(packet):
                raise IOError("Packet too short for 8-byte length-encoded integer")
            value = struct.unpack('<Q', packet[pos + 1:pos + 9])[0]
            return value, pos + 9
        else:
            raise IOError(f"Invalid length-encoded integer marker: {first_byte}")
    
    def read_length_encoded_string(self, packet: bytes, pos: int, encoding: str = 'utf-8') -> Tuple[Optional[str], int]:
        """
        Read MySQL length-encoded string from packet
        
        Args:
            packet: Packet data
            pos: Current position in packet
            encoding: Character encoding
            
        Returns:
            Tuple of (string_value, new_position). String is None for NULL.
            
        Raises:
            IOError: If packet is too short
        """
        if pos >= len(packet):
            raise IOError("Packet too short for length-encoded string")
        
        # Check for NULL marker
        if packet[pos] == 0xFB:
            return None, pos + 1
        
        # Read string length
        length, new_pos = self.read_length_encoded_int(packet, pos)
        
        if new_pos + length > len(packet):
            raise IOError("Packet too short for string data")
        
        # Extract string data
        string_data = packet[new_pos:new_pos + length]
        try:
            value = string_data.decode(encoding)
        except UnicodeDecodeError as e:
            raise IOError(f"Failed to decode string: {e}")
        
        return value, new_pos + length
    
    def read_length_string_encoded_int(self, packet: bytes, pos: int) -> Tuple[Optional[int], int]:
        """
        Read MySQL length-encoded string and convert to integer (atoll equivalent)
        
        Args:
            packet: Packet data
            pos: Current position in packet
            
        Returns:
            Tuple of (int_value, new_position). Value is None for NULL.
            
        Raises:
            IOError: If packet is too short
            ValueError: If data cannot be converted to integer
        """
        if pos >= len(packet):
            raise IOError("Packet too short for length-encoded integer")
        
        # Check for NULL marker
        if packet[pos] == 0xFB:
            return None, pos + 1
        
        # Read string length
        length, new_pos = self.read_length_encoded_int(packet, pos)
        
        if new_pos + length > len(packet):
            raise IOError("Packet too short for integer data")
        
        # Parse integer directly from binary data
        value = 0
        is_negative = False
        start_pos = new_pos
        
        # Handle empty string
        if length == 0:
            return 0, new_pos
        
        # Check for negative sign
        if packet[new_pos] == 0x2D:  # '-' character
            is_negative = True
            new_pos += 1
            length -= 1
        elif packet[new_pos] == 0x2B:  # '+' character
            new_pos += 1
            length -= 1
        
        # Parse digits directly from bytes
        for i in range(length):
            digit = packet[new_pos + i] - 0x30
            value = value * 10 + digit
        
        # Calculate correct end position including the sign character if present
        total_length = length + (1 if is_negative else 0)
        return -value if is_negative else value, start_pos + total_length
    
    def read_length_encoded_bytes(self, packet: bytes, pos: int) -> Tuple[Optional[bytes], int]:
        """
        Read MySQL length-encoded binary data directly as bytes (optimized for BLOBs)
        
        Args:
            packet: Packet data
            pos: Current position in packet
            
        Returns:
            Tuple of (bytes_value, new_position). Value is None for NULL.
            
        Raises:
            IOError: If packet is too short
        """
        if pos >= len(packet):
            raise IOError("Packet too short for length-encoded bytes")
        
        # Check for NULL marker
        if packet[pos] == 0xFB:
            return None, pos + 1
        
        # Read data length
        length, new_pos = self.read_length_encoded_int(packet, pos)
        
        if new_pos + length > len(packet):
            raise IOError("Packet too short for binary data")
        
        # Extract binary data directly (no encoding/decoding)
        binary_data = packet[new_pos:new_pos + length]
        
        return binary_data, new_pos + length
    
    def read_null_terminated_string(self, packet: bytes, pos: int, encoding: str = 'utf-8') -> Tuple[str, int]:
        """
        Read null-terminated string from packet
        
        Args:
            packet: Packet data
            pos: Current position in packet
            encoding: Character encoding
            
        Returns:
            Tuple of (string_value, new_position)
            
        Raises:
            IOError: If packet is too short or no null terminator found
        """
        null_pos = packet.find(0, pos)
        if null_pos == -1:
            raise IOError("No null terminator found in packet")
        
        string_data = packet[pos:null_pos]
        try:
            value = string_data.decode(encoding)
        except UnicodeDecodeError as e:
            raise IOError(f"Failed to decode string: {e}")
        
        return value, null_pos + 1
        
    def close(self) -> None:
        """Close reader and socket"""
        self.stream.close()
    
    def _read_exactly(self, num_bytes: int) -> bytes:
        """
        Read exactly the specified number of bytes from socket
        
        Args:
            num_bytes: Number of bytes to read
            
        Returns:
            Bytes read from socket
            
        Raises:
            IOError: If socket error occurs or connection closed
        """
        data = b''
        while len(data) < num_bytes:
            try:
                chunk = self.stream.recv(num_bytes - len(data))
                if not chunk:
                    raise IOError("Connection closed by server")
                data += chunk
            except socket.timeout:
                raise IOError("Socket timeout while reading data")
            except Exception as e:
                raise IOError(f"Socket error while reading data: {e}")
        
        return data
    