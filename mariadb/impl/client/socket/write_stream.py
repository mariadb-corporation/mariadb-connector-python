"""
Write stream interfaces for socket I/O operations (async and sync)
"""

from abc import ABC, abstractmethod
import asyncio
import socket
import struct
import logging

from .mutable_int import MutableInt
from ...debug_utils import hex_dump

# Initial buffer size for write buffers
initial_buffer_size = 8192

logger = logging.getLogger(__name__)

HEADER_SIZE = 4
MAX_PACKET_SIZE = 0xFFFFFF

SLASH_BYTE: int = b"\\"[0]
QUOTE_BYTE: int = b"'"[0]
DQUOTE_BYTE: int = b"\""[0]
NULL_BYTE: int = b"\0"[0]


class BaseWriteStream(ABC):
    """Base class for write stream operations"""
    
    def __init__(self, connection_id: int = -1):
        """
        Initialize write stream
        
        Args:
            connection_id: Connection ID for logging
        """
        self.connection_id: int = connection_id
        self.sequence: MutableInt = MutableInt(-1)
        
        self._writebuf: bytearray = bytearray(initial_buffer_size)
        self._write_view: memoryview = memoryview(self._writebuf)
        self._write_pos: int = HEADER_SIZE  # Start after header
        self._write_start: int = HEADER_SIZE  # Track start of current packet
    
    def begin_write(self, reset_sequence: bool = True) -> None:
        """
        Begin writing a new packet directly to the write buffer.
        Resets write position to start after 4-byte header.
        
        Args:
            reset_sequence: Whether to reset sequence number to 0
        """
        if reset_sequence:
            self.sequence.set(-1)
        self._write_pos = HEADER_SIZE
        self._write_start = HEADER_SIZE
        if len(self._writebuf) > initial_buffer_size:
            self._writebuf = bytearray(initial_buffer_size)
            self._write_view = memoryview(self._writebuf)
    
    @abstractmethod
    def write_byte(self, value: int) -> None:
        """Write a single byte to the write buffer"""
        ...
    
    @abstractmethod
    def write_bytes(self, data: bytes) -> None:
        """Write bytes to the write buffer"""
        ...
    
    @abstractmethod
    def write_string(self, text: str, encoding: str = 'utf-8') -> None:
        """Write string to the write buffer"""
        ...
    
    @abstractmethod
    def write_uint16(self, data: int) -> None:
        """Write a 16-bit integer to the write buffer"""
        ...
    
    @abstractmethod
    def write_uint24(self, data: int) -> None:
        """Write a 24-bit integer to the write buffer"""
        ...
    
    @abstractmethod
    def write_uint32(self, data: int) -> None:
        """Write a 32-bit unsigned integer to the write buffer"""
        ...
    
    @abstractmethod
    def write_uint64(self, data: int) -> None:
        """Write a 64-bit integer to the write buffer"""
        ...
    
    def write_escaped_bytes(self, data: bytes, no_backslash_escapes: bool) -> None:
        """Write escaped bytes for SQL string literals"""
        if not data:
            return
        length = len(data)
        self._ensure_write_capacity(length * 2)
        
        if no_backslash_escapes:
            for byte in data:
                if byte == QUOTE_BYTE:
                    self.write_byte(QUOTE_BYTE)
                self.write_byte(byte)
        else:
            for byte in data:
                if byte == QUOTE_BYTE or byte == DQUOTE_BYTE or byte == NULL_BYTE or byte == SLASH_BYTE:
                    self.write_byte(SLASH_BYTE)
                self.write_byte(byte)
    
    def write_length_encoded_string(self, text: str, encoding: str = 'utf-8') -> None:
        """Write length-encoded string"""
        encoded = text.encode(encoding)
        self.write_length_encoded_int(len(encoded))
        self.write_bytes(encoded)
    
    def write_length_encoded_bytes(self, data: bytes) -> None:
        """Write length-encoded bytes"""
        self.write_length_encoded_int(len(data))
        self.write_bytes(data)
    
    def write_length_encoded_int(self, length: int) -> None:
        """Write length-encoded integer"""
        if length < 251:
            self.write_byte(length)
        elif length < 65536:
            self.write_byte(0xfc)
            self.write_uint16(length)
        elif length < 16777216:
            self.write_byte(0xfd)
            self.write_uint24(length)
        else:
            self.write_byte(0xfe)
            self.write_uint64(length)
    
    @abstractmethod
    def _ensure_write_capacity(self, additional: int) -> None:
        """Ensure write buffer has capacity for additional bytes"""
        ...
    
    @abstractmethod
    def flush(self, packet_type: str = "", end: bool = True) -> None:
        """Flush write buffer to socket (subclass implements I/O)"""
        ...
    
    def reset_sequence(self) -> None:
        """Reset packet sequence number"""
        self.sequence.set(0)


