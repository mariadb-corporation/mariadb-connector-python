"""
Stream interfaces for socket I/O operations (async and sync)
"""

from abc import ABC, abstractmethod
import asyncio
import datetime
import socket
import struct
import logging
from typing import Union

from .mutable_int import MutableInt

from ...debug_utils import hex_dump

# Initial buffer size for read/write buffers
initial_buffer_size = 8192

logger = logging.getLogger(__name__)

HEADER_SIZE = 4
MAX_PACKET_SIZE = 0xFFFFFF

SLASH_BYTE: int = b"\\"[0]
QUOTE_BYTE: int = b"'"[0]
DQUOTE_BYTE: int = b"\""[0]
NULL_BYTE: int = b"\0"[0]

class PacketBuffer:
    """
    Wrapper for packet data that tracks whether it needs explicit release.
    Provides both memoryview (zero-copy) and bytearray (owned) interfaces.
    
    For single-packet responses (99.9999% of cases), this wraps a memoryview
    of the stream's internal buffer. For multi-packet responses, it wraps
    an owned bytearray.
    
    IMPORTANT: Callers MUST call .release() when done with the buffer,
    typically in a try/finally block.
    """
    __slots__ = ('_data', '_is_view', '_stream')
    
    def __init__(self, data: Union[memoryview, bytearray], is_view: bool, stream: 'SyncStream' = None):
        self._data = data
        self._is_view = is_view
        self._stream = stream
    
    def __getitem__(self, key):
        return self._data[key]
    
    def __len__(self):
        return len(self._data)    
    
    def release(self) -> None:
        """Release buffer back to stream (only needed for views)"""
        if self._is_view:
            self._stream._release_buffer()
            self._stream = None
    
    def __del__(self):
        """Auto-release on garbage collection (safety net)"""
        if self._is_view and self._stream:
            self.release()

class BaseStream(ABC):
    def __init__(self, connection_id: int = -1, max_allowed_packet: int = MAX_PACKET_SIZE):
        """
        Initialize async socket stream
        
        Args:
            connection_id: Connection ID for logging
        """
        self._closed: bool = False
        self.sequence: MutableInt = MutableInt(-1)
        self.connection_id: int = connection_id
        self.max_allowed_packet: int = max_allowed_packet

        self._readbuf: bytearray = bytearray(initial_buffer_size)
        self._view: memoryview = memoryview(self._readbuf)
        self._buffer_in_use: bool = False  # Track if buffer is borrowed
        self.header: bytearray = bytearray(4)
        self._header_view: memoryview = memoryview(self.header)

        self._writebuf: bytearray = bytearray(initial_buffer_size)
        self._write_pos: int = HEADER_SIZE  # Start after header
        self._write_start: int = HEADER_SIZE  # Track start of current packet
    
    # =========================================================================
    # Streaming Write API - Zero-copy direct writes
    # =========================================================================
    
    @abstractmethod
    def read_payload(self) -> PacketBuffer:
        ...

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
                if byte == QUOTE_BYTE or byte == QUOTE_BYTE or byte == NULL_BYTE or byte == SLASH_BYTE:
                    self.write_byte(SLASH_BYTE)
                self.write_byte(byte)

    
    def write_length_encoded_string(self, text: str, encoding: str = 'utf-8') -> None:
        encoded = text.encode(encoding)
        self.write_length_encoded_int(len(encoded))
        self.write_bytes(encoded)

    def write_length_encoded_bytes(self, data: bytes) -> None:
        self.write_length_encoded_int(len(data))
        self.write_bytes(data)
    
    def write_length_encoded_int(self, len: int) -> None:    
        if len < 251:
            self.write_byte(len)
        elif len < 65536:
            self.write_byte(0xfc)
            self.write_uint16(len)
        elif len < 16777216:
            self.write_byte(0xfd)
            self.write_uint24(len)
        else:
            self.write_byte(0xfe)
            self.write_uint64(len)
    
    @abstractmethod
    def flush(self, packet_type: str = "", end: bool = True) -> None:
        """Flush write buffer to socket (subclass implements I/O)"""
        ...

