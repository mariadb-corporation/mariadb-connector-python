"""
Socket Stream Wrapper

Provides a unified interface for socket operations with sequence tracking
for MariaDB protocol communication.
"""

import socket
import struct
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
        self._buffer: bytearray = bytearray()
    
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
    
    def read_payload(self) -> bytearray:
        """
        Read a complete MySQL packet and return payload only
        
        This method reads from the socket, buffers incomplete data,
        parses the 4-byte header, and returns only the payload.
        
        Handles multi-packet messages: when packet length is 0xFFFFFF (16MB),
        it continues reading subsequent packets until a packet with length < 0xFFFFFF.
        
        Returns:
            Packet payload as bytearray (without 4-byte header)
            
        Raises:
            OSError: If socket error occurs or connection closed
        """
        if not self.socket:
            raise OSError("Socket is closed")
        
        # Accumulator for multi-packet payloads
        complete_payload = bytearray()
        
        # Keep reading packets until we get one with length < 0xFFFFFF
        while True:
            # Keep reading until we have a complete packet
            while True:
                # Check if we have enough data for a complete packet
                if len(self._buffer) >= 4:
                    # Parse packet header (3 bytes length + 1 byte sequence)
                    packet_length = struct.unpack('<I', bytes(self._buffer[0:3]) + b'\x00')[0]
                    packet_sequence = self._buffer[3]
                    
                    # Total packet size = 4 byte header + payload length
                    total_packet_size = 4 + packet_length
                    
                    # Check if we have the complete packet
                    if len(self._buffer) >= total_packet_size:
                        # Extract payload only (skip 4-byte header)
                        payload = self._buffer[4:total_packet_size]
                        
                        # Remove packet from buffer
                        self._buffer = self._buffer[total_packet_size:]
                        
                        # Update sequence for next packet
                        self.sequence.set((packet_sequence + 1) % 256)
                        
                        # Add this payload to the complete payload
                        complete_payload.extend(payload)
                        
                        # If packet length is exactly 0xFFFFFF (16MB), there are more packets
                        if packet_length == 0xFFFFFF:
                            # Continue reading next packet
                            break
                        else:
                            # This is the last packet, return complete payload
                            return complete_payload
                
                # Need more data - read from socket (blocking)
                try:
                    chunk = self.socket.recv(16384)  # Read up to 16KB at a time
                    if not chunk:
                        # Connection closed
                        if len(self._buffer) > 0:
                            raise OSError("Connection closed with incomplete packet in buffer")
                        raise OSError("Connection closed by remote host")
                    self._buffer.extend(chunk)
                except socket.error as e:
                    raise OSError(f"Failed to receive data: {e}")
    
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
            OSError: If stream error occurs during send
        """
        # Reset sequence if requested
        if reset_sequence:
            self.reset()
        
        max_packet_size = 0xFFFFFF  # 16MB - 1
        payload_length = len(payload)
        offset = 0
        
        while offset < payload_length:
            # Calculate chunk size (max 0xFFFFFF bytes)
            chunk_size = min(max_packet_size, payload_length - offset)
            chunk_data = payload[offset:offset + chunk_size]
            
            # Send packet with header
            self._send_packet_chunk(chunk_data)
            
            offset += chunk_size
            
            # If this chunk was exactly max size and there's no more data,
            # send an empty packet to indicate end
            if chunk_size == max_packet_size and offset == payload_length:
                self._send_packet_chunk(bytearray())
        
        # If payload was empty, still send one packet
        if payload_length == 0:
            self._send_packet_chunk(bytearray())
    
    def _send_packet_chunk(self, chunk_data: bytearray) -> None:
        """
        Send a single packet chunk with header
        
        Args:
            chunk_data: Data to send (max 0xFFFFFF bytes)
            
        Raises:
            OSError: If socket error occurs during send
        """
        chunk_length = len(chunk_data)
        
        # Prepare packet with header
        packet = bytearray()
        
        # Write 3-byte length (little-endian)
        packet.append(chunk_length & 0xFF)
        packet.append((chunk_length >> 8) & 0xFF)
        packet.append((chunk_length >> 16) & 0xFF)
        
        # Write sequence ID
        packet.append(self.sequence.get_and_increment() & 0xFF)
        
        # Write chunk data
        packet.extend(chunk_data)
        
        # Send through socket
        self.sendall(packet)
    