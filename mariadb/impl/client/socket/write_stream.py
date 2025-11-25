"""
Write stream interfaces for socket I/O operations (async and sync)
"""

from abc import ABC, abstractmethod
import asyncio
import socket
import logging

from .mutable_int import MutableInt
from ...debug_utils import hex_dump

logger = logging.getLogger(__name__)

HEADER_SIZE = 4
MAX_PACKET_SIZE = 0xFFFFFF


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
    
    @abstractmethod
    def write_payload(self, payload: bytes, packet_type: str = "", reset_sequence: bool = True) -> None:
        """
        Write payload with MariaDB packet framing
        
        Args:
            payload: Payload bytes to send
            packet_type: Packet type for logging (e.g., "COM_QUERY")
            reset_sequence: Whether to reset sequence number before sending
        """
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
    
    async def write_payload(self, payload: bytes, packet_type: str = "", reset_sequence: bool = True) -> None:
        """
        Write payload with MariaDB packet framing (async version)
        
        Args:
            payload: Payload bytes to send
            packet_type: Packet type for logging (e.g., "COM_QUERY")
            reset_sequence: Whether to reset sequence number before sending
        """
        if reset_sequence:
            self.sequence.set(-1)
        
        payload_len = len(payload)
        offset = 0
        
        # Handle empty payload - still need to send header
        if payload_len == 0:
            seq = self.sequence.increment_and_get()
            header = b'\x00\x00\x00' + bytes([seq])
            
            if logger.isEnabledFor(logging.DEBUG):
                conn_id_str = f"[conn_id={self.connection_id}]" if self.connection_id >= 0 else ""
                packet_type_str = f" {packet_type}" if packet_type else ""
                logger.debug(hex_dump(header, f"SEND async: {conn_id_str}{packet_type_str}"))
            
            self.writer.write(header)
            await self.writer.drain()
            return
        
        # Handle packet splitting for large payloads
        while offset < payload_len:
            chunk_size = min(MAX_PACKET_SIZE, payload_len - offset)
            seq = self.sequence.increment_and_get()
            
            # Build header: 3-byte length + 1-byte sequence
            header = chunk_size.to_bytes(3, 'little') + bytes([seq])
            
            # Log if debug enabled (need to build full packet for logging)
            if logger.isEnabledFor(logging.DEBUG):
                chunk = payload[offset:offset + chunk_size]
                packet = header + chunk
                conn_id_str = f"[conn_id={self.connection_id}]" if self.connection_id >= 0 else ""
                packet_type_str = f" {packet_type}" if packet_type else ""
                logger.debug(hex_dump(packet, f"SEND async: {conn_id_str}{packet_type_str}"))
            
            # Send header and chunk separately (more efficient - no concatenation)
            self.writer.write(header)
            self.writer.write(payload[offset:offset + chunk_size])
            offset += chunk_size
        
        # Flush all buffered data
        await self.writer.drain()
        
        # If last packet was exactly MAX_PACKET_SIZE, send empty packet to signal end
        if payload_len % MAX_PACKET_SIZE == 0:
            seq = self.sequence.increment_and_get()
            header = b'\x00\x00\x00' + bytes([seq])
            self.writer.write(header)
            await self.writer.drain()


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
    
    def write_payload(self, payload: bytes, packet_type: str = "", reset_sequence: bool = True) -> None:
        """
        Write payload with MariaDB packet framing (sync version)
        
        Args:
            payload: Payload bytes to send
            packet_type: Packet type for logging (e.g., "COM_QUERY")
            reset_sequence: Whether to reset sequence number before sending
        """
        if reset_sequence:
            self.sequence.set(-1)
        
        payload_len = len(payload)
        offset = 0
        
        # Handle empty payload - still need to send header
        if payload_len == 0:
            seq = self.sequence.increment_and_get()
            header = b'\x00\x00\x00' + bytes([seq])
            
            if logger.isEnabledFor(logging.DEBUG):
                conn_id_str = f"[conn_id={self.connection_id}]" if self.connection_id >= 0 else ""
                packet_type_str = f" {packet_type}" if packet_type else ""
                logger.debug(hex_dump(header, f"SEND sync: {conn_id_str}{packet_type_str}"))
            
            self.socket.sendall(header)
            return
        
        # Handle packet splitting for large payloads
        while offset < payload_len:
            chunk_size = min(MAX_PACKET_SIZE, payload_len - offset)
            seq = self.sequence.increment_and_get()
            
            # Build header: 3-byte length + 1-byte sequence
            header = chunk_size.to_bytes(3, 'little') + bytes([seq])
            chunk = payload[offset:offset + chunk_size]
            
            # Log if debug enabled (need full packet for logging)
            if logger.isEnabledFor(logging.DEBUG):
                packet = header + chunk
                conn_id_str = f"[conn_id={self.connection_id}]" if self.connection_id >= 0 else ""
                packet_type_str = f" {packet_type}" if packet_type else ""
                logger.debug(hex_dump(packet, f"SEND sync: {conn_id_str}{packet_type_str}"))
            
            # Send header and chunk in a single syscall using scatter-gather I/O
            # sendmsg() is available on Unix and sends multiple buffers efficiently
            try:
                self.socket.sendmsg([header, chunk])
            except Exception:
                # Fallback for platforms without sendmsg (e.g., Windows)
                self.socket.sendall(header)
                self.socket.sendall(chunk)
            
            offset += chunk_size
        
        # If last packet was exactly MAX_PACKET_SIZE, send empty packet to signal end
        if payload_len % MAX_PACKET_SIZE == 0:
            seq = self.sequence.increment_and_get()
            header = b'\x00\x00\x00' + bytes([seq])
            self.socket.sendall(header)