class AsyncWriteStream(BaseWriteStream):
    """Async write stream implementation using asyncio socket operations"""
    
    def __init__(self, writer: asyncio.StreamWriter, connection_id: int = -1):
        """
        Initialize async write stream
        
        Args:
            writer: Asyncio stream writer
            connection_id: Connection ID for logging
        """
        self.writer: asyncio.StreamWriter = writer
        super().__init__(connection_id)
    
    def _ensure_write_capacity(self, additional: int) -> None:
        """Ensure write buffer has capacity for additional bytes"""
        required = self._write_pos + additional
        if required > len(self._writebuf):
            if required > MAX_PACKET_SIZE + HEADER_SIZE:
                new_size = max(required, int(len(self._writebuf) * 1.5))
            else:
                new_size = max(required, len(self._writebuf) * 2, MAX_PACKET_SIZE + HEADER_SIZE)
            new_buf = bytearray(new_size)
            new_buf[:len(self._writebuf)] = self._writebuf
            self._writebuf = new_buf
            self._write_view = memoryview(self._writebuf)
    
    def write_byte(self, value: int) -> None:
        """Write a single byte to the write buffer"""
        self._ensure_write_capacity(1)
        self._write_view[self._write_pos] = value
        self._write_pos += 1
    
    def write_bytes(self, data: bytes) -> None:
        """Write bytes to the write buffer"""
        length = len(data)
        self._ensure_write_capacity(length)
        self._write_view[self._write_pos:self._write_pos + length] = data
        self._write_pos += length
    
    def write_string(self, text: str, encoding: str = 'utf-8') -> None:
        """Write string to the write buffer"""
        encoded = text.encode(encoding)
        self.write_bytes(encoded)
    
    def write_uint16(self, data: int) -> None:
        """Write a 16-bit integer to the write buffer"""
        self._ensure_write_capacity(2)
        self._write_view[self._write_pos:self._write_pos + 2] = struct.pack('<H', data)
        self._write_pos += 2
    
    def write_uint24(self, data: int) -> None:
        """Write a 24-bit integer to the write buffer"""
        self._ensure_write_capacity(3)
        self._write_view[self._write_pos:self._write_pos + 3] = struct.pack('<I', data)[:3]
        self._write_pos += 3
    
    def write_uint32(self, data: int) -> None:
        """Write a 32-bit unsigned integer to the write buffer"""
        self._ensure_write_capacity(4)
        self._write_view[self._write_pos:self._write_pos + 4] = struct.pack('<I', data)
        self._write_pos += 4
    
    def write_uint64(self, data: int) -> None:
        """Write a 64-bit integer to the write buffer"""
        self._ensure_write_capacity(8)
        self._write_view[self._write_pos:self._write_pos + 8] = struct.pack('<Q', data)
        self._write_pos += 8
    
    async def flush(self, packet_type: str = "", end: bool = True) -> None:
        """
        Flush the write buffer to socket with proper MariaDB packet header (async version).
        Handles packet splitting if data exceeds MAX_PACKET_SIZE.
        
        Args:
            packet_type: Packet type for logging (e.g., "COM_QUERY")
            end: Whether to send empty packet if size == MAX_PACKET_SIZE
        """
        seq = self.sequence.increment_and_get()
        packet_size = self._write_pos - HEADER_SIZE
        self._write_view[0:3] = struct.pack('<I', packet_size)[:3]
        self._write_view[3] = seq
        
        # Log if debug enabled
        if logger.isEnabledFor(logging.DEBUG):
            conn_id_str = f"[conn_id={self.connection_id}]" if self.connection_id >= 0 else ""
            packet_type_str = f" {packet_type}" if packet_type else ""
            logger.debug(hex_dump(self._write_view[0:self._write_pos], f"SEND async: {conn_id_str}{packet_type_str}"))
        
        # Send in one write call
        self.writer.write(self._write_view[0:self._write_pos])
        await self.writer.drain()
        
        # Reset write position for next packet
        self._write_pos = HEADER_SIZE
        
        # If we sent a full MAX_PACKET_SIZE packet, send empty packet to signal end
        if end and packet_size == MAX_PACKET_SIZE:
            await self.flush(packet_type)


