#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""
Text-protocol DATE / DATETIME / TIMESTAMP / TIME decoding, driven through the wire
fake server so every value shape the server can send is covered without a
database: plain seconds, fractional seconds of 1..6 digits (DATETIME(n)),
zero dates and impossible dates (returned as None), and NULL.

The pure-Python client decodes these with datetime.fromisoformat() and falls
back to a field-by-field parser when that raises (zero dates; and, before
Python 3.11, fractional widths other than 3 or 6); both paths must agree.
"""

import datetime
import unittest

import mariadb
from tests.unit._fakeserver import (
    FakeServer, scripted_handler, query_text, fake_conf, text_resultset, ok,
    MYSQL_TYPE_DATE, MYSQL_TYPE_DATETIME, MYSQL_TYPE_TIMESTAMP, MYSQL_TYPE_TIME,
)

_MARKER = "fake_table_marker"

COLS = [("dt", MYSQL_TYPE_DATETIME), ("ts", MYSQL_TYPE_TIMESTAMP), ("d", MYSQL_TYPE_DATE)]

# (wire text of dt, wire text of ts, wire text of d) -> expected tuple
CASES = [
    (("2024-01-01 12:34:56", "2024-01-01 12:34:56", "2024-01-01"),
     (datetime.datetime(2024, 1, 1, 12, 34, 56), datetime.datetime(2024, 1, 1, 12, 34, 56), datetime.date(2024, 1, 1))),
    # fractional seconds, every width a DATETIME(n) column can produce
    (("2024-06-15 23:59:59.5", "2024-06-15 23:59:59.12", "2024-02-29"),
     (datetime.datetime(2024, 6, 15, 23, 59, 59, 500000), datetime.datetime(2024, 6, 15, 23, 59, 59, 120000), datetime.date(2024, 2, 29))),
    (("2024-06-15 23:59:59.123", "2024-06-15 23:59:59.1234", "1000-01-01"),
     (datetime.datetime(2024, 6, 15, 23, 59, 59, 123000), datetime.datetime(2024, 6, 15, 23, 59, 59, 123400), datetime.date(1000, 1, 1))),
    (("2024-06-15 23:59:59.12345", "9999-12-31 23:59:59.999999", "9999-12-31"),
     (datetime.datetime(2024, 6, 15, 23, 59, 59, 123450), datetime.datetime(9999, 12, 31, 23, 59, 59, 999999), datetime.date(9999, 12, 31))),
    (("2024-01-01 00:00:00.000000", "2024-01-01 00:00:00.000", "2024-12-31"),
     (datetime.datetime(2024, 1, 1), datetime.datetime(2024, 1, 1), datetime.date(2024, 12, 31))),
    # zero dates and impossible dates decode to None
    (("0000-00-00 00:00:00", "2008-08-00 10:00:00", "0000-00-00"),
     (None, None, None)),
    (("2024-02-30 00:00:00", "2024-00-01 00:00:00", "2023-02-29"),
     (None, None, None)),
    # SQL NULL
    ((None, None, None), (None, None, None)),
]
ROWS = [wire for wire, _ in CASES]
EXPECTED = [expected for _, expected in CASES]


def _responder():
    def on_query(payload):
        if _MARKER in query_text(payload):
            return text_resultset(COLS, ROWS)
        return ok()
    return on_query


def test_text_temporal_sync():
    with FakeServer(scripted_handler(on_query=_responder())) as s:
        con = mariadb.connect(**fake_conf(s.port))
        cur = con.cursor()
        cur.execute(f"SELECT dt, ts, d FROM {_MARKER}")
        rows = cur.fetchall()
        con.close()
    assert rows == EXPECTED


class TestTextTemporalAsync(unittest.IsolatedAsyncioTestCase):
    async def test_text_temporal_async(self):
        with FakeServer(scripted_handler(on_query=_responder())) as s:
            con = await mariadb.asyncConnect(**fake_conf(s.port))
            cur = con.cursor()
            await cur.execute(f"SELECT dt, ts, d FROM {_MARKER}")
            rows = await cur.fetchall()
            await con.close()
        self.assertEqual(rows, EXPECTED)


# TIME: '[-]HHH:MM:SS[.ffffff]', hours may exceed 24 and reach the server's
# +-838:59:59 bound; decoded as a (possibly negative) timedelta.
TIME_COLS = [("t", MYSQL_TYPE_TIME)]
TIME_CASES = [
    ("00:00:00", datetime.timedelta(0)),
    ("12:34:56", datetime.timedelta(hours=12, minutes=34, seconds=56)),
    ("12:34:56.5", datetime.timedelta(hours=12, minutes=34, seconds=56, microseconds=500000)),
    ("12:34:56.123456", datetime.timedelta(hours=12, minutes=34, seconds=56, microseconds=123456)),
    ("-12:34:56.123456", -datetime.timedelta(hours=12, minutes=34, seconds=56, microseconds=123456)),
    ("-00:00:01", -datetime.timedelta(seconds=1)),
    ("838:59:59", datetime.timedelta(hours=838, minutes=59, seconds=59)),
    ("-838:59:59.999999", -datetime.timedelta(hours=838, minutes=59, seconds=59, microseconds=999999)),
    (None, None),
]
TIME_ROWS = [(wire,) for wire, _ in TIME_CASES]
TIME_EXPECTED = [(expected,) for _, expected in TIME_CASES]


def _time_responder():
    def on_query(payload):
        if _MARKER in query_text(payload):
            return text_resultset(TIME_COLS, TIME_ROWS)
        return ok()
    return on_query


def test_text_time_sync():
    with FakeServer(scripted_handler(on_query=_time_responder())) as s:
        con = mariadb.connect(**fake_conf(s.port))
        cur = con.cursor()
        cur.execute(f"SELECT t FROM {_MARKER}")
        rows = cur.fetchall()
        con.close()
    assert rows == TIME_EXPECTED


class TestTextTimeAsync(unittest.IsolatedAsyncioTestCase):
    async def test_text_time_async(self):
        with FakeServer(scripted_handler(on_query=_time_responder())) as s:
            con = await mariadb.asyncConnect(**fake_conf(s.port))
            cur = con.cursor()
            await cur.execute(f"SELECT t FROM {_MARKER}")
            rows = await cur.fetchall()
            await con.close()
        self.assertEqual(rows, TIME_EXPECTED)
