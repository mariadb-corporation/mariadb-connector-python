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
Compression stream wrappers for MariaDB protocol

Provides reader and writer wrappers that handle compression/decompression
with 7-byte compression headers. These wrap the underlying async/sync streams.
"""

import asyncio
import socket
import struct
import zlib
import logging
from typing import Optional, Union

logger = logging.getLogger(__name__)


class AsyncCompressStreamReader:
    """
    Async compression stream reader that wraps an asyncio.StreamReader
    
    Handles decompression of MySQL/MariaDB packets with 7-byte compression headers.
    """
    
    MAX_PACKET_SIZE = 0x00ffffff  # Maximum MySQL packet size
    
    def __init__(self, reader: asyncio.StreamReader, connection_id: int = -1):
        """
        Initialize async compression stream reader
        
        Args:
            reader: Asyncio stream reader to wrap
            connection_id: Connection ID for debug output
        """
        self.reader = reader
        self.connection_id = connection_id
        
        # Compression sequence for reading
        self.sequence_comp = 0
        
        # Read buffer for decompressed data
        self.read_buffer: Optional[bytes] = None
        self.read_pos = 0
        self.read_end = 0
    
    async def read_payload(self) -> bytes:
        """
        Read a complete MySQL packet payload (decompressed)
        
        Handles decompression and reassembly of multi-packet messages.
        
        Returns:
            Packet payload as bytes (without 4-byte MySQL header)
        """
        # Accumulator for multi-packet payloads
        complete_payload = bytearray()
        
        # Keep reading MySQL packets until we get one with length < 0xFFFFFF
        while True:
            # Ensure we have data in the read buffer
            if self.read_buffer is None or self.read_pos >= self.read_end:
                await self._read_compressed_packet()
            
            # Read 4-byte MySQL packet header from decompressed buffer
            if self.read_end - self.read_pos < 4:
                raise IOError("Incomplete MySQL packet header in decompressed data")
            
            packet_length = struct.unpack('<I', self.read_buffer[self.read_pos:self.read_pos+3] + b'\x00')[0]
            # packet_sequence = self.read_buffer[self.read_pos + 3]  # Not used currently
            self.read_pos += 4
            
            # Read MySQL packet payload from decompressed buffer
            if self.read_end - self.read_pos < packet_length:
                raise IOError("Incomplete MySQL packet payload in decompressed data")
            
            payload = self.read_buffer[self.read_pos:self.read_pos + packet_length]
            self.read_pos += packet_length
            
            # Add this payload to the complete payload
            complete_payload.extend(payload)
            
            # If packet length < 0xFFFFFF, this is the last packet
            if packet_length < self.MAX_PACKET_SIZE:
                break
        
        return bytes(complete_payload)
    
    async def _read_compressed_packet(self) -> None:
        """
        Read and decompress a single packet from the stream
        
        Raises:
            IOError: If stream error occurs
        """
        # Read 7-byte compression header
        header = await self.reader.readexactly(7)
        
        # Parse compression header
        compressed_length = (header[0] & 0xff) | ((header[1] & 0xff) << 8) | ((header[2] & 0xff) << 16)
        self.sequence_comp = (header[3] + 1) & 0xff
        uncompressed_length = (header[4] & 0xff) | ((header[5] & 0xff) << 8) | ((header[6] & 0xff) << 16)
        
        # Read compressed data
        compressed_data = await self.reader.readexactly(compressed_length)
        
        # Check if data is actually compressed
        is_compressed = (uncompressed_length != 0)
        
        if is_compressed:
            # Decompress the data
            try:
                decompressed_data = zlib.decompress(compressed_data)
                if len(decompressed_data) != uncompressed_length:
                    raise IOError(f"Invalid decompression length: got {len(decompressed_data)}, expected {uncompressed_length}")
                
                if logger.isEnabledFor(logging.DEBUG):
                    conn_id_str = f"[conn_id={self.connection_id}]" if self.connection_id >= 0 else ""
                    logger.debug(f"Compress READ:{conn_id_str} compressed={compressed_length} uncompressed={uncompressed_length}")
                
                self.read_buffer = decompressed_data
            except zlib.error as e:
                raise IOError(f"Decompression failed: {e}")
        else:
            if logger.isEnabledFor(logging.DEBUG):
                conn_id_str = f"[conn_id={self.connection_id}]" if self.connection_id >= 0 else ""
                logger.debug(f"Compress READ:{conn_id_str} uncompressed length={compressed_length}")
            # Data is not compressed, use as-is
            self.read_buffer = compressed_data
        
        # Reset buffer position
        self.read_pos = 0
        self.read_end = len(self.read_buffer)


class AsyncCompressStreamWriter:
    """
    Async compression stream writer that wraps an asyncio.StreamWriter
    
    Handles compression of MySQL/MariaDB packets with 7-byte compression headers.
    """
    
    MIN_COMPRESSION_SIZE = 1536  # TCP-IP single packet size
    MAX_PACKET_SIZE = 0x00ffffff  # Maximum MySQL packet size
    
    def __init__(self, writer: asyncio.StreamWriter, connection_id: int = -1):
        """
        Initialize async compression stream writer
        
        Args:
            writer: Asyncio stream writer to wrap
            connection_id: Connection ID for debug output
        """
        self.writer = writer
        self.connection_id = connection_id
        
        # Compression sequence for writing
        self.sequence_comp = 0
    
    async def write_payload(self, data: bytes, packet_type: str = "") -> None:
        """
        Write a payload with compression
        
        Args:
            data: Payload data to send (MySQL packet with 4-byte header)
            packet_type: Packet type for debugging (e.g., "COM_QUERY")
        """
        if logger.isEnabledFor(logging.DEBUG):
            conn_id_str = f"[conn_id={self.connection_id}]" if self.connection_id >= 0 else ""
            packet_type_str = f" {packet_type}" if packet_type else ""
            logger.debug(f"Compress SEND:{conn_id_str}{packet_type_str} length={len(data)}")
        
        # Decide whether to compress based on size
        if len(data) < self.MIN_COMPRESSION_SIZE:
            # Small packet - send uncompressed
            await self._write_uncompressed(data)
        else:
            # Large packet - compress
            await self._write_compressed(data)
    
    async def _write_uncompressed(self, data: bytes) -> None:
        """
        Write uncompressed packet with 7-byte compression header
        
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
        header[3] = self.sequence_comp & 0xff
        self.sequence_comp = (self.sequence_comp + 1) & 0xff
        
        # Uncompressed length (3 bytes) - 0 indicates no compression
        header[4] = 0
        header[5] = 0
        header[6] = 0
        
        # Write header and uncompressed data
        self.writer.write(header + data)
        await self.writer.drain()
    
    async def _write_compressed(self, data: bytes) -> None:
        """
        Write compressed packet with 7-byte compression header
        
        Args:
            data: Packet data to write
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
        header[3] = self.sequence_comp & 0xff
        self.sequence_comp = (self.sequence_comp + 1) & 0xff
        
        # Uncompressed length (3 bytes) - non-zero indicates compression
        uncompressed_length = len(data)
        header[4] = uncompressed_length & 0xff
        header[5] = (uncompressed_length >> 8) & 0xff
        header[6] = (uncompressed_length >> 16) & 0xff
        
        # Write header and compressed data
        self.writer.write(header + compressed_data)
        await self.writer.drain()
    
    async def close(self) -> None:
        """Close the underlying writer"""
        self.writer.close()
        await self.writer.wait_closed()


class SyncCompressSocket:
    """
    Sync compression socket wrapper
    
    Acts as a complete socket replacement, implementing both recv() and sendall()
    to handle compression/decompression transparently.
    """
    
    MIN_COMPRESSION_SIZE = 1536  # TCP-IP single packet size
    
    def __init__(self, sock: socket.socket, connection_id: int = -1):
        """
        Initialize sync compression socket
        
        Args:
            sock: Socket to wrap
            connection_id: Connection ID for debug output
        """
        self._socket = sock
        self.connection_id = connection_id
        
        self.sequence_comp = 0
        
        # Read buffer for decompressed data
        self.read_buffer: Optional[bytes] = None
        self.read_pos = 0
        self.read_end = 0
    
    def recv(self, bufsize: int) -> bytes:
        """
        Receive data from socket (decompressed)
        
        Acts like socket.recv() but handles decompression transparently.
        
        Args:
            bufsize: Maximum number of bytes to receive
            
        Returns:
            Decompressed data bytes
        """
        # Ensure we have data in the read buffer
        if self.read_buffer is None or self.read_pos >= self.read_end:
            self._read_compressed_packet()
        
        # Return up to bufsize bytes from the decompressed buffer
        available = self.read_end - self.read_pos
        to_read = min(bufsize, available)
        
        data = self.read_buffer[self.read_pos:self.read_pos + to_read]
        self.read_pos += to_read
        
        return data
    
    def sendall(self, data: bytes) -> None:
        """
        Send data to socket (compressed)
        
        Acts like socket.sendall() but handles compression transparently.
        
        Args:
            data: Data to send (will be compressed if large enough)
        """
        if logger.isEnabledFor(logging.DEBUG):
            conn_id_str = f"[conn_id={self.connection_id}]" if self.connection_id >= 0 else ""
            logger.debug(f"Compress SEND:{conn_id_str} length={len(data)}")
        
        # Decide whether to compress based on size
        if len(data) < self.MIN_COMPRESSION_SIZE:
            # Small packet - send uncompressed
            self._write_uncompressed(data)
        else:
            # Large packet - compress
            self._write_compressed(data)
    
    def close(self) -> None:
        """Close the underlying socket"""
        self._socket.close()
    
    def _read_compressed_packet(self) -> None:
        """
        Read and decompress a single packet from the stream
        
        Raises:
            IOError: If stream error occurs
        """
        # Read 7-byte compression header
        header = self._recv_exactly(7)
        
        # Parse compression header
        compressed_length = (header[0] & 0xff) | ((header[1] & 0xff) << 8) | ((header[2] & 0xff) << 16)
        self.sequence_comp = (header[3] + 1) & 0xff
        uncompressed_length = (header[4] & 0xff) | ((header[5] & 0xff) << 8) | ((header[6] & 0xff) << 16)
        
        # Read compressed data
        compressed_data = self._recv_exactly(compressed_length)
        
        # Check if data is actually compressed
        is_compressed = (uncompressed_length != 0)
        
        if is_compressed:
            # Decompress the data
            try:
                decompressed_data = zlib.decompress(compressed_data)
                if len(decompressed_data) != uncompressed_length:
                    raise IOError(f"Invalid decompression length: got {len(decompressed_data)}, expected {uncompressed_length}")
                
                if logger.isEnabledFor(logging.DEBUG):
                    conn_id_str = f"[conn_id={self.connection_id}]" if self.connection_id >= 0 else ""
                    logger.debug(f"Compress READ:{conn_id_str} compressed={compressed_length} uncompressed={uncompressed_length}")
                
                self.read_buffer = decompressed_data
            except zlib.error as e:
                raise IOError(f"Decompression failed: {e}")
        else:
            if logger.isEnabledFor(logging.DEBUG):
                conn_id_str = f"[conn_id={self.connection_id}]" if self.connection_id >= 0 else ""
                logger.debug(f"Compress READ:{conn_id_str} uncompressed length={compressed_length}")
            # Data is not compressed, use as-is
            self.read_buffer = compressed_data
        
        # Reset buffer position
        self.read_pos = 0
        self.read_end = len(self.read_buffer)
    
    def _recv_exactly(self, n: int) -> bytes:
        """
        Receive exactly n bytes from underlying socket
        
        Args:
            n: Number of bytes to receive
            
        Returns:
            Received bytes
            
        Raises:
            IOError: If connection closed or error occurs
        """
        data = bytearray()
        while len(data) < n:
            chunk = self._socket.recv(n - len(data))
            if not chunk:
                raise IOError("Connection closed while reading")
            data.extend(chunk)
        return bytes(data)
    
    def _write_uncompressed(self, data: bytes) -> None:
        """
        Write uncompressed packet with 7-byte compression header
        
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
        header[3] = self.sequence_comp & 0xff
        self.sequence_comp = (self.sequence_comp + 1) & 0xff
        
        # Uncompressed length (3 bytes) - 0 indicates no compression
        header[4] = 0
        header[5] = 0
        header[6] = 0
        
        # Write header and uncompressed data to underlying socket
        self._socket.sendall(header + data)
    
    def _write_compressed(self, data: bytes) -> None:
        """
        Write compressed packet with 7-byte compression header
        
        Args:
            data: Packet data to write
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
        header[3] = self.sequence_comp & 0xff
        self.sequence_comp = (self.sequence_comp + 1) & 0xff
        
        # Uncompressed length (3 bytes) - non-zero indicates compression
        uncompressed_length = len(data)
        header[4] = uncompressed_length & 0xff
        header[5] = (uncompressed_length >> 8) & 0xff
        header[6] = (uncompressed_length >> 16) & 0xff
        
        # Write header and compressed data to underlying socket
        self._socket.sendall(header + compressed_data)