class AsyncStream(BaseStream):
    """
    Async stream implementation using asyncio socket operations
    """
    
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, connection_id: int = -1):
        """
        Initialize async socket stream
        
        Args:
            reader: Asyncio stream reader
            writer: Asyncio stream writer
            connection_id: Connection ID for logging
            max_allowed_packet: Maximum allowed packet size
        """
        self.reader: asyncio.StreamReader = reader
        self.writer: asyncio.StreamWriter = writer
        super().__init__(connection_id)
    
    async def read_payload(self) -> PacketBuffer:
        """
        Read one complete MariaDB logical packet (may consist of multiple sub-packets).
        
        Returns:
            PacketBuffer wrapping owned bytearray (async always owns data, no zero-copy)
            
        Note: For async, the buffer is always owned (is_view=False) since asyncio.StreamReader
        doesn't support zero-copy recv_into(). The release() call is still required for API
        consistency but is a no-op for owned buffers.
        """
        # Read first packet header
        header = await self.reader.readexactly(HEADER_SIZE)
        pkt_len = header[0] | (header[1] << 8) | (header[2] << 16)
        self.sequence.set(header[3])
        
        # Read first payload chunk
        payload = await self.reader.readexactly(pkt_len)
        
        # Log if debug enabled
        if logger.isEnabledFor(logging.DEBUG):
            conn_id_str = f"[conn_id={self.connection_id}]" if self.connection_id >= 0 else ""
            full_packet = header + payload
            logger.debug(hex_dump(full_packet, f"RECV async: {conn_id_str}"))
        
        # Fast path: single packet (99.9999% of cases)
        # Return owned bytearray (async cannot do zero-copy)
        if pkt_len < MAX_PACKET_SIZE:
            return PacketBuffer(bytearray(payload), False, None)
        
        # Slow path: multiple packets (rare)
        # Pre-allocate buffer with estimate
        result = bytearray(pkt_len * 2)
        result[:pkt_len] = payload
        result_len = pkt_len
        
        while True:
            # Read next packet header
            header = await self.reader.readexactly(HEADER_SIZE)
            pkt_len = header[0] | (header[1] << 8) | (header[2] << 16)
            self.sequence.set(header[3])
            
            # Read payload chunk
            payload = await self.reader.readexactly(pkt_len)
            
            # Log if debug enabled
            if logger.isEnabledFor(logging.DEBUG):
                conn_id_str = f"[conn_id={self.connection_id}]" if self.connection_id >= 0 else ""
                full_packet = header + payload
                logger.debug(hex_dump(full_packet, f"RECV async: {conn_id_str}"))
            
            # Ensure result buffer has enough space
            needed = result_len + pkt_len
            if needed > len(result):
                # Grow buffer
                new_size = max(needed, len(result) * 2)
                result.extend(bytearray(new_size - len(result)))
            
            # Copy payload to result
            result[result_len:result_len + pkt_len] = payload
            result_len += pkt_len
            
            # Continuation condition
            if pkt_len < MAX_PACKET_SIZE:
                break
        
        # Trim to actual size
        del result[result_len:]
        # Async always returns owned buffer (no zero-copy possible with asyncio)
        return PacketBuffer(result, False, None)
    
    def _ensure_write_capacity(self, additional: int) -> None:
        """Ensure write buffer has capacity for additional bytes"""
        required = self._write_pos + additional
        if required > len(self._writebuf):
            if (required > MAX_PACKET_SIZE + HEADER_SIZE):
                new_size = max(required, len(self._writebuf) * 1.5)
            else:
                new_size = max(required, len(self._writebuf) * 2, MAX_PACKET_SIZE + HEADER_SIZE)
            new_buf = bytearray(new_size)
            new_buf[:len(self._writebuf)] = self._writebuf
            self._writebuf = new_buf
    
    def write_byte(self, value: int) -> None:
        """Write a single byte to the write buffer"""
        self._ensure_write_capacity(1)
        self._writebuf[self._write_pos] = value
        self._write_pos += 1
    
    def write_bytes(self, data: bytes) -> None:
        """Write bytes to the write buffer"""
        length = len(data)
        self._ensure_write_capacity(length)
        self._writebuf[self._write_pos:self._write_pos + length] = data
        self._write_pos += length
    
    def write_string(self, text: str, encoding: str = 'utf-8') -> None:
        """Write string to the write buffer"""
        encoded = text.encode(encoding)
        self.write_bytes(encoded)
    
    def write_uint16(self, data: int) -> None:
        """Write a 16-bit integer to the write buffer"""
        self._ensure_write_capacity(2)
        self._writebuf[self._write_pos:self._write_pos + 2] = struct.pack('<H', data)
        self._write_pos += 2
    
    def write_uint24(self, data: int) -> None:
        """Write a 24-bit integer to the write buffer"""
        self._ensure_write_capacity(3)
        self._writebuf[self._write_pos:self._write_pos + 3] = struct.pack('<I', data)[:3]
        self._write_pos += 3
    
    def write_uint32(self, data: int) -> None:
        """Write a 32-bit unsigned integer to the write buffer"""
        self._ensure_write_capacity(4)
        self._writebuf[self._write_pos:self._write_pos + 4] = struct.pack('<I', data)
        self._write_pos += 4
    
    def write_uint64(self, data: int) -> None:
        """Write a 64-bit integer to the write buffer"""
        self._ensure_write_capacity(8)
        self._writebuf[self._write_pos:self._write_pos + 8] = struct.pack('<Q', data)
        self._write_pos += 8


    async def flush(self, packet_type: str = "", end: bool = True) -> None:
        """
        Flush the write buffer to socket with proper MariaDB packet header (async version).
        Handles packet splitting if data exceeds MAX_PACKET_SIZE.
        
        Args:
            packet_type: Packet type for logging (e.g., "COM_QUERY")
        """
        seq = self.sequence.increment_and_get()
        packet_size = self._write_pos - HEADER_SIZE
        self._writebuf[0] = packet_size & 0xFF
        self._writebuf[1] = (packet_size >> 8) & 0xFF
        self._writebuf[2] = (packet_size >> 16) & 0xFF
        self._writebuf[3] = seq
        
        # Log if debug enabled
        if logger.isEnabledFor(logging.DEBUG):
            conn_id_str = f"[conn_id={self.connection_id}]" if self.connection_id >= 0 else ""
            packet_type_str = f" {packet_type}" if packet_type else ""
            logger.debug(hex_dump(self._writebuf[0:self._write_pos], f"SEND async: {conn_id_str}{packet_type_str}"))
        
        # Send in one write call
        self.writer.write(self._writebuf[0:self._write_pos])
        await self.writer.drain()
        
        # Reset write position for next packet
        self._write_pos = HEADER_SIZE
        
        # If we sent a full MAX_PACKET_SIZE packet, send empty packet to signal end
        if end and packet_size == MAX_PACKET_SIZE:
            await self.flush(packet_type)

    async def close(self) -> None:
        """Close the stream asynchronously"""
        if not self._closed:
            self.writer.close()
            await self.writer.wait_closed()
            self._closed = True
    
    def is_closed(self) -> bool:
        """Check if stream is closed"""
        return self._closed
    
    def reset_sequence(self) -> None:
        """Reset packet sequence number"""
        self.sequence.set(0)


