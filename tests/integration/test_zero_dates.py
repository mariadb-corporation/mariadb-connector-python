#!/usr/bin/env python -O
# -*- coding: utf-8 -*-
"""
Regression tests for CONPY-368.

A DATE, DATETIME or TIMESTAMP the server accepts under a lenient sql_mode has
no Python equivalent when one of its components is zero ('2008-08-00',
'0000-00-00'), or when ALLOW_INVALID_DATES kept an impossible day
('2008-02-30'). The C extension called PyDate_FromDate() on such a value, which
returns NULL with a ValueError set, and the pending exception then surfaced far
from its cause. These values must come back as None, matching mysqlclient and
PyMySQL, and both drivers must agree.

Note the two sql_modes are not interchangeable: under '' the server zeroes an
impossible day, so only zero components survive, while ALLOW_INVALID_DATES
stores '2008-02-30' as given. Both are covered.
"""
from __future__ import annotations

import datetime
from typing import Any

import pytest

import mariadb

from ..conftest import get_test_config as conf

# accepted and stored as given under ALLOW_INVALID_DATES
INVALID_DATES = ["2008-02-30", "2009-02-29", "2008-04-31",
                 "2008-00-15", "0000-08-15", "2008-00-00"]
# accepted under a plain lenient sql_mode
ZERO_DATES = ["2008-08-00", "0000-00-00"]


@pytest.fixture
def cursor() -> Any:
    connection = mariadb.connect(**conf())
    cur = connection.cursor()
    cur.execute("DROP TABLE IF EXISTS conpy368")
    cur.execute("CREATE TABLE conpy368 "
                "(id INT PRIMARY KEY, d DATE, dt DATETIME(6), ts TIMESTAMP NULL)")
    yield cur
    cur.execute("DROP TABLE IF EXISTS conpy368")
    cur.close()
    connection.close()


def _insert(cur: Any, sql_mode: str, values: list[str]) -> None:
    cur.execute("SET SESSION sql_mode=%s" % ("'%s'" % sql_mode))
    for i, value in enumerate(values):
        cur.execute("INSERT INTO conpy368 VALUES (?,?,?,?)",
                    (i, value, "%s 12:34:56.789012" % value,
                     "%s 12:34:56" % value))


@pytest.mark.parametrize("binary", [False, True], ids=["text", "binary"])
def test_zero_component_dates_are_none(cursor: Any, binary: bool) -> None:
    _insert(cursor, "", ZERO_DATES)
    for i, value in enumerate(ZERO_DATES):
        if binary:
            cursor.execute("SELECT d, dt, ts FROM conpy368 WHERE id=?", (i,))
        else:
            cursor.execute("SELECT d, dt, ts FROM conpy368 WHERE id=%d" % i)
        assert cursor.fetchone() == (None, None, None), value


@pytest.mark.parametrize("binary", [False, True], ids=["text", "binary"])
def test_invalid_dates_kept_by_the_server_are_none(cursor: Any, binary: bool) -> None:
    _insert(cursor, "ALLOW_INVALID_DATES", INVALID_DATES)
    for i, value in enumerate(INVALID_DATES):
        if binary:
            cursor.execute("SELECT d, dt, ts FROM conpy368 WHERE id=?", (i,))
        else:
            cursor.execute("SELECT d, dt, ts FROM conpy368 WHERE id=%d" % i)
        assert cursor.fetchone() == (None, None, None), value


@pytest.mark.parametrize("binary", [False, True], ids=["text", "binary"])
def test_valid_leap_day_still_round_trips(cursor: Any, binary: bool) -> None:
    cursor.execute("SET SESSION sql_mode='ALLOW_INVALID_DATES'")
    cursor.execute("INSERT INTO conpy368 VALUES "
                   "(1, '2008-02-29', '2008-02-29 12:34:56.789012', "
                   "'2008-02-29 12:34:56')")
    if binary:
        cursor.execute("SELECT d, dt FROM conpy368 WHERE id=?", (1,))
    else:
        cursor.execute("SELECT d, dt FROM conpy368 WHERE id=1")
    row = cursor.fetchone()
    assert row[0] == datetime.date(2008, 2, 29)
    assert row[1] == datetime.datetime(2008, 2, 29, 12, 34, 56, 789012)


def test_a_rejected_row_does_not_abort_the_batch(cursor: Any) -> None:
    # The pending exception used to abort the whole fetch, so a valid row
    # following an unrepresentable one was lost too.
    cursor.execute("SET SESSION sql_mode='ALLOW_INVALID_DATES'")
    cursor.execute("INSERT INTO conpy368 VALUES "
                   "(1, '2008-02-30', '2008-02-30 12:34:56.789012', NULL),"
                   "(2, '2008-03-01', '2008-03-01 12:34:56.789012', NULL)")
    cursor.execute("SELECT id, d FROM conpy368 ORDER BY id")
    assert cursor.fetchall() == [(1, None), (2, datetime.date(2008, 3, 1))]


if __name__ == "__main__":
    pytest.main([__file__])
