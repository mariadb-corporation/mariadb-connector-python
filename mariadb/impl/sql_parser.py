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

from typing import List, Tuple

def split_sql_parts(sql: str) -> Tuple[bytes, List[int]]:
    """
    Find positions of positional placeholders (?) in SQL and return SQL as bytes.

    Args:
        sql: SQL statement

    Returns:
        Tuple of (sql_bytes, placeholder_byte_positions)
        - sql_bytes: SQL encoded as UTF-8 bytes
        - placeholder_byte_positions: List of byte positions (start, end) pairs
    """
    sql_bytes = sql.encode('utf-8')
    param_positions: List[int] = []

    NORMAL = 0
    STRING = 1
    ESCAPE = 2
    BACKTICK = 3
    EOL = 4
    COMMENT = 5
    state = NORMAL
    single_quotes = False

    last_char = 0  # only used for comment detection

    for i, c in enumerate(sql_bytes):
        if state == ESCAPE:
            # Escaped char ends escape sequence
            state = STRING
            last_char = c
            continue

        if state == NORMAL:
            # Use dict lookup for clarity if desired
            if c == 63:  # '?'
                param_positions.append(i)
                param_positions.append(i + 1)
            elif c == 39:  # "'"
                state = STRING
                single_quotes = True
            elif c == 34:  # '"'
                state = STRING
                single_quotes = False
            elif c == 96:  # '`'
                state = BACKTICK
            elif c == 92:  # '\'
                pass  # nothing to do in NORMAL
            elif c == 42:  # '*'
                if last_char == 47:  # '/*'
                    # Check for executable comment
                    if i + 1 < len(sql_bytes):
                        next_c = sql_bytes[i + 1]
                        if next_c not in (33, 77):  # '!' or 'M'
                            state = COMMENT
                    else:
                        state = COMMENT
            elif c == 47:  # '/'
                if last_char == 42:  # end of comment '*/'
                    state = NORMAL
                elif last_char == 47:  # start of // comment
                    state = EOL
            elif c == 35:  # '#'
                state = EOL
            elif c == 45:  # '-'
                if last_char == 45:  # '--'
                    state = EOL

        elif state == STRING:
            if c == 92:  # '\'
                state = ESCAPE
            elif (c == 39 and single_quotes) or (c == 34 and not single_quotes):
                state = NORMAL

        elif state == BACKTICK:
            if c == 96:  # '`'
                state = NORMAL

        elif state == EOL:
            if c == 10:  # '\n'
                state = NORMAL

        elif state == COMMENT:
            if last_char == 42 and c == 47:  # '*/'
                state = NORMAL

        last_char = c

    return sql_bytes, param_positions
