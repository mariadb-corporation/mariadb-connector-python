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

    def recv(self, bufsize: int) -> bytes:
        """
        Receive data from the stream
        
        Args:
            bufsize: Maximum number of bytes to receive
            
        Returns:
            Bytes received from stream
            
        Raises:
            OSError: If stream error occurs during receive
        """
        ...
