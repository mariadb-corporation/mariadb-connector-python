#!/usr/bin/env python -O
# -*- coding: utf-8 -*-
"""
Regression tests for CONPY-378.

The text protocol rendered a parameter with str(), so a timezone-aware value
carried its offset into the SQL literal:

    TIMESTAMP'2026-08-14 04:00:00+00:00'
    -> Incorrect DATETIME value (errno 1292)

No DATETIME or TIME column accepts that, so every insert of an aware value
failed - while the binary protocol, on the same connection, accepted it. The
two protocols disagreed: binary keeps the wall clock and drops the zone, which
is also what 1.1 did.

The text protocol now drops the offset the same way, so both protocols store
the same value. Note this is deliberately lossy: 04:00+02:00 is stored as
04:00, not converted to 02:00 UTC. That matches the binary protocol and 1.1;
callers wanting UTC must convert before binding.
"""
from __future__ import annotations

import datetime
from typing import Any

import pytest

import mariadb

from ..conftest import get_test_config as conf

TZ_PLUS_2 = datetime.timezone(datetime.timedelta(hours=2))
TZ_MINUS_5 = datetime.timezone(datetime.timedelta(hours=-5))


@pytest.fixture
def conn() -> Any:
    connection = mariadb.connect(**conf())
    cur = connection.cursor()
    cur.execute("DROP TABLE IF EXISTS conpy378")
    cur.execute("CREATE TABLE conpy378 (d DATETIME, t TIME)")
    cur.close()
    yield connection
    cur = connection.cursor()
    cur.execute("DROP TABLE IF EXISTS conpy378")
    cur.close()
    connection.close()


def _roundtrip(connection: Any, binary: bool, dt: Any, tm: Any) -> tuple[Any, Any]:
    cur = connection.cursor(binary=binary)
    cur.execute("INSERT INTO conpy378 VALUES (?,?)", (dt, tm))
    cur.close()
    cur = connection.cursor()
    cur.execute("SELECT d, t FROM conpy378")
    row = cur.fetchone()
    cur.execute("DELETE FROM conpy378")
    cur.close()
    return row[0], row[1]


@pytest.mark.parametrize("tz", [datetime.timezone.utc, TZ_PLUS_2, TZ_MINUS_5])
@pytest.mark.parametrize("binary", [False, True], ids=["text", "binary"])
def test_aware_values_are_accepted(conn: Any, tz: Any, binary: bool) -> None:
    dt = datetime.datetime(2026, 8, 14, 4, 30, 15, tzinfo=tz)
    tm = datetime.time(4, 30, 15, tzinfo=tz)
    stored_d, stored_t = _roundtrip(conn, binary, dt, tm)
    # the wall clock is kept, the offset dropped - not converted to UTC
    assert stored_d == datetime.datetime(2026, 8, 14, 4, 30, 15)
    assert stored_t == datetime.timedelta(hours=4, minutes=30, seconds=15)


@pytest.mark.parametrize("tz", [datetime.timezone.utc, TZ_PLUS_2, TZ_MINUS_5])
def test_text_and_binary_agree_on_aware_values(conn: Any, tz: Any) -> None:
    dt = datetime.datetime(2026, 8, 14, 4, 30, 15, tzinfo=tz)
    tm = datetime.time(4, 30, 15, tzinfo=tz)
    assert _roundtrip(conn, False, dt, tm) == _roundtrip(conn, True, dt, tm)


@pytest.mark.parametrize("binary", [False, True], ids=["text", "binary"])
def test_naive_values_are_unchanged(conn: Any, binary: bool) -> None:
    dt = datetime.datetime(2026, 8, 14, 4, 30, 15)
    tm = datetime.time(4, 30, 15)
    stored_d, stored_t = _roundtrip(conn, binary, dt, tm)
    assert stored_d == dt
    assert stored_t == datetime.timedelta(hours=4, minutes=30, seconds=15)


def test_aware_value_with_microseconds(conn: Any) -> None:
    dt = datetime.datetime(2026, 8, 14, 4, 30, 15, 123456, tzinfo=TZ_PLUS_2)
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS conpy378us")
    cur.execute("CREATE TABLE conpy378us (d DATETIME(6))")
    try:
        cur.execute("INSERT INTO conpy378us VALUES (?)", (dt,))
        cur.execute("SELECT d FROM conpy378us")
        assert cur.fetchone()[0] == dt.replace(tzinfo=None)
    finally:
        cur.execute("DROP TABLE IF EXISTS conpy378us")
        cur.close()


def test_date_parameter_still_works(conn: Any) -> None:
    # dates carry no tzinfo; guard against the change touching them
    cur = conn.cursor()
    cur.execute("SELECT CAST(? AS DATE)", (datetime.date(2026, 8, 14),))
    assert cur.fetchone()[0] == datetime.date(2026, 8, 14)
    cur.close()


if __name__ == "__main__":
    pytest.main([__file__])
