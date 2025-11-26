# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Debug utilities for MariaDB connector

Provides hex dump and other debugging functionality.
"""

import sys
from typing import Union


def hex_dump(data: Union[bytes, bytearray], descr: str = "") -> str:
    """
    Generate hex dump of binary data in MySQL protocol format
    
    Args:
        data: Binary data to dump
        descr: Description of the data
        
    Returns:
        Formatted hex dump string
    """
    if not data:
        return ""
    
    MAX_DUMP_SIZE = 1024
    original_len = len(data)
    truncated = False
    
    # Truncate if data is too large
    if len(data) > MAX_DUMP_SIZE:
        data = data[:MAX_DUMP_SIZE]
        truncated = True
    
    lines = [f"{descr}"]
    
    # Header
    lines.append("       +---------------------------------------------------+")
    lines.append("       |  0  1  2  3  4  5  6  7    8  9  a  b  c  d  e  f |")
    lines.append("+------+---------------------------------------------------+------------------+")
    
    # Process data in 16-byte chunks
    offset = 0
    while offset < len(data):
        # Get chunk (up to 16 bytes)
        chunk = data[offset:offset + 16]
        
        # Format offset
        offset_str = f"|{offset:06X}|"
        
        # Format hex bytes
        hex_parts = []
        for i in range(16):
            if i < len(chunk):
                hex_parts.append(f"{chunk[i]:02X}")
            else:
                hex_parts.append("  ")
            
            # Add extra space after 8th byte
            if i == 7:
                hex_parts.append(" ")
        
        hex_str = " ".join(hex_parts)
        
        # Format ASCII representation
        ascii_parts = []
        for i in range(len(chunk)):
            byte_val = chunk[i]
            if 32 <= byte_val <= 126:  # Printable ASCII
                ascii_parts.append(chr(byte_val))
            else:
                ascii_parts.append(".")
        
        # Pad ASCII to 16 characters
        ascii_str = "".join(ascii_parts).ljust(16)
        
        # Add the line
        lines.append(f"{offset_str} {hex_str} | {ascii_str} |")
        
        offset += 16
    
    # Footer
    lines.append("+------+---------------------------------------------------+------------------+")
    
    # Add truncation notice if data was truncated
    if truncated:
        lines.append(f"[DATA TRUNCATED: showing {MAX_DUMP_SIZE} of {original_len} bytes]")
    
    return "\n".join(lines)
