#
# Copyright (C) 2020-2021 Georg Richter and MariaDB Corporation AB

# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Library General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.

# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Library General Public License for more details.

# You should have received a copy of the GNU Library General Public
# License along with this library; if not see <http://www.gnu.org/licenses>
# or write to the Free Software Foundation, Inc.,
# 51 Franklin St., Fifth Floor, Boston, MA 02110, USA
#

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
    lines.append("+------+--------------------------------------------------+------------------+")
    
    return "\n".join(lines)
