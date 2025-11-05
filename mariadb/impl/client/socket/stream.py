"""
Stream interfaces for socket I/O operations (async and sync)
"""

import asyncio
import socket
import struct
import logging

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
        self.reader = reader
        self.writer = writer
        self._closed = False
        self.sequence = 0
        self.connection_id = connection_id
    
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
            sequence = header[3]
            
            # Read payload chunk
            payload = await self.reader.readexactly(payload_length)
            
            # Log individual packet with header if debug enabled
            if logger.isEnabledFor(logging.DEBUG):
                conn_id_str = f"[conn_id={self.connection_id}]" if self.connection_id >= 0 else ""
                # Combine header and payload for logging
                full_packet = header + payload
                logger.debug(hex_dump(full_packet, f"RECV async: {conn_id_str}"))
            
            result.extend(payload)
            
            # Update sequence number
            self.sequence = (sequence + 1) % 256
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
            self.sequence = 0
            if hasattr(self.writer, 'sequence_comp'):
                self.writer.sequence_comp = 0
        
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
            header = struct.pack('<I', chunk_size)[:3] + bytes([self.sequence])
            
            # Log if debug enabled
            if logger.isEnabledFor(logging.DEBUG):
                conn_id_str = f"[conn_id={self.connection_id}]" if self.connection_id >= 0 else ""
                packet_type_str = f" {packet_type}" if packet_type else ""
                logger.debug(hex_dump(header + chunk, f"SEND async: {conn_id_str}{packet_type_str}"))
            
            # Write header and chunk
            self.writer.write(header + chunk)
            await self.writer.drain()
            
            # Update sequence and offset
            self.sequence = (self.sequence + 1) % 256
            offset += chunk_size
            chunk_count += 1
            if (chunk_size == MAX_PACKET_SIZE and offset == len(data)):
                # send empty packet to signal end of data
                self._send_empty_packet(packet_type)
                break

    def _send_empty_packet(self, packet_type: str = ""):
        header = struct.pack('<I', 0)[:3] + bytes([self.sequence])
        # Log if debug enabled
        if logger.isEnabledFor(logging.DEBUG):
            conn_id_str = f"[conn_id={self.connection_id}]" if self.connection_id >= 0 else ""
            packet_type_str = f" {packet_type}" if packet_type else ""
            logger.debug(hex_dump(header, f"SEND async: {conn_id_str}{packet_type_str}"))
        self.writer.write(header)
        self.sequence = (self.sequence + 1) % 256

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
        self.sequence = 0


class SyncStream():
    """
    Sync stream implementation using blocking socket operations
    """
    
    def __init__(self, sock: socket.socket, connection_id: int = -1):
        """
        Initialize sync socket stream
        
        Args:
            sock: Blocking socket
            connection_id: Connection ID for logging
        """
        self.socket = sock
        self._closed = False
        self.sequence = 0
        self.connection_id = connection_id
    
    def read_payload(self) -> bytearray:
        """
        Read a complete MariaDB packet synchronously
        Handles packets split across multiple 16MB chunks
        
        Returns:
            Packet payload as bytes
        """
        MAX_PACKET_SIZE = 0xFFFFFF
        result = bytearray()
        packet_count = 0
        
        while True:
            # Read packet header (4 bytes: 3 bytes length + 1 byte sequence)
            header = self._recv_exact(4)
            
            # Parse header
            payload_length = struct.unpack('<I', header[:3] + b'\x00')[0]
            sequence = header[3]
            
            # Read payload chunk
            payload = self._recv_exact(payload_length)
            
            # Log individual packet with header if debug enabled
            if logger.isEnabledFor(logging.DEBUG):
                conn_id_str = f"[conn_id={self.connection_id}]" if self.connection_id >= 0 else ""
                # Combine header and payload for logging
                full_packet = header + payload
                logger.debug(hex_dump(full_packet, f"RECV sync: {conn_id_str}"))
            
            result.extend(payload)
            
            # Update sequence number
            self.sequence = (sequence + 1) % 256
            packet_count += 1
            
            # If chunk is less than max size, this is the last chunk
            if payload_length < MAX_PACKET_SIZE:
                break
        
        
        return result
    
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
            self.sequence = 0
            if hasattr(self.socket, 'sequence_comp'):
                self.socket.sequence_comp = 0
        
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
            header = struct.pack('<I', chunk_size)[:3] + bytes([self.sequence])
            
            # Log if debug enabled
            if logger.isEnabledFor(logging.DEBUG):
                conn_id_str = f"[conn_id={self.connection_id}]" if self.connection_id >= 0 else ""
                packet_type_str = f" {packet_type}" if packet_type else ""
                logger.debug(hex_dump(header + chunk, f"SEND sync: {conn_id_str}{packet_type_str}"))

            
            # Write header and chunk
            self.socket.sendall(header + chunk)
            
            # Update sequence and offset
            self.sequence = (self.sequence + 1) % 256
            offset += chunk_size
            chunk_count += 1

            if (chunk_size == MAX_PACKET_SIZE and offset == len(data)):
                # send empty packet to signal end of data
                self._send_empty_packet(packet_type)
                break

    def _send_empty_packet(self, packet_type: str = ""):
        header = struct.pack('<I', 0)[:3] + bytes([self.sequence])
        # Log if debug enabled
        if logger.isEnabledFor(logging.DEBUG):
            conn_id_str = f"[conn_id={self.connection_id}]" if self.connection_id >= 0 else ""
            packet_type_str = f" {packet_type}" if packet_type else ""
            logger.debug(hex_dump(header, f"SEND sync: {conn_id_str}{packet_type_str}"))
        self.socket.sendall(header)
        self.sequence = (self.sequence + 1) % 256


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
        self.sequence = 0
    
    def _recv_exact(self, n: int) -> bytes:
        """
        Receive exactly n bytes from socket
        
        Args:
            n: Number of bytes to receive
            
        Returns:
            Received bytes
            
        Raises:
            IOError: If connection is closed or error occurs
        """
        data = bytearray()
        while len(data) < n:
            chunk = self.socket.recv(n - len(data))
            if not chunk:
                raise IOError("Connection closed while reading")
            data.extend(chunk)
        return bytes(data)
