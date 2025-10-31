"""
Stream Interface

Defines the common interface for different stream implementations
(socket streams, compressed streams, etc.) used in MariaDB protocol communication.
"""

from typing import Protocol, runtime_checkable

from ..mutable_int import MutableInt


class Stream(Protocol):
    """
    Protocol defining the interface for stream implementations
    
    This protocol defines the common methods that all stream implementations
    must provide for MariaDB protocol communication.
    """
    
    def close(self) -> None:
        """
        Close the stream connection
        
        Closes the underlying connection and cleans up resources.
        """
        ...
    
    def sendall(self, data: bytes) -> None:
        """
        Send all data through the stream
        
        Args:
            data: Bytes to send
            
        Raises:
            OSError: If stream error occurs during send
        """
        ...
    
    def reset(self) -> None:
        """
        Reset the packet sequence counter
        
        This should be called at the start of a new command or
        when the protocol requires sequence reset.
        """
        ...
    
    def sequence(self) -> MutableInt:
        ...

    def read_payload(self) -> bytearray:
        """
        Read a complete MySQL packet and return payload only
        
        This method reads from the socket, buffers incomplete data,
        parses the 4-byte header, and returns only the payload.
        
        Returns:
            Packet payload as bytearray (without 4-byte header)
            
        Raises:
            OSError: If stream error occurs or connection closed
        """
        ...
    
    def send_payload(self, payload: bytearray, packet_type: str = "", reset_sequence: bool = True) -> None:
        """
        Send payload with automatic packet framing and chunking
        
        This method:
        1. Optionally resets sequence number to 0
        2. Splits payload into chunks if larger than 0xFFFFFF bytes
        3. Adds 4-byte header (3-byte length + 1-byte sequence) to each chunk
        4. Sends all chunks through the stream
        5. Handles sequence number incrementing
        
        Args:
            payload: Payload bytes to send
            packet_type: Packet type for debugging (e.g., "COM_QUERY")
            reset_sequence: Whether to reset sequence number before sending (default True)
            
        Raises:
            OSError: If stream error occurs during send
        """
        ...
