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


def validate_int(value: Any, name: str) -> int:
    """Strictly parse an integer connection option.

    Accepts an ``int`` or a string of digits (``3306`` or ``'3306'``), so an
    option read from a config file or an environment variable works without the
    caller converting it. Anything else raises ``ProgrammingError`` naming the
    option, rather than the bare "'str' object cannot be interpreted as an
    integer" the C argument parser produced (CONPY-331).
    """
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        v = value.strip()
        try:
            return int(v)
        except ValueError:
            pass
    raise ProgrammingError(
        f"Invalid integer value for option '{name}': {value!r}."
    )
