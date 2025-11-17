#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
SQL parser for handling placeholders in SQL statements.

This module provides proper parsing of SQL statements to identify placeholders
while correctly handling:
- String literals (single and double quotes)
- Comments (/* */, --, #, //)
- Backtick identifiers
- Escape sequences

Based on mariadb-connector-nodejs implementation.
"""

from enum import IntEnum
from typing import List, Tuple, Dict, Any, Optional


class ParseState(IntEnum):
    """Parser state machine states"""
    NORMAL = 1          # Normal SQL parsing
    STRING = 2          # Inside string literal
    SLASH_STAR_COMMENT = 3  # Inside /* */ comment
    ESCAPE = 4          # Found backslash escape
    EOL_COMMENT = 5     # Inside # or -- or // comment
    BACKTICK = 6        # Inside backtick identifier


def split_sql_parts(sql: str) -> Tuple[bytes, List[int]]:
    """
    Find positions of positional placeholders (?) in SQL and return SQL as bytes.
    
    Ignores placeholders inside strings, comments, and backtick identifiers.
    
    Args:
        sql: SQL statement
        
    Returns:
        Tuple of (sql_bytes, placeholder_byte_positions)
        - sql_bytes: SQL encoded as UTF-8 bytes
        - placeholder_byte_positions: List of byte positions (start, end) pairs
    """
    sql_bytes = sql.encode('utf-8')
    param_positions = []
    state = ParseState.NORMAL
    last_char = '\0'
    single_quotes = False
    
    for i, char in enumerate(sql_bytes):
        # Handle escape sequences
        if state == ParseState.ESCAPE:
            if not ((char == ord("'") and single_quotes) or (char == ord('"') and not single_quotes)):
                state = ParseState.STRING
                last_char = char
                continue
        
        # State machine using match/case
        match char:
            case 42:  # ord('*')
                if state == ParseState.NORMAL and last_char == 47:  # ord('/')
                    # Check if this is an executable comment /*! or /*M!
                    # Peek ahead to see if next char is ! or M
                    if i + 1 < len(sql_bytes):
                        next_char = sql_bytes[i + 1]
                        if next_char == 33:  # ord('!')
                            # Executable comment /*! - treat as normal SQL, don't enter comment state
                            pass
                        elif next_char == 77 and i + 2 < len(sql_bytes) and sql_bytes[i + 2] == 33:  # ord('M') and ord('!')
                            # MariaDB executable comment /*M! - treat as normal SQL
                            pass
                        else:
                            state = ParseState.SLASH_STAR_COMMENT
                    else:
                        state = ParseState.SLASH_STAR_COMMENT
            
            case 47:  # ord('/')
                if state == ParseState.SLASH_STAR_COMMENT and last_char == 42:  # ord('*')
                    state = ParseState.NORMAL
                elif state == ParseState.NORMAL and last_char == 47:  # ord('/')
                    state = ParseState.EOL_COMMENT
            
            case 35:  # ord('#')
                if state == ParseState.NORMAL:
                    state = ParseState.EOL_COMMENT
            
            case 45:  # ord('-')
                if state == ParseState.NORMAL and last_char == 45:  # ord('-')
                    state = ParseState.EOL_COMMENT
            
            case 10:  # ord('\n')
                if state == ParseState.EOL_COMMENT:
                    state = ParseState.NORMAL
            
            case 34:  # ord('"')
                if state == ParseState.NORMAL:
                    state = ParseState.STRING
                    single_quotes = False
                elif state == ParseState.STRING and not single_quotes:
                    state = ParseState.NORMAL
                elif state == ParseState.ESCAPE:
                    state = ParseState.STRING
            
            case 39:  # ord("'")
                if state == ParseState.NORMAL:
                    state = ParseState.STRING
                    single_quotes = True
                elif state == ParseState.STRING and single_quotes:
                    state = ParseState.NORMAL
                elif state == ParseState.ESCAPE:
                    state = ParseState.STRING
            
            case 92:  # ord('\\')
                if state == ParseState.STRING:
                    state = ParseState.ESCAPE
            
            case 63:  # ord('?')
                if state == ParseState.NORMAL:
                    param_positions.append(i)
                    param_positions.append(i + 1)
            
            case 96:  # ord('`')
                if state == ParseState.BACKTICK:
                    state = ParseState.NORMAL
                elif state == ParseState.NORMAL:
                    state = ParseState.BACKTICK
        
        last_char = char
    
    return sql_bytes, param_positions
