#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""Member names of cursor(named_tuple=True) rows.

A row type can only carry a given name once, so two columns sharing one - the
usual case being a join selecting an ``id`` from each table - would leave one
of them unreachable. Both drivers used to accept it and lose a column silently,
then refused the result set with a ProgrammingError.

One rule now, identical in the C extension and the pure Python driver: a
column name is kept when collections.namedtuple accepts it - a valid
identifier, not a keyword, no leading underscore, not used by an earlier
column. Any other name is replaced by the column position, 'column_<index>',
with '_1', '_2', ... appended should that name itself be taken. Every column
stays reachable as an attribute, no member shadows another, and the statement
never fails because of its column names. cursor.description keeps the names
as the server sent them.

``mariadb`` resolves to whichever implementation MARIADB_PYTHON_CONNECTOR
selects, so mariadb_c is exercised explicitly as well.
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


def _row(conn: Any, sql: str, **kwargs: Any) -> tuple[Any, list[str]]:
    """The first row of sql on a named tuple cursor, and the description names."""
    cur = conn.cursor(named_tuple=True, **kwargs)
    try:
        cur.execute(sql)
        row = cur.fetchone()
        return row, [d[0] for d in cur.description]
    finally:
        cur.close()


def test_duplicate_column_name_is_renamed(conn: Any) -> None:
    row, names = _row(conn, "SELECT 1 AS a, 2 AS a")
    assert row.a == 1
    assert row.column_1 == 2
    assert tuple(row) == (1, 2)
    assert names == ["a", "a"]


def test_duplicate_column_name_from_join(conn: Any) -> None:
    row, _ = _row(conn, "SELECT 1 AS id, 'x' AS id")
    assert (row.id, row.column_1) == (1, "x")


def test_more_than_two_duplicates(conn: Any) -> None:
    row, _ = _row(conn, "SELECT 1 AS a, 2 AS a, 3 AS a")
    assert (row.a, row.column_1, row.column_2) == (1, 2, 3)


@pytest.mark.parametrize("sql, expected", [
    ("SELECT 1 AS `COUNT(*)`, 2 AS `not an id`", ("column_0", "column_1")),
    ("SELECT 1 AS `_foo`, 2 AS `_bar`", ("column_0", "column_1")),
    ("SELECT 1 AS `def`, 2 AS `class`, 3 AS ok", ("column_0", "column_1", "ok")),
    ("SELECT COUNT(*), COUNT(*) + 1", ("column_0", "column_1")),
])
def test_name_namedtuple_cannot_carry_is_renamed(conn: Any, sql: str,
                                                 expected: tuple[str, ...]) -> None:
    row, _ = _row(conn, sql)
    for i, name in enumerate(expected):
        assert getattr(row, name) == i + 1
    assert f"{expected[0]}=1" in repr(row)


def test_identifiers_are_kept(conn: Any) -> None:
    row, names = _row(conn, "SELECT 1 AS héllo, 2 AS `日本`, 3 AS count, 4 AS `index`")
    assert names == ["héllo", "日本", "count", "index"]
    assert (getattr(row, "héllo"), getattr(row, "日本"), row.count, row.index) == (1, 2, 3, 4)


def test_positional_name_already_taken_by_a_column(conn: Any) -> None:
    # a column may itself be called column_1; the replacement then gets a
    # counter until it is free
    row, _ = _row(conn, "SELECT 1 AS column_1, 2 AS column_1")
    assert (row.column_1, row.column_1_1) == (1, 2)

    row, _ = _row(conn, "SELECT 1 AS a, 2 AS a, 3 AS column_1")
    assert (row.a, row.column_1, row.column_2) == (1, 2, 3)

    row, _ = _row(conn, "SELECT 1 AS `def`, 2 AS column_0")
    assert (row.column_0, row.column_1) == (1, 2)


def test_distinct_column_names_still_work(conn: Any) -> None:
    row, _ = _row(conn, "SELECT 1 AS a, 2 AS b")
    assert tuple(row) == (1, 2)
    assert (row.a, row.b) == (1, 2)


def test_unbuffered_cursor(conn: Any) -> None:
    row, _ = _row(conn, "SELECT 1 AS a, 2 AS a UNION ALL SELECT 3, 4", buffered=False)
    assert (row.a, row.column_1) == (1, 2)


def test_cursor_is_reusable(conn: Any) -> None:
    cur = conn.cursor(named_tuple=True)
    cur.execute("SELECT 1 AS a, 2 AS a")
    assert cur.fetchone().column_1 == 2
    cur.execute("SELECT 3 AS a, 4 AS b")
    assert cur.fetchone().b == 4
    cur.close()


@pytest.mark.parametrize("kwargs", [{}, {"dictionary": True}])
def test_other_result_formats_are_unaffected(conn: Any, kwargs: Any) -> None:
    cur = conn.cursor(**kwargs)
    cur.execute("SELECT 1 AS a, 2 AS a")
    assert cur.fetchone() is not None
    cur.close()
