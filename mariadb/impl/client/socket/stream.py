"""
Stream interfaces for socket I/O operations (async and sync)
"""

import asyncio
import socket
import struct
import logging

from .mutable_int import MutableInt

from ...debug_utils import hex_dump

logger = logging.getLogger(__name__)

class AsyncStream():
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
        """
        self.reader: asyncio.StreamReader = reader
        self.writer: asyncio.StreamWriter = writer
        self._closed: bool = False
        self.sequence: MutableInt = MutableInt(-1)
        self.connection_id: int = connection_id
    
    async def read_payload(self) -> bytearray:
        """
        Read a complete MariaDB packet asynchronously
        Handles packets split across multiple 16MB chunks
        
        Returns:
            Packet payload as bytes
        """
        MAX_PACKET_SIZE = 0xFFFFFF
        result = bytearray()
        packet_count = 0
        
        while True:
            # Read packet header (4 bytes: 3 bytes length + 1 byte sequence)
            header = await self.reader.readexactly(4)
            
            # Parse header
            payload_length = struct.unpack('<I', header[:3] + b'\x00')[0]
            self.sequence.set(header[3])
            
            # Read payload chunk
            payload = await self.reader.readexactly(payload_length)
            
            # Log individual packet with header if debug enabled
            if logger.isEnabledFor(logging.DEBUG):
                conn_id_str = f"[conn_id={self.connection_id}]" if self.connection_id >= 0 else ""
                # Combine header and payload for logging
                full_packet = header + payload
                logger.debug(hex_dump(full_packet, f"RECV async: {conn_id_str}"))
            
            result.extend(payload)
            packet_count += 1
            
            # If chunk is less than max size, this is the last chunk
            if payload_length < MAX_PACKET_SIZE:
                break
        
        return result
    
    async def send_payload(self, data: bytes, packet_type: str = "", reset_sequence: bool = True) -> None:
        """
        Send a complete MariaDB packet asynchronously
        
        Args:
            data: Packet data to write
            packet_type: Packet type for logging (e.g., "COM_QUERY", "COM_QUIT")
            reset_sequence: Whether to reset sequence number to 0 before sending
        """
        # Reset sequence if requested
        if reset_sequence:
            self.sequence.set(-1)
        
        # Split into chunks if needed (max packet size is 16MB - 1)
        MAX_PACKET_SIZE = 0xFFFFFF

        offset = 0
        chunk_count = 0
        if len(data) == 0:
            self._send_empty_packet(packet_type)
            return

        while offset < len(data):
            chunk_size = min(len(data) - offset, MAX_PACKET_SIZE)
            chunk = data[offset:offset + chunk_size]
            
            # Build packet header
            header = struct.pack('<I', chunk_size)[:3] + bytes([self.sequence.increment_and_get()])
            
            # Log if debug enabled
            if logger.isEnabledFor(logging.DEBUG):
                conn_id_str = f"[conn_id={self.connection_id}]" if self.connection_id >= 0 else ""
                packet_type_str = f" {packet_type}" if packet_type else ""
                logger.debug(hex_dump(header + chunk, f"SEND async: {conn_id_str}{packet_type_str}"))
            
            # Write header and chunk
            self.writer.write(header + chunk)
            await self.writer.drain()
            
            # Update sequence and offset
            offset += chunk_size
            chunk_count += 1
            if (chunk_size == MAX_PACKET_SIZE and offset == len(data)):
                # send empty packet to signal end of data
                self._send_empty_packet(packet_type)
                break

    def _send_empty_packet(self, packet_type: str = ""):
        header = struct.pack('<I', 0)[:3] + bytes([self.sequence.increment_and_get()])
        # Log if debug enabled
        if logger.isEnabledFor(logging.DEBUG):
            conn_id_str = f"[conn_id={self.connection_id}]" if self.connection_id >= 0 else ""
            packet_type_str = f" {packet_type}" if packet_type else ""
            logger.debug(hex_dump(header, f"SEND async: {conn_id_str}{packet_type_str}"))
        self.writer.write(header)

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


class SyncStream():
    """
    Sync stream implementation using blocking socket operations
    """
    MAX_PACKET_SIZE = 0xFFFFFF  # 16 MB - 1
    SLICE_SIZE = 16384
 
    def __init__(self, sock: socket.socket, connection_id: int = -1, max_allowed_packet: int = 0xFFFFFF * 0xFE):
        """
        Initialize sync socket stream
        
        Args:
            sock: Blocking socket
            connection_id: Connection ID for logging
        """
        self.socket: socket.socket = sock
        self._closed: bool = False
        self.sequence: MutableInt = MutableInt(-1)
        self.connection_id: int = connection_id

        self.max_allowed_packet = max_allowed_packet
        self._recv_buf: bytearray = bytearray(65536)  # Read chunks up to 64 KB
        self._recv_pos: int = 0   # Current read position
        self._recv_len: int = 0   # Total valid bytes in buffer

        self._payload_accum: bytearray = bytearray(self.SLICE_SIZE)  # Accumulate multi-packet payloads
        self._payload_len = 0

    def read_payload(self) -> bytearray:
        """
        Read a complete MySQL packet and return payload only, using a preallocated buffer.
        Returns a bytearray object for parsing.
        """
        # Reset accumulation buffer
        self._payload_accum.clear()

        while True:
            # Ensure we have at least 4 bytes for the header
            while self._recv_len - self._recv_pos < 4:
                self._fill_recv_buf()

            packet_len = (
                self._recv_buf[self._recv_pos]
                | (self._recv_buf[self._recv_pos + 1] << 8)
                | (self._recv_buf[self._recv_pos + 2] << 16)
            )
            self.sequence.set(self._recv_buf[self._recv_pos + 3])

            total_size = 4 + packet_len
            while self._recv_len - self._recv_pos < total_size:
                self._fill_recv_buf()

            # Extract payload
            start = self._recv_pos + 4
            end = self._recv_pos + total_size
            self._payload_accum.extend(self._recv_buf[start:end])

            self._recv_pos += total_size

            # Reset buffer if fully consumed
            if self._recv_pos == self._recv_len:
                self._recv_pos = 0
                self._recv_len = 0

            # Multi-packet check
            if packet_len < self.MAX_PACKET_SIZE:
                return self._payload_accum

    def _fill_recv_buf(self) -> None:
        """
        Read data from socket into preallocated buffer.
        """
        if self._recv_len == len(self._recv_buf):
            # Shift unconsumed data to the start
            if self._recv_pos > 0:
                remaining = self._recv_len - self._recv_pos
                self._recv_buf[:remaining] = self._recv_buf[self._recv_pos:self._recv_len]
                self._recv_len = remaining
                self._recv_pos = 0
            else:
                # Expand buffer if needed
                new_size = min(len(self._recv_buf) * 2, self.MAX_PACKET_SIZE + 4)
                self._recv_buf.extend(bytearray(new_size - len(self._recv_buf)))

        try:
            # recv_into requires a writable buffer slice
            view = memoryview(self._recv_buf)[self._recv_len:]
            n = self.socket.recv_into(view)
            if n == 0:
                raise OSError("Connection closed by remote host")
            self._recv_len += n
        except socket.error as e:
            raise OSError(f"Failed to receive data: {e}")
    
    def send_payload(self, data: bytes, packet_type: str = "", reset_sequence: bool = True) -> None:
        """
        Send a complete MariaDB packet synchronously
        
        Args:
            data: Packet data to write
            packet_type: Packet type for logging (e.g., "COM_QUERY", "COM_QUIT")
            reset_sequence: Whether to reset sequence number to 0 before sending
        """
        # Reset sequence if requested
        if reset_sequence:
            self.sequence.set(-1)
        
        # Split into chunks if needed (max packet size is 16MB - 1)
        MAX_PACKET_SIZE = 0xFFFFFF
        offset = 0
        chunk_count = 0

        if len(data) == 0:
            self._send_empty_packet(packet_type)
            return
        
        while offset < len(data):
            chunk_size = min(len(data) - offset, MAX_PACKET_SIZE)
            chunk = data[offset:offset + chunk_size]
            
            # Build packet header
            header = struct.pack('<I', chunk_size)[:3] + bytes([self.sequence.increment_and_get()])
            
            # Log if debug enabled
            if logger.isEnabledFor(logging.DEBUG):
                conn_id_str = f"[conn_id={self.connection_id}]" if self.connection_id >= 0 else ""
                packet_type_str = f" {packet_type}" if packet_type else ""
                logger.debug(hex_dump(header + chunk, f"SEND sync: {conn_id_str}{packet_type_str}"))

            
            # Write header and chunk
            self.socket.sendmsg([header,chunk])
            offset += chunk_size
            chunk_count += 1

            if (chunk_size == MAX_PACKET_SIZE and offset == len(data)):
                # send empty packet to signal end of data
                self._send_empty_packet(packet_type)
                break

    def _send_empty_packet(self, packet_type: str = ""):
        header = struct.pack('<I', 0)[:3] + bytes([self.sequence.increment_and_get()])
        # Log if debug enabled
        if logger.isEnabledFor(logging.DEBUG):
            conn_id_str = f"[conn_id={self.connection_id}]" if self.connection_id >= 0 else ""
            packet_type_str = f" {packet_type}" if packet_type else ""
            logger.debug(hex_dump(header, f"SEND sync: {conn_id_str}{packet_type_str}"))
        self.socket.sendall(header)


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
    

