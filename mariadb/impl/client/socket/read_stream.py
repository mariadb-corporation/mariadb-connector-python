"""
Read stream interfaces for socket I/O operations (async and sync)
"""

from abc import ABC, abstractmethod
import asyncio
import socket
import logging
from typing import Union

from .mutable_int import MutableInt
from ...debug_utils import hex_dump

# Initial buffer size for read buffers
initial_buffer_size = 8192

logger = logging.getLogger(__name__)

HEADER_SIZE = 4
MAX_PACKET_SIZE = 0xFFFFFF


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
    
    def __init__(self, data: Union[memoryview, bytearray], is_view: bool, stream: 'SyncReadStream' = None):
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


class BaseReadStream(ABC):
    """Base class for read stream operations"""
    
    def __init__(self, connection_id: int = -1, max_allowed_packet: int = MAX_PACKET_SIZE):
        """
        Initialize read stream
        
        Args:
            connection_id: Connection ID for logging
            max_allowed_packet: Maximum allowed packet size
        """
        self.connection_id: int = connection_id
        self.max_allowed_packet: int = max_allowed_packet
        self.sequence: MutableInt = MutableInt(-1)
        
        self._readbuf: bytearray = bytearray(initial_buffer_size)
        self._read_view: memoryview = memoryview(self._readbuf)
        self._buffer_in_use: bool = False  # Track if buffer is borrowed
    
    @abstractmethod
    def read_payload(self) -> PacketBuffer:
        """Read one complete MariaDB logical packet"""
        ...
    
    def reset_sequence(self) -> None:
        """Reset packet sequence number"""
        self.sequence.set(0)


class AsyncReadStream(BaseReadStream):
    """Async read stream implementation using asyncio socket operations"""
    
    def __init__(self, reader: asyncio.StreamReader, connection_id: int = -1):
        """
        Initialize async read stream
        
        Args:
            reader: Asyncio stream reader
            connection_id: Connection ID for logging
        """
        self.reader: asyncio.StreamReader = reader
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


class SyncReadStream(BaseReadStream):
    """
    Sync read stream implementation using blocking socket operations
    
    Uses zero-copy optimization for single-packet responses (99.9999% of cases)
    by returning a memoryview of the internal buffer. Callers must explicitly
    release the buffer via packet.release().
    """
    
    def __init__(self, sock: socket.socket, connection_id: int = -1):
        """
        Initialize sync read stream
        
        Args:
            sock: Blocking socket
            connection_id: Connection ID for logging
        """
        self.socket: socket.socket = sock
        super().__init__(connection_id)
    
    def _recv_exact(self, size: int, dest_offset: int) -> memoryview:
        """Read exactly `size` bytes into buffer at offset."""
        view = self._read_view[dest_offset:dest_offset + size]
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
            self._read_view = memoryview(self._readbuf)
    
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
            view = self._read_view[4:pkt_len + 4]
            return PacketBuffer(view, True, self)
        
        # Slow path: multiple packets (rare)
        # Allocate new buffer and return owned data
        result = bytearray(pkt_len * 2)  # Pre-allocate with estimate
        result[:pkt_len] = self._read_view[4:pkt_len + 4]
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
            result[result_len:result_len + pkt_len] = self._read_view[4:pkt_len + 4]
            result_len += pkt_len
            
            # Continuation condition
            if pkt_len < MAX_PACKET_SIZE:
                break
        
        # Trim to actual size
        del result[result_len:]
        # Multi-packet returns owned buffer (no release needed, but release() is safe to call)
        return PacketBuffer(result, False, None)
    
    def _release_buffer(self) -> None:
        """Mark internal buffer as available for reuse (called by PacketBuffer.release())"""
        self._buffer_in_use = False