class SyncWriteStream(BaseWriteStream):
    """Sync write stream implementation using blocking socket operations"""
    
    def __init__(self, sock: socket.socket, connection_id: int = -1):
        """
        Initialize sync write stream
        
        Args:
            sock: Blocking socket
            connection_id: Connection ID for logging
        """
        self.socket: socket.socket = sock
        super().__init__(connection_id)
    
    def _ensure_write_capacity(self, additional: int) -> None:
        """Ensure write buffer has capacity for additional bytes"""
        required = self._write_pos + additional
        if required > len(self._writebuf):
            new_size = max(required, len(self._writebuf) * 2, MAX_PACKET_SIZE + HEADER_SIZE)
            new_buf = bytearray(new_size)
            new_buf[:len(self._writebuf)] = self._writebuf
            self._writebuf = new_buf
            self._write_view = memoryview(self._writebuf)
    
    def write_byte(self, value: int) -> None:
        """Write a single byte to the write buffer"""
        self._ensure_write_capacity(1)
        if self._write_pos + 1 > len(self._writebuf):
            self.write_bytes([value])
            return
        self._write_view[self._write_pos] = value
        self._write_pos += 1
    
    def write_bytes(self, data: bytes) -> None:
        """Write bytes to the write buffer"""
        length = len(data)
        self._ensure_write_capacity(length)
        if self._write_pos + length > len(self._writebuf):
            init_pos = 0
            remaining = len(data)
            while remaining > 0:
                write_length = min(remaining, len(self._writebuf) - self._write_pos)
                self._write_view[self._write_pos:self._write_pos + write_length] = data[init_pos:init_pos + write_length]
                self.flush(False)
                init_pos += write_length
                remaining -= write_length
            return
        self._write_view[self._write_pos:self._write_pos + length] = data
        self._write_pos += length
    
    def write_string(self, text: str, encoding: str = 'utf-8') -> None:
        """Write string to the write buffer"""
        encoded = text.encode(encoding)
        self.write_bytes(encoded)
    
    def write_uint16(self, data: int) -> None:
        """Write a 16-bit integer to the write buffer"""
        self._ensure_write_capacity(2)
        if self._write_pos + 1 > len(self._writebuf):
            bytes_data = struct.pack('<H', data)
            self.write_bytes(bytes_data)
            return
        
        self._write_view[self._write_pos:self._write_pos + 2] = struct.pack('<H', data)
        self._write_pos += 2
    
    def write_uint24(self, data: int) -> None:
        """Write a 24-bit integer to the write buffer"""
        self._ensure_write_capacity(3)
        if self._write_pos + 1 > len(self._writebuf):
            bytes_data = struct.pack('<I', data)[:3]
            self.write_bytes(bytes_data)
            return
        
        self._write_view[self._write_pos:self._write_pos + 3] = struct.pack('<I', data)[:3]
        self._write_pos += 3
    
    def write_uint32(self, data: int) -> None:
        """Write a 32-bit unsigned integer to the write buffer"""
        self._ensure_write_capacity(4)
        if self._write_pos + 1 > len(self._writebuf):
            bytes_data = struct.pack('<I', data)
            self.write_bytes(bytes_data)
            return
        
        self._write_view[self._write_pos:self._write_pos + 4] = struct.pack('<I', data)
        self._write_pos += 4
    
    def write_uint64(self, data: int) -> None:
        """Write a 64-bit integer to the write buffer"""
        self._ensure_write_capacity(8)
        if self._write_pos + 1 > len(self._writebuf):
            bytes_data = struct.pack('<Q', data)
            self.write_bytes(bytes_data)
            return
        
        self._write_view[self._write_pos:self._write_pos + 8] = struct.pack('<Q', data)
        self._write_pos += 8
    
    def flush(self, packet_type: str = "", end: bool = True) -> None:
        """
        Flush the write buffer to socket with proper MariaDB packet header (sync version).
        
        Args:
            packet_type: Packet type for logging (e.g., "COM_QUERY")
            end: Whether to send empty packet if size == MAX_PACKET_SIZE
        """
        seq = self.sequence.increment_and_get()
        packet_size = self._write_pos - HEADER_SIZE
        self._write_view[0:3] = struct.pack('<I', packet_size)[:3]
        self._write_view[3] = seq
        
        # Log if debug enabled
        if logger.isEnabledFor(logging.DEBUG):
            conn_id_str = f"[conn_id={self.connection_id}]" if self.connection_id >= 0 else ""
            packet_type_str = f" {packet_type}" if packet_type else ""
            logger.debug(hex_dump(self._write_view[0:self._write_pos], f"SEND sync: {conn_id_str}{packet_type_str}"))
        
        # Send in one syscall
        self.socket.sendall(self._write_view[0:self._write_pos])
        
        # Reset write position for next packet
        self._write_pos = HEADER_SIZE
        
        # If we sent a full MAX_PACKET_SIZE packet, send empty packet to signal end
        if end and packet_size == MAX_PACKET_SIZE:
            self.flush(packet_type)
