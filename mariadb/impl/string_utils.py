# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

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
