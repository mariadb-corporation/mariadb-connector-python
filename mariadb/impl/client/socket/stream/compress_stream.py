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
Compression stream for MariaDB protocol

Handles compression/decompression of MySQL/MariaDB packets with 7-byte compression headers.
Acts as a transparent wrapper around the socket for both reading and writing.
Equivalent to the Java CompressInputStream/CompressOutputStream classes.
"""

import socket
import zlib
from typing import Optional
from ..mutable_int import MutableInt
from ....debug_utils import log_socket_data


class CompressStream:
    """
    Compression stream that wraps a socket for transparent compression/decompression.
    
    This stream handles the 7-byte compression protocol and acts as a drop-in
    replacement for the raw socket, allowing readers and writers to work
    without compression-specific logic.
    """
    
    MIN_COMPRESSION_SIZE = 1536  # TCP-IP single packet size
    MAX_PACKET_SIZE = 0x00ffffff  # Maximum MySQL packet size
    
    def __init__(self, socket: socket.socket, debug: bool = False, connection_id: int = -1):
        """
        Initialize compression stream
        
        Args:
            socket_obj: Socket to wrap
            debug: Enable debug output
            connection_id: Connection ID for debug output
        """
        self.socket = socket
        self.debug = debug
        self.connection_id = connection_id
        
        # Compression sequences (separate for read/write)        
        self.sequence: MutableInt = MutableInt(1)
        self.sequence_comp: MutableInt = MutableInt(0)
        
        # Read buffer management
        self.read_buffer: Optional[bytes] = None
        self.read_pos = 0
        self.read_end = 0
    
    
    def reset(self) -> None:
        """
        Reset the packet sequence counter
        
        This should be called at the start of a new command or
        when the protocol requires sequence reset.
        """
        self.sequence.set(0)
        self.sequence_comp.set(0)

    def sequence(self) -> MutableInt:
        return self.sequence

    def sequence_comp(self) -> MutableInt:
        return self.sequence_comp

    def recv(self, size: int) -> bytes:
        """
        Receive data from the compression stream (socket interface compatible)
        
        Args:
            size: Maximum number of bytes to receive
            
        Returns:
            Decompressed data
            
        Raises:
            IOError: If socket error occurs
        """
        if size <= 0:
            return b''
        
        # If we have buffered data, return from buffer first
        if self.read_buffer and self.read_pos < self.read_end:
            available = self.read_end - self.read_pos
            to_return = min(size, available)
            data = self.read_buffer[self.read_pos:self.read_pos + to_return]
            self.read_pos += to_return
            return data
        
        # Need to read a new compressed packet
        self._read_compressed_packet()
        
        # Return requested data from the new buffer
        if self.read_buffer and self.read_pos < self.read_end:
            available = self.read_end - self.read_pos
            to_return = min(size, available)
            data = self.read_buffer[self.read_pos:self.read_pos + to_return]
            self.read_pos += to_return
            return data
        
        return b''
    
    def sendall(self, data: bytes) -> None:
        """
        Send all data through the compression stream (socket interface compatible)
        
        Args:
            data: Data to send
            
        Raises:
            IOError: If socket error occurs
        """
        # Loop until all data is sent
        offset = 0
        while offset < len(data):
            # Determine chunk size (respect MAX_PACKET_SIZE)
            chunk_size = min(len(data) - offset, self.MAX_PACKET_SIZE)
            chunk = data[offset:offset + chunk_size]
            
            # Send this chunk
            self._write_compressed_packet(chunk)
            offset += chunk_size
    
    def _read_compressed_packet(self) -> None:
        """
        Read and decompress a single packet from the socket
        
        Raises:
            IOError: If socket error occurs
        """
        # Read 7-byte compression header
        header = self._read_exactly(7)
        
        # Parse compression header
        compressed_length = (header[0] & 0xff) | ((header[1] & 0xff) << 8) | ((header[2] & 0xff) << 16)
        self.sequence_comp.set((header[3] + 1) & 0xff)
        uncompressed_length = (header[4] & 0xff) | ((header[5] & 0xff) << 8) | ((header[6] & 0xff) << 16)
        
        # Read compressed data
        compressed_data = self._read_exactly(compressed_length)
        
        # Check if data is actually compressed
        is_compressed = (uncompressed_length != 0)
        
        if is_compressed:
            # Decompress the data
            try:
                decompressed_data = zlib.decompress(compressed_data)
                if len(decompressed_data) != uncompressed_length:
                    raise IOError(f"Invalid decompression length: got {len(decompressed_data)}, expected {uncompressed_length}")

                if self.debug:
                    log_socket_data(header + decompressed_data, "READ COMPRESS", connection_id=self.connection_id)

                self.read_buffer = decompressed_data
            except zlib.error as e:
                raise IOError(f"Decompression failed: {e}")
        else:
            if self.debug:
                log_socket_data(header + compressed_data, "READ COMPRESS", connection_id=self.connection_id)
            # Data is not compressed, use as-is
            self.read_buffer = compressed_data
        
        # Reset buffer position
        self.read_pos = 0
        self.read_end = len(self.read_buffer)
    
    def _write_compressed_packet(self, data: bytes) -> None:
        """
        Compress and write packet to socket
        
        Args:
            data: Packet data to write (single chunk, already size-limited)
            
        Raises:
            IOError: If socket error occurs
        """
        if len(data) < self.MIN_COMPRESSION_SIZE:
            # Small packet - no compression
            self._write_uncompressed(data)
        else:
            # Large packet - compress
            self._write_compressed(data)
    
    def _write_uncompressed(self, data: bytes) -> None:
        """
        Write uncompressed packet with 7-byte header
        
        Args:
            data: Packet data to write
        """
        # Create 7-byte header for uncompressed packet
        length = len(data)
        header = bytearray(7)
        
        # Compressed length (3 bytes) - same as uncompressed for uncompressed packets
        header[0] = length & 0xff
        header[1] = (length >> 8) & 0xff
        header[2] = (length >> 16) & 0xff
        
        # Compression sequence (1 byte)
        header[3] = self.sequence_comp.get_and_increment() & 0xff
        
        # Uncompressed length (3 bytes) - 0 indicates no compression
        header[4] = 0
        header[5] = 0
        header[6] = 0
        
        packet = bytearray()
        packet.extend(header)
        packet.extend(data)
        
        # Write header and uncompressed data
        if self.debug:
            log_socket_data(packet, "SEND UNCOMPRESS", connection_id=self.connection_id)
        self._write_to_socket(packet)
    
    def _write_compressed(self, data: bytes) -> None:
        """
        Write compressed packet with 7-byte header
        
        Args:
            data: Packet data to write (single chunk, already size-limited)
        """
        # Compress the data
        try:
            compressed_data = zlib.compress(data)
        except zlib.error as e:
            raise IOError(f"Compression failed: {e}")
        
        compressed_length = len(compressed_data)
        
        # Create 7-byte header for compressed packet
        header = bytearray(7)
        
        # Compressed length (3 bytes)
        header[0] = compressed_length & 0xff
        header[1] = (compressed_length >> 8) & 0xff
        header[2] = (compressed_length >> 16) & 0xff
        
        # Compression sequence (1 byte)
        header[3] = self.sequence_comp.get_and_increment() & 0xff

        # Uncompressed length (3 bytes) - non-zero indicates compression
        uncompressed_length = len(data)
        header[4] = uncompressed_length & 0xff
        header[5] = (uncompressed_length >> 8) & 0xff
        header[6] = (uncompressed_length >> 16) & 0xff
        
        packet = bytearray()
        packet.extend(header)
        packet.extend(compressed_data)
        
        # Write header and compressed data
        if self.debug:
            log_socket_data(packet, "SEND COMPRESS", connection_id=self.connection_id)
        self._write_to_socket(packet)

    
    def close(self) -> None:
        """Close the underlying socket"""
        self.socket.close()
    
    def _read_exactly(self, length: int) -> bytes:
        """
        Read exactly the specified number of bytes from socket
        
        Args:
            length: Number of bytes to read
            
        Returns:
            Bytes read from socket
            
        Raises:
            IOError: If socket error or unexpected EOF
        """
        data = b''
        remaining = length
        
        while remaining > 0:
            try:
                chunk = self.socket.recv(remaining)
                if not chunk:
                    raise IOError(f"Unexpected end of stream, read {len(data)} bytes from {length} (socket closed by server)")
                data += chunk
                remaining -= len(chunk)
            except socket.error as e:
                raise IOError(f"Socket error while reading data: {e}")
        
        return data
    
    def _write_to_socket(self, data: bytes) -> None:
        """
        Write data to socket, handling partial writes
        
        Args:
            data: Data to write
            
        Raises:
            IOError: If socket error occurs
        """
        total_sent = 0
        while total_sent < len(data):
            try:
                sent = self.socket.send(data[total_sent:])
                if sent == 0:
                    raise IOError("Socket connection broken")
                total_sent += sent
            except socket.error as e:
                raise IOError(f"Socket error while writing data: {e}")
    
