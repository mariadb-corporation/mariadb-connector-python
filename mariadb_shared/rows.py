# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Row types of the cursors.

A cursor produces rows whose shape depends on how it, or its connection, was
opened: tuples by default, dicts with ``dictionary=True``, named tuples with
``named_tuple=True``. The interfaces are generic over that row type, and the
``cursor()`` / ``connect()`` overloads pick it when the option is written as
a literal; when it is not known statically the row type is ``Any``.
"""

from typing import Any, Dict, TypeVar

# Covariant: a cursor only ever produces its rows.
RowT_co = TypeVar('RowT_co', covariant=True)

TupleRow = tuple[Any, ...]
"""Row of a default cursor: one value per column, in column order."""

DictRow = Dict[str, Any]
"""Row of a ``dictionary=True`` cursor: column name to value."""
