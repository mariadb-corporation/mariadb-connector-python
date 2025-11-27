"""
PayloadReader for MariaDB protocol

Provides parsing facilities for MySQL/MariaDB packet payloads.
Does NOT perform any I/O - only parses bytes.
"""

import struct
from typing import Optional


class PayloadReader:
    """
    Reader for MariaDB protocol payloads
    
    This class takes a packet payload (bytes) and provides methods
    to parse various data types from it. It does NOT perform any I/O.
    """
    
    def __init__(self, packet: memoryview, pos: int = 0):
        """Initialize parser with packet payload and optional starting position"""
        self.packet: memoryview = packet
        self.pos: int = pos  # Current read position
    
    def set_buffer(self, packet: memoryview, pos: int = 0):
        self.packet = packet
        self.pos = pos
    
    def get_byte(self) -> int:
        """Read single byte from packet without advancing position"""
        return self.packet[self.pos]

    def read_byte(self) -> int:
        """Read single byte from packet and advance position"""
        value = self.packet[self.pos]
        self.pos += 1
        return value
    
    def read_uint16(self) -> int:
        """Read 2-byte integer (little-endian) and advance position"""
        value = struct.unpack('<H', self.packet[self.pos:self.pos+2])[0]
        self.pos += 2
        return value
    
    def read_int16(self) -> int:
        """Read 2-byte integer (little-endian) and advance position"""
        value = struct.unpack('<h', self.packet[self.pos:self.pos+2])[0]
        self.pos += 2
        return value

    def read_uint24(self) -> int:
        """Read 3-byte integer (little-endian) and advance position"""
        value = (self.packet[self.pos] | 
                (self.packet[self.pos + 1] << 8) | 
                (self.packet[self.pos + 2] << 16))
        self.pos += 3
        return value

    def read_uint32(self) -> int:
        """Read 4-byte integer (little-endian) and advance position"""
        value = struct.unpack('<I', self.packet[self.pos:self.pos+4])[0]
        self.pos += 4
        return value

    def read_int32(self) -> int:
        """Read 4-byte integer (little-endian) and advance position"""
        value = struct.unpack('<i', self.packet[self.pos:self.pos+4])[0]
        self.pos += 4
        return value
    
    def read_uint64(self) -> int:
        """Read 8-byte integer (little-endian) and advance position"""
        value = struct.unpack('<Q', self.packet[self.pos:self.pos+8])[0]
        self.pos += 8
        return value

    def read_int64(self) -> int:
        """Read 8-byte integer (little-endian) and advance position"""
        value = struct.unpack('<q', self.packet[self.pos:self.pos+8])[0]
        self.pos += 8
        return value

    def read_float(self) -> float:
        """Read 4-byte float (little-endian) and advance position"""
        value = struct.unpack('<f', self.packet[self.pos:self.pos+4])[0]
        self.pos += 4
        return value
    
    def read_double(self) -> float:
        """Read 8-byte float (little-endian) and advance position"""
        value = struct.unpack('<d', self.packet[self.pos:self.pos+8])[0]
        self.pos += 8
        return value

    def read_length_encoded_int(self) -> Optional[int]:
        """Read length-encoded integer (MySQL protocol format) and advance position"""
        first_byte = self.packet[self.pos]
        self.pos += 1
        
        if first_byte < 251:
            return first_byte
        elif first_byte == 251:    
            return None
        elif first_byte == 252:
            return self.read_uint16()
        elif first_byte == 253:
            return self.read_uint24()
        return self.read_uint64()
    
    def read_length_encoded_string(self, encoding: str = 'utf-8') -> Optional[str]:
        """Read length-encoded string with specified encoding and advance position"""
        length = self.read_length_encoded_int()
        
        if length is None:
            return None
        
        # Direct decode without intermediate bytes() conversion
        # memoryview supports decode directly
        string_data = self.packet[self.pos:self.pos+length]
        self.pos += length
        
        # Decode directly from memoryview - faster than bytes()
        return bytes(string_data).decode(encoding, errors='replace')
    
    def read_length_encoded_bytes(self) -> Optional[bytes]:
        """Read length-encoded bytes and advance position"""
        length = self.read_length_encoded_int()
        
        if length is None:
            return None

        data = bytes(self.packet[self.pos:self.pos+length])
        self.pos += length
        return data

    def read_null_terminated_bytes(self) -> memoryview:
        """Read null-terminated string"""
        for i in range(self.pos, len(self.packet)):
            if self.packet[i] == 0x00:
                data = self.packet[self.pos:i]
                self.pos = i + 1
                return data
        data = self.packet[self.pos:]
        self.pos = len(self.packet)
        return data

        
    def read_null_terminated_string(self, encoding: str = 'utf-8') -> str:
        """Read null-terminated string"""
        for i in range(self.pos, len(self.packet)):
            if self.packet[i] == 0x00:
                string_data = bytes(self.packet[self.pos:i]).decode(encoding)
                self.pos = i + 1
                return string_data
        string_data = bytes(self.packet[self.pos:]).decode(encoding)        
        self.pos = len(self.packet)
        return string_data
    
    def read_bytes(self, length: int) -> bytes:
        """Read fixed number of bytes and advance position"""
        data = bytes(self.packet[self.pos:self.pos+length])
        self.pos += length
        return data
    
    def read_remaining(self) -> bytes:
        """Read all remaining bytes in packet and advance to end"""
        data = bytes(self.packet[self.pos:])
        self.pos = len(self.packet)
        return data
    
    def skip(self, num_bytes: int) -> None:
        """Skip specified number of bytes and advance position"""
        self.pos += num_bytes
    
    def has_remaining(self) -> bool:
        """Check if there are remaining bytes to read"""
        return self.pos < len(self.packet)
    
    def remaining_bytes(self) -> int:
        """Get number of remaining bytes"""
        return len(self.packet) - self.pos
