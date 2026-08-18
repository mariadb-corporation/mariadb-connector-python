#!/usr/bin/env python -O
# -*- coding: utf-8 -*-
"""
Regression tests for CONPY-379.

The C extension built the row type for cursor(named_tuple=True) by pointing
each struct sequence member name straight at MYSQL_FIELD.name, which is owned
by the result set. CPython copies the PyMemberDef array into the type but not
the strings it points to, so once the result set was released - on the next
execute(), on cursor.close() or on connection.close() - the type kept dangling
pointers.

Attribute access stayed correct because the member descriptor interns its own
copy of the name. repr() did not: struct sequence repr reads
tp_members[i].name directly and strlen()s it, so it printed whatever the
allocator had since put there, typically data from a later query on the same
connection, and segfaulted once the block had been returned to the OS.

The pure Python driver builds rows with collections.namedtuple and was never
affected; it is covered here so both drivers keep the same behaviour.

``mariadb`` resolves to whichever implementation MARIADB_PYTHON_CONNECTOR
selects, so mariadb_c is exercised explicitly as well - the defect is in the
C extension and must be covered on the pure Python leg of the matrix too.
"""
from __future__ import annotations

from typing import Any

import pytest

import mariadb
mariadb_c = pytest.importorskip("mariadb_c")

from ..conftest import get_test_config as conf


@pytest.fixture(params=["selected", "c"])
def driver(request: Any) -> Any:
    return mariadb if request.param == "selected" else mariadb_c


@pytest.fixture
def conn(driver: Any) -> Any:
    connection = driver.connect(**conf())
    yield connection
    connection.close()


def test_repr_after_cursor_close(conn: Any) -> None:
    """Rows outliving their cursor must still repr their own names."""
    name = "a" * 32
    cur = conn.cursor(named_tuple=True)
    cur.execute(f"SELECT 1 AS {name}")
    rows = cur.fetchall()
    cur.close()

    assert name in repr(rows[0])
    assert rows[0][0] == 1
    assert getattr(rows[0], name) == 1


def test_no_disclosure_from_later_query(conn: Any) -> None:
    """The freed field name buffer used to be recycled by a later query, which
    printed that query's data as the column name."""
    name = "a" * 32
    secret = "SECRET_" + "S" * 300

    cur = conn.cursor(named_tuple=True)
    cur.execute(f"SELECT 1 AS {name}")
    rows = cur.fetchall()
    cur.close()

    other = conn.cursor()
    other.execute(f"SELECT '{secret}'")
    other.fetchall()
    other.close()

    assert "SECRET_" not in repr(rows[0])
    assert name in repr(rows[0])


def test_repr_after_next_execute(conn: Any) -> None:
    """The result set is released by the next execute() on the same cursor,
    which is enough to reach the freed names."""
    cur = conn.cursor(named_tuple=True)
    cur.execute("SELECT 1 AS first_column")
    rows = cur.fetchall()
    cur.execute("SELECT 2 AS second_column")
    cur.fetchall()

    assert "first_column" in repr(rows[0])
    cur.close()


def test_repr_after_connection_close(driver: Any) -> None:
    """Large field name blocks are released to the OS on close, which turned
    the dangling read into a segfault."""
    connection = driver.connect(**conf())
    cur = connection.cursor(named_tuple=True)
    cols = ",".join("1 AS %s%d" % ("z" * 200, i) for i in range(300))
    cur.execute("SELECT " + cols)
    rows = cur.fetchall()
    cur.close()
    connection.close()

    assert "z" * 200 in repr(rows[0])
    assert len(rows[0]) == 300


def test_column_named_like_internal_key() -> None:
    """The C extension keeps the copied names in an attribute on the row type.
    A column with that name must keep its own value.

    C extension only: the pure Python driver builds rows with namedtuple,
    which rejects field names starting with an underscore.
    """
    connection = mariadb_c.connect(**conf())
    try:
        cur = connection.cursor(named_tuple=True)
        cur.execute("SELECT 1 AS _mariadb_field_names, 2 AS other")
        rows = cur.fetchall()
        cur.close()

        assert rows[0]._mariadb_field_names == 1
        assert rows[0].other == 2
        assert "_mariadb_field_names" in repr(rows[0])
    finally:
        connection.close()
