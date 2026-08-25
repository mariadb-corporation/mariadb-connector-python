#!/usr/bin/env python -O
# -*- coding: utf-8 -*-
"""
Regression tests for CONPY-385.

cursor(named_tuple=True) built its row type from the column names after
checking only str.isidentifier(). collections.namedtuple rejects more than
non-identifiers, so a perfectly ordinary query raised instead of returning
rows:

    cursor.execute("select 1 as def")
    -> ValueError: Type names and field names cannot be a keyword: 'def'

namedtuple refuses a field name that is not an identifier, that is a keyword,
that starts with an underscore, or that duplicates another. Only the first and
the last were handled, so both reserved words ('def', 'class') and
underscore-prefixed columns ('_foo') crashed. Soft keywords ('match', 'type')
are accepted by namedtuple and must keep their own name.

Offending names become 'column_<position>', which the existing duplicate
suffixing then keeps unique. The C extension uses a struct sequence rather
than namedtuple and never raised, so it is exercised here only to confirm the
query works on both drivers.
"""
from __future__ import annotations

from typing import Any

import pytest

import mariadb

from ..conftest import get_test_config as conf


@pytest.fixture
def conn() -> Any:
    connection = mariadb.connect(**conf())
    yield connection
    connection.close()


@pytest.mark.parametrize("alias", ["def", "class", "return", "None", "lambda"])
def test_keyword_column_name_does_not_raise(conn: Any, alias: str) -> None:
    cur = conn.cursor(named_tuple=True)
    cur.execute(f"SELECT 1 AS `{alias}`")
    row = cur.fetchone()
    cur.close()
    assert tuple(row) == (1,)


def test_underscore_prefixed_column_name_does_not_raise(conn: Any) -> None:
    # namedtuple rejects a leading underscore even though isidentifier() passes
    cur = conn.cursor(named_tuple=True)
    cur.execute("SELECT 1 AS `_foo`, 2 AS other")
    row = cur.fetchone()
    cur.close()
    assert tuple(row) == (1, 2)
    assert row.other == 2


@pytest.mark.parametrize("alias", ["match", "case", "type"])
def test_soft_keyword_column_name_is_preserved(conn: Any, alias: str) -> None:
    # namedtuple accepts soft keywords, so they must not be renamed
    cur = conn.cursor(named_tuple=True)
    cur.execute(f"SELECT 1 AS `{alias}`")
    row = cur.fetchone()
    cur.close()
    assert getattr(row, alias) == 1


def test_renamed_columns_stay_addressable_and_ordered(conn: Any) -> None:
    cur = conn.cursor(named_tuple=True)
    cur.execute("SELECT 1 AS `def`, 2 AS ok, 3 AS `class`")
    row = cur.fetchone()
    cur.close()
    assert tuple(row) == (1, 2, 3)
    assert row.ok == 2
    # the replacement name carries the column position
    assert row[0] == 1 and row[2] == 3


def test_replacement_name_colliding_with_real_column_stays_unique(conn: Any) -> None:
    # 'def' becomes column_0, which is also a real column here. Building the row
    # type at all proves the two were kept distinct: namedtuple raises on a
    # duplicate field name. (The C extension does not rename, so it never
    # collides; only the values are checked on both.)
    cur = conn.cursor(named_tuple=True)
    cur.execute("SELECT 1 AS `def`, 2 AS column_0")
    row = cur.fetchone()
    cur.close()
    assert tuple(row) == (1, 2)


def test_ordinary_column_names_are_untouched(conn: Any) -> None:
    cur = conn.cursor(named_tuple=True)
    cur.execute("SELECT 1 AS alpha, 2 AS beta")
    row = cur.fetchone()
    cur.close()
    assert row.alpha == 1
    assert row.beta == 2


if __name__ == "__main__":
    pytest.main([__file__])
