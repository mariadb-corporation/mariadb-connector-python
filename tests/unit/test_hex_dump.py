#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

import unittest
from mariadb.impl.debug_utils import hex_dump


class TestHexDump(unittest.TestCase):
    """Test hex_dump utility function"""

    def test_empty_data(self):
        """Test hex_dump with empty data"""
        result = hex_dump(b"")
        self.assertEqual(result, "")
        
        result = hex_dump(bytearray())
        self.assertEqual(result, "")

    def test_single_byte(self):
        """Test hex_dump with single byte"""
        result = hex_dump(b"\x00")
        
        # Should contain header
        self.assertIn("0  1  2  3  4  5  6  7", result)
        
        # Should contain the byte
        self.assertIn("00", result)
        
        # Should contain offset
        self.assertIn("|000000|", result)
        
        # Should contain ASCII representation (. for non-printable)
        self.assertIn(".", result)

    def test_printable_ascii(self):
        """Test hex_dump with printable ASCII characters"""
        data = b"Hello"
        result = hex_dump(data)
        
        # Check hex representation
        self.assertIn("48", result)  # H
        self.assertIn("65", result)  # e
        self.assertIn("6C", result)  # l
        self.assertIn("6F", result)  # o
        
        # Check ASCII representation
        self.assertIn("Hello", result)

    def test_non_printable_characters(self):
        """Test hex_dump with non-printable characters"""
        data = b"\x00\x01\x02\x03\x04"
        result = hex_dump(data)
        
        # Check hex representation
        self.assertIn("00 01 02 03 04", result)
        
        # Check ASCII representation (should be dots)
        lines = result.split("\n")
        data_line = [line for line in lines if "|000000|" in line][0]
        self.assertIn(".....", data_line)

    def test_mixed_printable_and_non_printable(self):
        """Test hex_dump with mixed printable and non-printable characters"""
        data = b"AB\x00\x01CD"
        result = hex_dump(data)
        
        # Check hex representation
        self.assertIn("41 42 00 01 43 44", result)
        
        # Check ASCII representation
        lines = result.split("\n")
        data_line = [line for line in lines if "|000000|" in line][0]
        self.assertIn("AB..CD", data_line)

    def test_exactly_16_bytes(self):
        """Test hex_dump with exactly 16 bytes (one full line)"""
        data = b"0123456789ABCDEF"
        result = hex_dump(data)
        
        # Should have exactly one data line
        lines = result.split("\n")
        data_lines = [line for line in lines if line.startswith("|000000|")]
        self.assertEqual(len(data_lines), 1)
        
        # Check that all 16 bytes are present
        self.assertIn("30 31 32 33 34 35 36 37", result)  # First 8 bytes
        self.assertIn("38 39 41 42 43 44 45 46", result)  # Last 8 bytes
        
        # Check ASCII
        self.assertIn("0123456789ABCDEF", result)

    def test_more_than_16_bytes(self):
        """Test hex_dump with more than 16 bytes (multiple lines)"""
        data = b"0123456789ABCDEF" + b"GHIJKLMNOPQRSTUV"
        result = hex_dump(data)
        
        # Should have two data lines
        lines = result.split("\n")
        data_lines = [line for line in lines if line.startswith("|")]
        self.assertGreaterEqual(len(data_lines), 2)
        
        # Check first line offset
        self.assertIn("|000000|", result)
        
        # Check second line offset
        self.assertIn("|000010|", result)  # 16 in hex
        
        # Check ASCII for both lines
        self.assertIn("0123456789ABCDEF", result)
        self.assertIn("GHIJKLMNOPQRSTUV", result)

    def test_partial_last_line(self):
        """Test hex_dump with partial last line (not multiple of 16)"""
        data = b"Hello World!"  # 12 bytes
        result = hex_dump(data)
        
        # Should have one data line with padding
        lines = result.split("\n")
        data_line = [line for line in lines if "|000000|" in line][0]
        
        # Should have spaces for missing bytes
        # Count the hex part (should have spaces for 4 missing bytes)
        self.assertIn("Hello World!", result)

    def test_with_description(self):
        """Test hex_dump with description"""
        data = b"Test"
        descr = "Test Packet"
        result = hex_dump(data, descr)
        
        # Description should be in the output
        self.assertIn("Test Packet", result)

    def test_bytearray_input(self):
        """Test hex_dump with bytearray input"""
        data = bytearray([0x48, 0x65, 0x6C, 0x6C, 0x6F])  # "Hello"
        result = hex_dump(data)
        
        # Should work the same as bytes
        self.assertIn("48 65 6C 6C 6F", result)
        self.assertIn("Hello", result)

    def test_all_byte_values(self):
        """Test hex_dump with all possible byte values (0-255)"""
        data = bytes(range(256))
        result = hex_dump(data)
        
        # Should have 16 lines of data (256 / 16)
        lines = result.split("\n")
        data_lines = [line for line in lines if line.startswith("|")]
        self.assertEqual(len(data_lines), 16)
        
        # Check first offset
        self.assertIn("|000000|", result)
        
        # Check last offset (240 = 0xF0)
        self.assertIn("|0000F0|", result)
        
        # Check some specific values
        self.assertIn("00", result)  # First byte
        self.assertIn("FF", result)  # Last byte

    def test_special_ascii_boundary_values(self):
        """Test hex_dump with ASCII boundary values"""
        # Test space (32, first printable)
        data = b"\x20"
        result = hex_dump(data)
        self.assertIn("20", result)
        lines = result.split("\n")
        data_line = [line for line in lines if "|000000|" in line][0]
        self.assertIn(" ", data_line.split("|")[-2])
        
        # Test tilde (126, last printable)
        data = b"\x7E"
        result = hex_dump(data)
        self.assertIn("7E", result)
        lines = result.split("\n")
        data_line = [line for line in lines if "|000000|" in line][0]
        self.assertIn("~", data_line)
        
        # Test DEL (127, first non-printable after printables)
        data = b"\x7F"
        result = hex_dump(data)
        self.assertIn("7F", result)
        lines = result.split("\n")
        data_line = [line for line in lines if "|000000|" in line][0]
        self.assertIn(".", data_line.split("|")[-2])

    def test_mysql_handshake_packet_format(self):
        """Test hex_dump with MySQL-like packet data"""
        # Simulate a small MySQL packet
        data = b"\x0a\x35\x2e\x35\x2e\x35\x2d\x31\x30"  # Protocol version + server version
        result = hex_dump(data, "MySQL Handshake")
        
        # Should contain description
        self.assertIn("MySQL Handshake", result)
        
        # Should contain hex values
        self.assertIn("0A", result)
        self.assertIn("35 2E 35 2E 35", result)
        
        # Should have proper formatting
        self.assertIn("+------+", result)
        self.assertIn("|000000|", result)

    def test_spacing_after_8th_byte(self):
        """Test that there's extra spacing after the 8th byte"""
        data = bytes(range(16))
        result = hex_dump(data)
        
        lines = result.split("\n")
        data_line = [line for line in lines if "|000000|" in line][0]
        
        # The hex part should have extra space after 8th byte
        # Format: "00 01 02 03 04 05 06 07   08 09 0A 0B 0C 0D 0E 0F"
        hex_part = data_line.split("|")[2].strip()
        
        # Should contain the extra space separator (3 spaces total)
        self.assertIn("07   08", hex_part)

    def test_header_and_footer_format(self):
        """Test that header and footer are properly formatted"""
        data = b"Test"
        result = hex_dump(data)
        
        lines = result.split("\n")
        
        # Check header lines exist
        header_lines = [line for line in lines if "0  1  2  3" in line]
        self.assertEqual(len(header_lines), 1)
        
        # Check separator lines
        separator_lines = [line for line in lines if line.startswith("+------+")]
        self.assertGreaterEqual(len(separator_lines), 2)  # Top and bottom

    def test_large_offset(self):
        """Test hex_dump with large data requiring larger offsets"""
        # Create data that spans multiple lines
        data = b"X" * 256  # 256 bytes = 16 lines
        result = hex_dump(data)
        
        # Check various offsets
        self.assertIn("|000000|", result)  # First line
        self.assertIn("|000010|", result)  # Second line (16 in hex)
        self.assertIn("|0000F0|", result)  # Last line (240 in hex)

    def test_output_structure(self):
        """Test the overall structure of hex_dump output"""
        data = b"Hello"
        result = hex_dump(data, "Test Description")
        
        lines = result.split("\n")
        
        # Should have:
        # 1. Description line
        # 2. Header separator
        # 3. Column header
        # 4. Data separator
        # 5. Data line(s)
        # 6. Footer separator
        
        self.assertGreaterEqual(len(lines), 6)
        
        # First line should be description
        self.assertEqual(lines[0], "Test Description")
        
        # Should have proper box drawing
        self.assertTrue(any("+---" in line for line in lines))
        self.assertTrue(any("|000000|" in line for line in lines))


if __name__ == '__main__':
    unittest.main()
