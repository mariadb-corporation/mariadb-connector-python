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
    def write_payload(self, payload: bytearray, packet_type: str = "", reset_sequence: bool = True) -> None:
        """
        Write payload with MariaDB packet framing
        
        Args:
            payload: Payload bytearray to send (first 4 bytes reserved for header)
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
    
    async def write_payload(self, payload: bytearray, packet_type: str = "", reset_sequence: bool = True) -> None:
        """
        Write payload with MariaDB packet framing (async version)
        
        Args:
            payload: Payload bytearray with first 4 bytes reserved for header
            packet_type: Packet type for logging (e.g., "COM_QUERY")
            reset_sequence: Whether to reset sequence number before sending
        """
        if reset_sequence:
            self.sequence.set(-1)
        
        # Payload has 4 bytes reserved at start for header
        payload_len = len(payload) - 4
        data_offset = 4  # Data starts after reserved header space
        
        # Handle empty payload - still need to send header
        if payload_len == 0:
            seq = self.sequence.increment_and_get()
            # Write header into first 4 bytes
            payload[0:3] = b'\x00\x00\x00'
            payload[3] = seq

            if logger.isEnabledFor(logging.DEBUG):
                conn_id_str = f"[conn_id={self.connection_id}]" if self.connection_id >= 0 else ""
                packet_type_str = f" {packet_type}" if packet_type else ""
                logger.debug(hex_dump(bytes(payload[0:4]), f"SEND async: {conn_id_str}{packet_type_str}"))
            
            self.writer.write(payload[0:4])
            await self.writer.drain()
            return
        
        # Use memoryview to avoid buffer copies when slicing
        payload_view = memoryview(payload)
        
        # Handle packet splitting for large payloads
        sent = 0
        
        while sent < payload_len:
            chunk_size = min(MAX_PACKET_SIZE, payload_len - sent)
            seq = self.sequence.increment_and_get()
            
            # Data for this chunk starts at data_offset + sent
            chunk_start = data_offset + sent
            chunk_end = chunk_start + chunk_size
            
            # Write header 4 bytes before the chunk data
            header_pos = chunk_start - 4
            payload[header_pos] = chunk_size & 0xff
            payload[header_pos + 1] = (chunk_size >> 8) & 0xff
            payload[header_pos + 2] = (chunk_size >> 16) & 0xff
            payload[header_pos + 3] = seq
            
            # Log if debug enabled
            if logger.isEnabledFor(logging.DEBUG):
                packet = payload_view[header_pos:chunk_end]
                conn_id_str = f"[conn_id={self.connection_id}]" if self.connection_id >= 0 else ""
                packet_type_str = f" {packet_type}" if packet_type else ""
                logger.debug(hex_dump(packet, f"SEND async: {conn_id_str}{packet_type_str}"))
            
            # Send packet: header + chunk data using memoryview (no copy)
            self.writer.write(payload_view[header_pos:chunk_end])
            sent += chunk_size
        
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
    
    def __init__(self, socket: socket.socket, connection_id: int = -1):
        """Initialize write stream with socket"""
        self.socket = socket
        self.sequence = MutableInt(-1)
        self.connection_id = connection_id
        # Check once if sendmsg is supported (Unix) or if we need sendall (Windows)
        self.has_sendmsg = hasattr(socket, 'sendmsg')
    
    def write_payload(self, payload: bytearray, packet_type: str = "", reset_sequence: bool = True) -> None:
        """
        Write payload with MariaDB packet framing (sync version)
        
        Args:
            payload: Payload bytearray with first 4 bytes reserved for header
            packet_type: Packet type for logging (e.g., "COM_QUERY")
            reset_sequence: Whether to reset sequence number before sending
        """
        if reset_sequence:
            self.sequence.set(-1)
        
        # Payload has 4 bytes reserved at start for header
        payload_len = len(payload) - 4
        data_offset = 4  # Data starts after reserved header space
        
        # Handle empty payload - still need to send header
        if payload_len == 0:
            seq = self.sequence.increment_and_get()
            # Write header into first 4 bytes
            payload[0:3] = b'\x00\x00\x00'
            payload[3] = seq

            if logger.isEnabledFor(logging.DEBUG):
                conn_id_str = f"[conn_id={self.connection_id}]" if self.connection_id >= 0 else ""
                packet_type_str = f" {packet_type}" if packet_type else ""
                logger.debug(hex_dump(bytes(payload[0:4]), f"SEND sync: {conn_id_str}{packet_type_str}"))
            
            self.socket.sendall(payload[0:4])
            return
        
        # Use memoryview to avoid buffer copies when slicing
        payload_view = memoryview(payload)
        
        # Handle packet splitting for large payloads
        sent = 0  # Track how much data we've sent
        
        while sent < payload_len:
            chunk_size = min(MAX_PACKET_SIZE, payload_len - sent)
            seq = self.sequence.increment_and_get()
            
            # Data for this chunk starts at data_offset + sent
            chunk_start = data_offset + sent
            chunk_end = chunk_start + chunk_size
            
            # Write header 4 bytes before the chunk data
            header_pos = chunk_start - 4
            
            payload[header_pos] = chunk_size & 0xff
            payload[header_pos + 1] = (chunk_size >> 8) & 0xff
            payload[header_pos + 2] = (chunk_size >> 16) & 0xff
            payload[header_pos + 3] = seq
            
            # Log if debug enabled
            if logger.isEnabledFor(logging.DEBUG):
                packet = bytes(payload_view[header_pos:chunk_end])
                conn_id_str = f"[conn_id={self.connection_id}]" if self.connection_id >= 0 else ""
                packet_type_str = f" {packet_type}" if packet_type else ""
                logger.debug(hex_dump(packet, f"SEND sync: {conn_id_str}{packet_type_str}"))
            
            # Send packet: header + chunk data using memoryview (no copy)
            self.socket.sendall(payload_view[header_pos:chunk_end])
            
            sent += chunk_size
        
        # If last packet was exactly MAX_PACKET_SIZE, send empty packet to signal end
        if payload_len % MAX_PACKET_SIZE == 0:
            seq = self.sequence.increment_and_get()
            header = b'\x00\x00\x00' + bytes([seq])
            self.socket.sendall(header)