class SyncStream(BaseStream):
    """
    Sync stream implementation using blocking socket operations
    
    Uses zero-copy optimization for single-packet responses (99.9999% of cases)
    by returning a memoryview of the internal buffer. Callers must explicitly
    release the buffer via packet.release().
    """
    
    
    def __init__(self, sock: socket.socket, connection_id: int = -1):
        """
        Initialize sync socket stream
        
        Args:
            sock: Blocking socket
            connection_id: Connection ID for logging
        """
        self.socket: socket.socket = sock

        super().__init__(connection_id)

    def _recv_exact(self, size: int, dest_offset: int) -> memoryview:
        """Read exactly `size` bytes into buffer at offset."""
        view = self._view[dest_offset:dest_offset + size]
        received = 0
        while received < size:
            n = self.socket.recv_into(view[received:])
            if n == 0:
                raise ConnectionError("Connection closed by peer")
            received += n
        return view

    def _ensure_read_capacity(self, size: int) -> None:
        """Ensure buffer is large enough, within max_allowed_packet limit."""
        if size > len(self._readbuf):
            new_size = min(self.max_allowed_packet + 4, max(size, len(self._readbuf) * 2))
            new_buf = bytearray(new_size)
            new_buf[:len(self._readbuf)] = self._readbuf
            self._readbuf = new_buf
            self._view = memoryview(self._readbuf)

    def read_payload(self) -> PacketBuffer:
        """
        Read one complete MariaDB logical packet (may consist of multiple sub-packets).
        
        Returns:
            PacketBuffer that must be released via .release() when done
            
        IMPORTANT: Caller MUST call .release() on the returned buffer,
        typically in a try/finally block:
        
            packet = stream.read_payload()
            try:
                # Use packet...
            finally:
                packet.release()
        
        For single-packet responses (99.9999% of cases), returns a zero-copy
        memoryview of the internal buffer. For multi-packet responses, returns
        an owned bytearray that doesn't need explicit release.
        """
        if self._buffer_in_use:
            raise RuntimeError(
                "Previous packet buffer not released! Call packet.release() before reading next packet."
            )
        
        # Read first packet to determine if we need continuation
        self._recv_exact(4, 0)
        pkt_len = self._readbuf[0] | (self._readbuf[1] << 8) | (self._readbuf[2] << 16)
        self.sequence.set(self._readbuf[3])

        # Read first payload chunk
        self._ensure_read_capacity(pkt_len + 4)
        self._recv_exact(pkt_len, 4)

        # Log if debug enabled
        if logger.isEnabledFor(logging.DEBUG):
            conn_id_str = f"[conn_id={self.connection_id}]" if self.connection_id >= 0 else ""
            logger.debug(hex_dump(self._readbuf[0:pkt_len + 4], f"RECV sync: {conn_id_str}"))

        # Fast path: single packet (99.9999% of cases)
        # Return zero-copy view of internal buffer
        if pkt_len < MAX_PACKET_SIZE:
            self._buffer_in_use = True
            view = self._view[4:pkt_len + 4]
            return PacketBuffer(view, True, self)

        # Slow path: multiple packets (rare)
        # Allocate new buffer and return owned data
        result = bytearray(pkt_len * 2)  # Pre-allocate with estimate
        result[:pkt_len] = self._view[4:pkt_len + 4]
        result_len = pkt_len

        while True:
            # Read next packet header
            self._recv_exact(4, 0)
            pkt_len = self._readbuf[0] | (self._readbuf[1] << 8) | (self._readbuf[2] << 16)
            self.sequence.set(self._readbuf[3])

            # Read payload chunk
            self._ensure_read_capacity(pkt_len + 4)
            self._recv_exact(pkt_len, 4)

            # Log if debug enabled
            if logger.isEnabledFor(logging.DEBUG):
                conn_id_str = f"[conn_id={self.connection_id}]" if self.connection_id >= 0 else ""
                logger.debug(hex_dump(self._readbuf[0:pkt_len + 4], f"RECV sync: {conn_id_str}"))

            # Ensure result buffer has enough space
            needed = result_len + pkt_len
            if needed > len(result):
                # Grow buffer
                new_size = max(needed, len(result) * 2)
                result.extend(bytearray(new_size - len(result)))

            # Copy payload to result
            result[result_len:result_len + pkt_len] = self._view[4:pkt_len + 4]
            result_len += pkt_len

            # Continuation condition
            if pkt_len < self.MAX_PACKET_SIZE:
                break

        # Trim to actual size
        del result[result_len:]
        # Multi-packet returns owned buffer (no release needed, but release() is safe to call)
        return PacketBuffer(result, False, None)

    def close(self) -> None:
        """Close the stream synchronously"""
        if not self._closed:
            try:
                self.socket.close()
            except Exception:
                pass
            self._closed = True
    
    def is_closed(self) -> bool:
        """Check if stream is closed"""
        return self._closed
    
    def reset_sequence(self) -> None:
        """Reset packet sequence number"""
        self.sequence.set(-1)
    
    def _ensure_write_capacity(self, additional: int) -> None:
        """Ensure write buffer has capacity for additional bytes"""
        required = self._write_pos + additional
        if required > len(self._writebuf):
            new_size = max(required, len(self._writebuf) * 2, MAX_PACKET_SIZE + HEADER_SIZE)
            new_buf = bytearray(new_size)
            new_buf[:len(self._writebuf)] = self._writebuf
            self._writebuf = new_buf

    def write_byte(self, value: int) -> None:
        """Write a single byte to the write buffer"""
        self._ensure_write_capacity(1)
        if self._write_pos + 1 > len(self._writebuf):
            self.write_bytes([value])
            return 
        self._writebuf[self._write_pos] = value
        self._write_pos += 1
    
    def write_bytes(self, data: bytes) -> None:
        """Write bytes to the write buffer"""
        length = len(data)
        self._ensure_write_capacity(length)
        if self._write_pos + length > len(self._writebuf):
            init_pos = 0
            remaining = len(data)
            while remaining > 0:
                write_length = min(remaining, len(self._writebuf)-self._write_pos)
                self._writebuf[self._write_pos:self._write_pos + write_length] = data[init_pos:init_pos + write_length]
                self.flush(False)
                init_pos += write_length
                remaining -= write_length
            return
        self._writebuf[self._write_pos:self._write_pos + length] = data
        self._write_pos += length
    
    def write_string(self, text: str, encoding: str = 'utf-8') -> None:
        """Write string to the write buffer"""
        encoded = text.encode(encoding)
        self.write_bytes(encoded)
    
    def write_uint16(self, data: int) -> None:
        """Write a 16-bit integer to the write buffer"""
        self._ensure_write_capacity(2)
        if self._write_pos + 1 > len(self._writebuf):
            bytes = struct.pack('<H', data)
            self.write_bytes(bytes)
            return 
        
        self._writebuf[self._write_pos:self._write_pos + 2] = struct.pack('<H', data)
        self._write_pos += 2
    
    def write_uint24(self, data: int) -> None:
        """Write a 24-bit integer to the write buffer"""
        self._ensure_write_capacity(3)
        if self._write_pos + 1 > len(self._writebuf):
            bytes = struct.pack('<I', data)[:3]
            self.write_bytes(bytes)
            return 
        
        self._writebuf[self._write_pos:self._write_pos + 3] = struct.pack('<I', data)[:3]
        self._write_pos += 3
    
    def write_uint32(self, data: int) -> None:
        """Write a 32-bit unsigned integer to the write buffer"""
        self._ensure_write_capacity(4)
        if self._write_pos + 1 > len(self._writebuf):
            bytes = struct.pack('<I', data)
            self.write_bytes(bytes)
            return 
        
        self._writebuf[self._write_pos:self._write_pos + 4] = struct.pack('<I', data)
        self._write_pos += 4
    
    def write_uint64(self, data: int) -> None:
        """Write a 64-bit integer to the write buffer"""
        self._ensure_write_capacity(8)
        if self._write_pos + 1 > len(self._writebuf):
            bytes = struct.pack('<Q', data)
            self.write_bytes(bytes)
            return 
        
        self._writebuf[self._write_pos:self._write_pos + 8] = struct.pack('<Q', data)
        self._write_pos += 8
    

    def flush(self, packet_type: str = "", end: bool = True) -> None:
        """
        Flush the write buffer to socket with proper MariaDB packet header (sync version).
        
        Args:
            packet_type: Packet type for logging (e.g., "COM_QUERY")
        """
        seq = self.sequence.increment_and_get()
        packet_size = self._write_pos - HEADER_SIZE
        self._writebuf[0] = packet_size & 0xFF
        self._writebuf[1] = (packet_size >> 8) & 0xFF
        self._writebuf[2] = (packet_size >> 16) & 0xFF
        self._writebuf[3] = seq
        
        # Log if debug enabled
        if logger.isEnabledFor(logging.DEBUG):
            conn_id_str = f"[conn_id={self.connection_id}]" if self.connection_id >= 0 else ""
            packet_type_str = f" {packet_type}" if packet_type else ""
            logger.debug(hex_dump(self._writebuf[0:self._write_pos], f"SEND sync: {conn_id_str}{packet_type_str}"))
        
        # Send in one syscall
        self.socket.sendall(self._writebuf[0:self._write_pos])
        
        # Reset write position for next packet
        self._write_pos = HEADER_SIZE
        
        # If we sent a full MAX_PACKET_SIZE packet, send empty packet to signal end
        if end and packet_size == MAX_PACKET_SIZE:
            self.flush(packet_type)
    
    def _release_buffer(self) -> None:
        """Mark internal buffer as available for reuse (called by PacketBuffer.release())"""
        self._buffer_in_use = False

