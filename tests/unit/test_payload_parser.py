# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""Unit tests for PayloadParser"""

import pytest
from mariadb.impl.client.socket.payload_parser import PayloadParser


class TestPayloadParser:
    """Test PayloadParser functionality"""
    
    def test_init(self):
        """Test initialization"""
        data = bytearray(b'\x01\x02\x03')
        parser = PayloadParser(data)
        assert parser.position == 0
        assert parser.packet == data
    
    def test_read_byte(self):
        """Test reading single byte"""
        data = bytearray(b'\x42\x43\x44')
        parser = PayloadParser(data)
        
        assert parser.read_byte() == 0x42
        assert parser.position == 1
        assert parser.read_byte() == 0x43
        assert parser.position == 2
    
    def test_read_int16(self):
        """Test reading 2-byte integer"""
        data = bytearray(b'\x34\x12')  # Little-endian 0x1234
        parser = PayloadParser(data)
        
        assert parser.read_int16() == 0x1234
        assert parser.position == 2
    
    def test_read_int24(self):
        """Test reading 3-byte integer"""
        data = bytearray(b'\x56\x34\x12')  # Little-endian 0x123456
        parser = PayloadParser(data)
        
        assert parser.read_int24() == 0x123456
        assert parser.position == 3
    
    def test_read_int32(self):
        """Test reading 4-byte integer"""
        data = bytearray(b'\x78\x56\x34\x12')  # Little-endian 0x12345678
        parser = PayloadParser(data)
        
        assert parser.read_int32() == 0x12345678
        assert parser.position == 4
    
    def test_read_int64(self):
        """Test reading 8-byte integer"""
        data = bytearray(b'\xF0\xDE\xBC\x9A\x78\x56\x34\x12')
        parser = PayloadParser(data)
        
        assert parser.read_int64() == 0x123456789ABCDEF0
        assert parser.position == 8
    
    def test_read_length_encoded_int_small(self):
        """Test reading length-encoded int < 251"""
        data = bytearray(b'\x64')  # 100
        parser = PayloadParser(data)
        
        assert parser.read_length_encoded_int() == 100
        assert parser.position == 1
    
    def test_read_length_encoded_int_null(self):
        """Test reading NULL length-encoded int"""
        data = bytearray(b'\xFB')
        parser = PayloadParser(data)
        
        assert parser.read_length_encoded_int() is None
        assert parser.position == 1
    
    def test_read_length_encoded_int_medium(self):
        """Test reading length-encoded int with 0xFC marker"""
        data = bytearray(b'\xFC\xE8\x03')  # 1000
        parser = PayloadParser(data)
        
        assert parser.read_length_encoded_int() == 1000
        assert parser.position == 3
    
    def test_read_length_encoded_int_large(self):
        """Test reading length-encoded int with 0xFD marker"""
        data = bytearray(b'\xFD\xA0\x86\x01\x00')  # 100000
        parser = PayloadParser(data)
        
        assert parser.read_length_encoded_int() == 100000
        assert parser.position == 4
    
    def test_read_length_encoded_int_very_large(self):
        """Test reading length-encoded int with 0xFE marker"""
        data = bytearray(b'\xFE\x00\x2D\x31\x01\x00\x00\x00\x00')  # 20000000
        parser = PayloadParser(data)
        
        result = parser.read_length_encoded_int()
        assert result == 20000000
        assert parser.position == 9
    
    def test_read_length_encoded_string(self):
        """Test reading length-encoded string"""
        data = bytearray(b'\x04test')
        parser = PayloadParser(data)
        
        assert parser.read_length_encoded_string() == 'test'
        assert parser.position == 5
    
    def test_read_length_encoded_string_null(self):
        """Test reading NULL length-encoded string"""
        data = bytearray(b'\xFB')
        parser = PayloadParser(data)
        
        assert parser.read_length_encoded_string() is None
        assert parser.position == 1
    
    def test_read_length_encoded_string_utf8(self):
        """Test reading UTF-8 length-encoded string"""
        cafe_bytes = 'café'.encode('utf-8')
        data = bytearray([len(cafe_bytes)]) + bytearray(cafe_bytes)
        parser = PayloadParser(data)
        
        assert parser.read_length_encoded_string() == 'café'
    
    def test_read_length_encoded_string_invalid_utf8(self):
        """Test reading invalid UTF-8 with error handling"""
        # Invalid UTF-8 sequence
        data = bytearray(b'\x02\xFF\xFE')
        parser = PayloadParser(data)
        
        # Should use 'replace' error handling
        result = parser.read_length_encoded_string()
        assert result is not None  # Should not raise exception
    
    def test_read_length_encoded_bytes(self):
        """Test reading length-encoded bytes"""
        data = bytearray(b'\x04test')
        parser = PayloadParser(data)
        
        assert parser.read_length_encoded_bytes() == b'test'
        assert parser.position == 5
    
    def test_read_length_encoded_bytes_null(self):
        """Test reading NULL length-encoded bytes"""
        data = bytearray(b'\xFB')
        parser = PayloadParser(data)
        
        assert parser.read_length_encoded_bytes() is None
        assert parser.position == 1
    
    def test_read_fixed_length_string(self):
        """Test reading fixed-length string"""
        data = bytearray(b'hello world')
        parser = PayloadParser(data)
        
        assert parser.read_fixed_length_string(5) == 'hello'
        assert parser.position == 5
        
        assert parser.read_fixed_length_string(6) == ' world'
        assert parser.position == 11
    
    def test_read_bytes(self):
        """Test reading fixed number of bytes"""
        data = bytearray(b'hello world')
        parser = PayloadParser(data)
        
        assert parser.read_bytes(5) == b'hello'
        assert parser.position == 5
    
    def test_read_remaining(self):
        """Test reading all remaining bytes"""
        data = bytearray(b'hello world')
        parser = PayloadParser(data)
        
        parser.read_bytes(6)  # Read 'hello '
        remaining = parser.read_remaining()
        
        assert remaining == b'world'
        assert parser.position == 11
    
    def test_skip(self):
        """Test skipping bytes"""
        data = bytearray(b'hello world')
        parser = PayloadParser(data)
        
        parser.skip(6)
        assert parser.position == 6
        assert parser.read_bytes(5) == b'world'
    
    def test_has_remaining(self):
        """Test checking for remaining bytes"""
        data = bytearray(b'test')
        parser = PayloadParser(data)
        
        assert parser.has_remaining() is True
        parser.read_bytes(4)
        assert parser.has_remaining() is False
    
    def test_remaining_bytes(self):
        """Test getting remaining byte count"""
        data = bytearray(b'hello world')
        parser = PayloadParser(data)
        
        assert parser.remaining_bytes() == 11
        parser.read_bytes(6)
        assert parser.remaining_bytes() == 5
        parser.read_remaining()
        assert parser.remaining_bytes() == 0
    
    def test_reset(self):
        """Test resetting position"""
        data = bytearray(b'test')
        parser = PayloadParser(data)
        
        parser.read_bytes(2)
        assert parser.position == 2
        
        parser.reset()
        assert parser.position == 0
    
    def test_seek(self):
        """Test seeking to position"""
        data = bytearray(b'hello world')
        parser = PayloadParser(data)
        
        parser.seek(6)
        assert parser.position == 6
        assert parser.read_bytes(5) == b'world'
    
    def test_get_byte(self):
        """Test peeking at byte without advancing"""
        data = bytearray(b'\x42\x43')
        parser = PayloadParser(data)
        
        assert parser.get_byte() == 0x42
        assert parser.position == 0  # Position unchanged
        
        parser.read_byte()
        assert parser.get_byte() == 0x43
        assert parser.position == 1
    
    def test_read_length_encoded_string_at(self):
        """Test reading length-encoded string at specific position"""
        data = bytearray(b'\xFF\xFF\x04test\xFF')
        
        value, new_pos = PayloadParser.read_length_encoded_string_at(data, 2)
        assert value == 'test'
        assert new_pos == 7
    
    def test_read_length_encoded_string_at_null(self):
        """Test reading NULL at specific position"""
        data = bytearray(b'\xFF\xFB\xFF')
        
        value, new_pos = PayloadParser.read_length_encoded_string_at(data, 1)
        assert value is None
        assert new_pos == 2
    
    def test_read_length_encoded_bytes_at(self):
        """Test reading length-encoded bytes at specific position"""
        data = bytearray(b'\xFF\xFF\x04test\xFF')
        
        value, new_pos = PayloadParser.read_length_encoded_bytes_at(data, 2)
        assert value == b'test'
        assert new_pos == 7
    
    def test_read_length_encoded_bytes_at_null(self):
        """Test reading NULL bytes at specific position"""
        data = bytearray(b'\xFF\xFB\xFF')
        
        value, new_pos = PayloadParser.read_length_encoded_bytes_at(data, 1)
        assert value is None
        assert new_pos == 2
    
    def test_complex_sequence(self):
        """Test complex read sequence"""
        data = bytearray()
        data.append(0x01)  # byte
        data.extend(b'\x34\x12')  # short
        data.extend(b'\x78\x56\x34\x12')  # int
        data.extend(b'\x05hello')  # length-encoded string
        
        parser = PayloadParser(data)
        
        assert parser.read_byte() == 0x01
        assert parser.read_int16() == 0x1234
        assert parser.read_int32() == 0x12345678
        assert parser.read_length_encoded_string() == 'hello'
        assert parser.has_remaining() is False
    
    def test_boundary_conditions(self):
        """Test boundary conditions"""
        # Empty data
        parser = PayloadParser(bytearray())
        assert parser.has_remaining() is False
        assert parser.remaining_bytes() == 0
        
        # Single byte
        parser = PayloadParser(bytearray(b'\x42'))
        assert parser.has_remaining() is True
        assert parser.remaining_bytes() == 1
        assert parser.read_byte() == 0x42
        assert parser.has_remaining() is False
    
    def test_read_beyond_end(self):
        """Test reading beyond packet end"""
        data = bytearray(b'\x01\x02')
        parser = PayloadParser(data)
        
        parser.read_bytes(2)
        
        # Should raise or handle gracefully
        with pytest.raises((IndexError, Exception)):
            parser.read_byte()
    
    def test_encoding_variations(self):
        """Test different encoding variations"""
        # Latin-1 encoding
        data = bytearray(b'\x04test')
        parser = PayloadParser(data)
        result = parser.read_length_encoded_string(encoding='latin-1')
        assert result == 'test'
        
        # ASCII encoding
        parser.reset()
        result = parser.read_length_encoded_string(encoding='ascii')
        assert result == 'test'
