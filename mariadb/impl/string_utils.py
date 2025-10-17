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
String utility functions for MariaDB Connector/Python
"""


class StringEscaper:
    """
    Utility class for escaping strings in SQL statements
    """
    
    @staticmethod
    def escape_string(string: str, no_backslash_escapes: bool = False) -> str:
        """
        Escape a string for use in SQL statements
        
        Args:
            string: String to escape
            no_backslash_escapes: Whether NO_BACKSLASH_ESCAPES SQL mode is enabled
            
        Returns:
            str: Escaped string (without surrounding quotes)
        """
        if no_backslash_escapes:
            # When NO_BACKSLASH_ESCAPES is set, single quotes are escaped by doubling them
            escaped = string.replace("'", "''")
        else:
            # Standard escaping: backslash, quote, double quote, zero byte
            escaped = string.replace('\\', '\\\\')  # Backslash first
            escaped = escaped.replace("'", "\\'")   # Single quote
            escaped = escaped.replace('"', '\\"')   # Double quote  
            escaped = escaped.replace('\0', '\\0')  # Zero byte
        
        return escaped
    
    @staticmethod
    def escape_string_with_quotes(string: str, no_backslash_escapes: bool = False) -> str:
        """
        Escape a string for use in SQL statements and wrap it in single quotes
        
        Args:
            string: String to escape
            no_backslash_escapes: Whether NO_BACKSLASH_ESCAPES SQL mode is enabled
            
        Returns:
            str: Escaped string wrapped in single quotes
        """
        escaped = StringEscaper.escape_string(string, no_backslash_escapes)
        return f"'{escaped}'"
