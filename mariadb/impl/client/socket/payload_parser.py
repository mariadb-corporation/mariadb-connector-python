"""
Payload Parser for MariaDB protocol

Provides parsing facilities for MySQL/MariaDB packet payloads.
Does NOT perform any I/O - only parses bytes.
"""

import struct
from typing import Optional


class PayloadParser:
    """
    Parser for MariaDB protocol payloads
    
    This class takes a packet payload (bytes) and provides methods
    to parse various data types from it. It does NOT perform any I/O.
    """
    
    def __init__(self, packet: bytearray, pos: int = 0):
        """Initialize parser with packet payload and optional starting position"""
        self.packet: bytearray = packet
        self.pos: int = pos  # Current read position

    def get_byte(self) -> int:
        """Read single byte from packet without advancing position"""
        if self.pos >= len(self.packet):
            raise IOError("Not enough data in packet to read byte")
        
        return self.packet[self.pos]

    def read_byte(self) -> int:
        """Read single byte from packet and advance position"""
        if self.pos >= len(self.packet):
            raise IOError("Not enough data in packet to read byte")
        
        value = self.packet[self.pos]
        self.pos += 1
        return value
    
    def read_int16(self) -> int:
        """Read 2-byte integer (little-endian) and advance position"""
        if self.pos + 2 > len(self.packet):
            raise IOError("Not enough data in packet to read int16")
        
        value = struct.unpack('<H', self.packet[self.pos:self.pos+2])[0]
        self.pos += 2
        return value
    
    def read_int24(self) -> int:
        """Read 3-byte integer (little-endian) and advance position"""
        if self.pos + 3 > len(self.packet):
            raise IOError("Not enough data in packet to read int24")
        
        value = struct.unpack('<I', self.packet[self.pos:self.pos+3] + b'\x00')[0]
        self.pos += 3
        return value
    
    def read_int32(self) -> int:
        """Read 4-byte integer (little-endian) and advance position"""
        if self.pos + 4 > len(self.packet):
            raise IOError("Not enough data in packet to read int32")
        
        value = struct.unpack('<I', self.packet[self.pos:self.pos+4])[0]
        self.pos += 4
        return value
    
    def read_int64(self) -> int:
        """Read 8-byte integer (little-endian) and advance position"""
        if self.pos + 8 > len(self.packet):
            raise IOError("Not enough data in packet to read int64")
        
        value = struct.unpack('<Q', self.packet[self.pos:self.pos+8])[0]
        self.pos += 8
        return value
    
    def read_length_encoded_int(self) -> Optional[int]:
        """Read length-encoded integer (MySQL protocol format) and advance position"""
        if self.pos >= len(self.packet):
            raise IOError("Not enough data in packet to read length-encoded int")
        
        first_byte = self.packet[self.pos]
        self.pos += 1
        
        if first_byte < 251:
            return first_byte
        elif first_byte == 251:    
            return None
        elif first_byte == 252:
            return self.read_int16()
        elif first_byte == 253:
            return self.read_int24()
        elif first_byte == 254:
            return self.read_int64()
        else:
            raise IOError(f"Invalid length-encoded int first byte: {first_byte}")
    
    def read_length_encoded_string(self, encoding: str = 'utf-8') -> Optional[str]:
        """Read length-encoded string with specified encoding and advance position"""
        
        length = self.read_length_encoded_int()
        
        if length is None:
            return None
        
        if self.pos + length > len(self.packet):
            raise IOError(f"Not enough data in packet to read string of length {length}")
        
        string_data = self.packet[self.pos:self.pos+length]
        self.pos += length
        
        try:
            value = string_data.decode(encoding)
        except UnicodeDecodeError as e:
            # Fallback to replace invalid characters
            value = string_data.decode(encoding, errors='replace')
        
        return value
    
    def read_length_encoded_bytes(self) -> Optional[bytes]:
        """Read length-encoded bytes and advance position"""
        length = self.read_length_encoded_int()
        
        if length is None:
            return None

        if self.pos + length > len(self.packet):
            raise IOError(f"Not enough data in packet to read {length} bytes")
        
        data = self.packet[self.pos:self.pos+length]
        self.pos += length
        return data
    
    def read_fixed_length_string(self, length: int, encoding: str = 'utf-8') -> str:
        """Read fixed-length string with specified encoding and advance position"""
        if self.pos + length > len(self.packet):
            raise IOError(f"Not enough data in packet to read string of length {length}")
        
        string_data = self.packet[self.pos:self.pos+length]
        self.pos += length
        
        try:
            value = string_data.decode(encoding)
        except UnicodeDecodeError as e:
            # Fallback to replace invalid characters
            value = string_data.decode(encoding, errors='replace')
        
        return value
    
    def read_null_terminated_string(self, encoding: str = 'utf-8') -> str:
        """Read null-terminated string"""
        null_pos = self.packet.find(0, self.pos)
        if null_pos == -1:
            raise IOError("No null terminator found in packet")
        
        string_data = self.packet[self.pos:null_pos]
        self.pos = null_pos + 1
        
        try:
            value = string_data.decode(encoding)
        except UnicodeDecodeError as e:
            # Fallback to replace invalid characters
            value = string_data.decode(encoding, errors='replace')
        
        return value
    
    def read_bytes(self, length: int) -> bytes:
        """Read fixed number of bytes and advance position"""
        if self.pos + length > len(self.packet):
            raise IOError(f"Not enough data in packet to read {length} bytes")
        
        data = self.packet[self.pos:self.pos+length]
        self.pos += length
        return data
    
    def read_remaining(self) -> bytes:
        """Read all remaining bytes in packet and advance to end"""
        data = bytes(self.packet[self.pos:])
        self.pos = len(self.packet)
        return data
    
    def skip(self, num_bytes: int) -> None:
        """Skip specified number of bytes and advance position"""
        if self.pos + num_bytes > len(self.packet):
            raise IOError(f"Not enough data in packet to skip {num_bytes} bytes")
        
        self.pos += num_bytes
    
    def has_remaining(self) -> bool:
        """Check if there are remaining bytes to read"""
        return self.pos < len(self.packet)
    
    def remaining_bytes(self) -> int:
        """Get number of remaining bytes"""
        return len(self.packet) - self.pos
    
    def reset(self) -> None:
        """Reset read position to beginning"""
        self.pos = 0
    
    def seek(self, position: int) -> None:
        """Set read position to specified location"""
        if position < 0 or position > len(self.packet):
            raise IOError(f"Invalid position: {position}")
        
        self.pos = position
    
    @staticmethod
    def read_length_encoded_string_at(packet: bytes, pos: int, encoding: str = 'utf-8') -> tuple:
        """Read length-encoded string at position and return (value, new_position)"""
        parser = PayloadParser(packet, pos)
        value = parser.read_length_encoded_string(encoding)
        return value, parser.pos
    
    @staticmethod
    def read_length_encoded_bytes_at(packet: bytes, pos: int) -> tuple:
        """Read length-encoded bytes at position and return (value, new_position)"""
        parser = PayloadParser(packet, pos)
        value = parser.read_length_encoded_bytes()
        return value, parser.pos
