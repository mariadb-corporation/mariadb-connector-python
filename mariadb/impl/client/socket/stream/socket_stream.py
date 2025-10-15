"""
Socket Stream Wrapper

Provides a unified interface for socket operations with sequence tracking
for MariaDB protocol communication.
"""

import socket
from typing import Optional
from ..mutable_int import MutableInt


class SocketStream:
    """
    Socket stream wrapper with sequence tracking for MariaDB protocol
    
    This class wraps a socket and provides methods for sending/receiving data
    while maintaining packet sequence numbers as required by the MariaDB protocol.
    """
    
    def __init__(self, socket: socket.socket):
        """
        Initialize socket stream
        
        Args:
            sock: Socket instance to wrap
        """
        self.socket: socket.socket = socket
        self.sequence: MutableInt = MutableInt(1)
    
    def close(self) -> None:
        """
        Close the socket connection
        
        Closes the underlying socket and cleans up resources.
        """
        self.socket = None
    
    def sendall(self, data: bytes) -> None:
        """
        Send all data through the socket
        
        Args:
            data: Bytes to send
            
        Raises:
            OSError: If socket error occurs during send
        """
        if not self.socket:
            raise OSError("Socket is closed")
        
        try:
            self.socket.sendall(data)
        except socket.error as e:
            raise OSError(f"Failed to send data: {e}")
    
    def reset(self) -> None:
        """
        Reset the packet sequence counter
        
        This should be called at the start of a new command or
        when the protocol requires sequence reset.
        """
        self.sequence.set(0)
    
    def recv(self, bufsize: int) -> bytes:
        """
        Receive data from the socket
        
        Args:
            bufsize: Maximum number of bytes to receive
            
        Returns:
            Bytes received from socket
            
        Raises:
            OSError: If socket error occurs during receive
        """
        if not self.socket:
            raise OSError("Socket is closed")
        
        try:
            data = self.socket.recv(bufsize)
            if not data:
                raise OSError("Connection closed by remote host")
            return data
        except socket.error as e:
            raise OSError(f"Failed to receive data: {e}")
    