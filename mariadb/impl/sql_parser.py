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

from functools import lru_cache
from typing import List, Tuple


@lru_cache(maxsize=256)
def split_sql_parts(sql: str) -> Tuple[bytes, List[int]]:
    sql_bytes = sql.encode('utf-8')
    length = len(sql_bytes)
    param_positions: List[int] = []
    
    state = 0  # 0=NORMAL, 1=STRING, 2=ESCAPE, 3=BACKTICK, 4=EOL, 5=COMMENT
    single_quotes = False
    last_char = 0
    i = 0

    while i < length:
        c = sql_bytes[i]
        
        if state == 2:  # ESCAPE
            state = 1
            last_char = c
            i += 1
            continue

        if state == 0:  # NORMAL
            if c == 63:  # '?'
                param_positions.append(i)
                param_positions.append(i + 1)
            elif c == 39:  # "'"
                state = 1
                single_quotes = True
            elif c == 34:  # '"'
                state = 1
                single_quotes = False
            elif c == 96:  # '`'
                state = 3
            elif c == 42 and last_char == 47:  # '/*'
                if i + 1 < length:
                    next_c = sql_bytes[i + 1]
                    if next_c not in (33, 77):  # not '!' or 'M'
                        state = 5
                else:
                    state = 5
            elif c == 47:  # '/'
                if last_char == 42:  # '*/'
                    state = 0
                elif last_char == 47:  # '//'
                    state = 4
            elif c == 35:  # '#'
                state = 4
            elif c == 45 and last_char == 45:  # '--'
                state = 4

        elif state == 1:  # STRING
            if c == 92:  # '\'
                state = 2
            elif (c == 39 and single_quotes) or (c == 34 and not single_quotes):
                state = 0

        elif state == 3:  # BACKTICK
            if c == 96:
                state = 0

        elif state == 4:  # EOL
            if c == 10:  # '\n'
                state = 0

        elif state == 5:  # COMMENT
            if last_char == 42 and c == 47:  # '*/'
                state = 0

        last_char = c
        i += 1

    return sql_bytes, param_positions