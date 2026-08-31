#!/usr/bin/env python -O
# -*- coding: utf-8 -*-
"""
cursor(named_tuple=True) must reject a result set whose columns don't map to
distinct field names.

A row type can only carry a given name once, so two columns sharing one - the
usual case being a join selecting an ``id`` from each table - leave one of them
unreachable. Both drivers used to accept it and lose a column silently, in
different ways: the C extension built a struct sequence with the member twice,
where the second shadows the first, and the pure Python driver renamed the
second to '<name>_1', so the row carried a field the query never asked for.

The names are checked once all the columns of the result set are known. The C
extension builds its row type while reading the result metadata, so it raises
from execute(); the pure Python driver builds it lazily and raises from the
first fetch.

Each driver checks the names its own row type exposes. A name namedtuple can't
take - 'COUNT(*)', a keyword, a leading underscore - is replaced by a
positional one in the pure Python driver, so duplicates of it are not
ambiguous there; the C extension keeps such names, and they stay reachable
with getattr(), so duplicates of them are.

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


def _read(conn: Any, sql: str) -> Any:
    """Run sql on a named tuple cursor, whichever end raises."""
    cur = conn.cursor(named_tuple=True)
    try:
        cur.execute(sql)
        return cur.fetchall()
    finally:
        cur.close()


def test_duplicate_column_name_raises(conn: Any) -> None:
    with pytest.raises(mariadb.ProgrammingError) as exc:
        _read(conn, "SELECT 1 AS a, 2 AS a")
    assert "Duplicate column name 'a'" in str(exc.value)


def test_duplicate_column_name_from_join_raises(conn: Any) -> None:
    with pytest.raises(mariadb.ProgrammingError) as exc:
        _read(conn, "SELECT 1 AS id, 'x' AS id")
    assert "Duplicate column name 'id'" in str(exc.value)


def test_more_than_two_duplicates_raise(conn: Any) -> None:
    with pytest.raises(mariadb.ProgrammingError):
        _read(conn, "SELECT 1 AS a, 2 AS a, 3 AS a")


def test_distinct_column_names_still_work(conn: Any) -> None:
    rows = _read(conn, "SELECT 1 AS a, 2 AS b")
    assert tuple(rows[0]) == (1, 2)
    assert rows[0].a == 1
    assert rows[0].b == 2


def _replaces_unusable_names(conn: Any) -> bool:
    """Whether the driver replaces a name namedtuple can't take.

    The pure Python driver substitutes 'column_<n>'; the C extension builds a
    struct sequence, which takes any name, and keeps it.
    """
    cur = conn.cursor(named_tuple=True)
    cur.execute("SELECT 1 AS `def`")
    row = cur.fetchone()
    cur.close()
    return not hasattr(row, "def")


@pytest.mark.parametrize("sql", ["SELECT COUNT(*), COUNT(*)",
                                 "SELECT 1 AS `_foo`, 2 AS `_foo`"])
def test_duplicates_of_a_name_the_row_type_replaces(conn: Any,
                                                    sql: str) -> None:
    if _replaces_unusable_names(conn):
        # Both columns get their own positional name, so neither is hidden
        # and the result set is fine.
        rows = _read(conn, sql)
        assert len(rows[0]) == 2
    else:
        # The raw name is kept and stays reachable - getattr(row, 'COUNT(*)')
        # works - so a duplicate really does hide a column.
        with pytest.raises(mariadb.ProgrammingError):
            _read(conn, sql)


def test_cursor_stays_safe_to_use_after_the_error(conn: Any) -> None:
    # The result set is already stored when the names are checked; it has to
    # be dropped, or a fetch walks a row buffer that was never allocated.
    cur = conn.cursor(named_tuple=True)
    try:
        with pytest.raises(mariadb.ProgrammingError):
            cur.execute("SELECT 1 AS a, 2 AS a")
            cur.fetchall()
        # Reporting no result set or no row are both fine; reading the one
        # that failed is not.
        try:
            assert cur.fetchone() is None
        except mariadb.ProgrammingError:
            pass
    finally:
        cur.close()


def test_connection_is_usable_after_the_error(conn: Any) -> None:
    with pytest.raises(mariadb.ProgrammingError):
        _read(conn, "SELECT 1 AS a, 2 AS a")

    cur = conn.cursor()
    cur.execute("SELECT 42")
    assert cur.fetchone() == (42,)
    cur.close()


@pytest.mark.parametrize("kwargs", [{}, {"dictionary": True}])
def test_other_result_formats_are_unaffected(conn: Any, kwargs: Any) -> None:
    cur = conn.cursor(**kwargs)
    cur.execute("SELECT 1 AS a, 2 AS a")
    assert cur.fetchone() is not None
    cur.close()
