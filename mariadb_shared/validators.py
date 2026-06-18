# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""Shared validators for connection options (used by both the pure-Python and
C-extension implementations so they accept exactly the same values)."""

from typing import Any

from .exceptions import ProgrammingError


def validate_bool(value: Any, name: str) -> bool:
    """Strictly parse a boolean connection option.

    Accepts ``True`` / ``'true'`` / ``1`` / ``'1'`` -> ``True`` and
    ``False`` / ``'false'`` / ``0`` / ``'0'`` -> ``False`` (strings are
    case-insensitive). Any other value raises ``ProgrammingError`` so a typo such
    as ``ssl='ture'`` fails loudly instead of being silently truthy.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):              # bool is already handled above
        if value == 0:
            return False
        if value == 1:
            return True
    elif isinstance(value, str):
        v = value.strip().lower()
        if v in ('true', '1'):
            return True
        if v in ('false', '0'):
            return False
    raise ProgrammingError(
        f"Invalid boolean value for option '{name}': {value!r}. "
        "Expected one of True/'true'/1 or False/'false'/0."
    )
