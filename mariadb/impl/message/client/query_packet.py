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
Query packet for MariaDB SQL execution

Equivalent to the Java QueryPacket class.
"""

from typing import Any, List, Optional, Union
from ..client_message import ClientMessage


class QueryPacket(ClientMessage):
    """
    Query packet for SQL execution with optional parameter binding
    
    Supports both simple queries and parameterized queries for better performance.
    """
    
    COM_QUERY = 0x03
    
    def __init__(self, sql: str, parameters: Optional[List[Any]] = None):
        """
        Initialize query packet
        
        Args:
            sql: SQL query string (may contain ? placeholders)
            parameters: Optional list of parameters to bind
        """
        self.sql = sql
        self.parameters = parameters or []
        
    def encode(self, writer: Any, context: Any) -> None:
        """
        Encode query packet with optional parameter binding
        
        Args:
            writer: Packet writer
            context: Connection context
            
        Raises:
            IOError: If encoding fails
        """
        # Start payload mode
        writer.start_payload()
        
        # Command type (COM_QUERY = 0x03)
        writer.write_byte(0x03)
        
        if self.parameters:
            # Use parameter binding - write SQL with placeholders and parameters
            self._encode_parameterized_query(writer)
        else:
            # Simple query - write SQL directly
            writer.write_string(self.sql, 'utf-8')
        
        # Send packet with automatic header and chunking
        writer.send_payload("COM_QUERY")
    
    def _encode_parameterized_query(self, writer: Any) -> None:
        """
        Encode parameterized query by interleaving SQL fragments with parameters
        
        Args:
            writer: Packet writer
        """
        # Parse SQL into fragments separated by '?' placeholders
        sql_parts = self.sql.split('?')
        
        if len(sql_parts) - 1 != len(self.parameters):
            raise ValueError(f"Parameter count mismatch: SQL has {len(sql_parts) - 1} placeholders, got {len(self.parameters)} parameters")
        
        # Write SQL fragments interleaved with parameters
        for i, sql_part in enumerate(sql_parts):
            # Write SQL fragment
            if sql_part:  # Don't write empty strings
                writer.write_string(sql_part, 'utf-8')
            
            # Write parameter (except after the last SQL fragment)
            if i < len(self.parameters):
                self._write_parameter_value(writer, self.parameters[i])
    
    def _write_parameter_value(self, writer: Any, param: Any) -> None:
        """
        Write parameter value directly as its string representation
        (for COM_QUERY, parameters are converted to strings)
        
        Args:
            writer: Packet writer
            param: Parameter value
        """
        if param is None:
            writer.write_string('NULL', 'utf-8')
        elif isinstance(param, bool):
            writer.write_string('1' if param else '0', 'utf-8')
        elif isinstance(param, (int, float)):
            writer.write_string(str(param), 'utf-8')
        elif isinstance(param, str):
            # Escape single quotes and write as quoted string
            escaped = param.replace("'", "''")
            writer.write_string(f"'{escaped}'", 'utf-8')
        elif isinstance(param, (bytes, bytearray)):
            # Convert to hex string for binary data
            hex_str = param.hex()
            writer.write_string(f"0x{hex_str}", 'utf-8')
        else:
            # Default to string representation with quotes
            escaped = str(param).replace("'", "''")
            writer.write_string(f"'{escaped}'", 'utf-8')
    
    
    def description(self) -> str:
        """Get message description"""
        # Truncate long queries for description
        sql_desc = self.sql[:50] + "..." if len(self.sql) > 50 else self.sql
        if self.parameters:
            return f"QueryPacket(sql='{sql_desc}', params={len(self.parameters)})"
        else:
            return f"QueryPacket(sql='{sql_desc}')"
    
    def can_be_redone(self) -> bool:
        """Query can be redone if it's a SELECT statement"""
        sql_upper = self.sql.strip().upper()
        # Only SELECT statements are safe to redo
        return sql_upper.startswith('SELECT') or sql_upper.startswith('SHOW') or sql_upper.startswith('DESCRIBE')
