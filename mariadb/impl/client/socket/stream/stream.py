"""
Stream Interface for MariaDB Protocol

Defines the interface for sending and receiving MySQL/MariaDB packets.
"""

from abc import ABC, abstractmethod


class Stream(ABC):
    """
    Abstract interface for MariaDB protocol streams
    
    This interface defines the contract for sending and receiving
    MySQL/MariaDB packets with proper framing and sequence management.
    """
    
    @abstractmethod
    def read_payload(self) -> bytearray:
        """
        Read a complete MySQL packet and return payload only
        
        This method reads from the underlying transport, handles packet framing,
        and returns only the payload (without the 4-byte header).
        
        For multi-packet messages (packets with length 0xFFFFFF), it continues
        reading subsequent packets until a packet with length < 0xFFFFFF.
        
        Returns:
            Packet payload as bytearray (without 4-byte header)
            
        Raises:
            OSError: If transport error occurs or connection closed
        """
        pass
    
    @abstractmethod
    def send_payload(self, payload: bytearray, packet_type: str = "", reset_sequence: bool = True) -> None:
        """
        Send payload with automatic packet framing and chunking
        
        Handles packets larger than 0xFFFFFF by splitting into multiple packets.
        If a packet is exactly 0xFFFFFF bytes, sends an additional empty packet.
        
        Args:
            payload: Payload bytes to send
            packet_type: Packet type for debugging (e.g., "COM_QUERY")
            reset_sequence: Whether to reset sequence number before sending (default True)
            
        Raises:
            OSError: If transport error occurs during send
        """
        pass
