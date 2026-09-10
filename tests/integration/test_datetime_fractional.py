#!/usr/bin/env python -O
# -*- coding: utf-8 -*-
"""
DATE / DATETIME(n) / TIMESTAMP(n) values must decode identically over the
text and the binary protocol, for every fractional-seconds precision the
server can declare (0..6 digits), in the sync and the async client.

The pure-Python text decoder uses datetime.fromisoformat() with a
field-by-field fallback; before Python 3.11 fromisoformat() rejects
fractional widths other than 3 or 6, so each width is exercised on a real
column of that precision rather than on a hand-built string.
"""
from __future__ import annotations

import datetime
import unittest
from typing import Any

import pytest

import mariadb

from ..conftest import get_test_config as conf

TABLE = "test_datetime_fractional"
PRECISIONS = range(0, 7)
BASE = "2024-06-15 23:59:59"
FRACTION = "123456"

COLUMNS = ["d"] + [f"dt{p}" for p in PRECISIONS] + [f"ts{p}" for p in PRECISIONS]

DDL = (
    f"CREATE TABLE {TABLE} (id INT PRIMARY KEY, d DATE, "
    + ", ".join(f"dt{p} DATETIME({p})" for p in PRECISIONS) + ", "
    + ", ".join(f"ts{p} TIMESTAMP({p}) NULL" for p in PRECISIONS) + ")"
)


def _value(precision: int) -> str:
    """Wire text the server will send back for a DATETIME(precision) column."""
    return BASE + ("." + FRACTION[:precision] if precision else "")


def _expected(precision: int) -> datetime.datetime:
    micro = int(FRACTION[:precision].ljust(6, "0")) if precision else 0
    return datetime.datetime(2024, 6, 15, 23, 59, 59, micro)


ROW_VALUES = ["2024-06-15"] + [_value(p) for p in PRECISIONS] * 2
ROW_EXPECTED = (datetime.date(2024, 6, 15),) + tuple(_expected(p) for p in PRECISIONS) * 2
NULL_EXPECTED = (None,) * len(COLUMNS)

# A parameter is passed so that a binary=True cursor really uses the binary
# protocol (a parameterless execute always goes over the text protocol).
SELECT = f"SELECT {', '.join(COLUMNS)} FROM {TABLE} WHERE id = ?"


def _setup(cur: Any) -> None:
    cur.execute(f"DROP TABLE IF EXISTS {TABLE}")
    cur.execute(DDL)
    placeholders = ", ".join("?" for _ in COLUMNS)
    cur.execute(f"INSERT INTO {TABLE} VALUES (1, {placeholders})", ROW_VALUES)
    cur.execute(f"INSERT INTO {TABLE} VALUES (2, {placeholders})", [None] * len(COLUMNS))


@pytest.fixture
def connection() -> Any:
    con = mariadb.connect(**conf())
    cur = con.cursor()
    _setup(cur)
    cur.close()
    yield con
    cur = con.cursor()
    cur.execute(f"DROP TABLE IF EXISTS {TABLE}")
    cur.close()
    con.close()


@pytest.mark.parametrize("binary", [False, True], ids=["text", "binary"])
def test_fractional_precisions_sync(connection: Any, binary: bool) -> None:
    cur = connection.cursor(binary=True) if binary else connection.cursor()
    cur.execute(SELECT, (1,))
    assert cur.fetchone() == ROW_EXPECTED
    cur.execute(SELECT, (2,))
    assert cur.fetchone() == NULL_EXPECTED
    cur.close()


class TestFractionalPrecisionsAsync(unittest.IsolatedAsyncioTestCase):
    async def _check(self, binary: bool) -> None:
        con = await mariadb.AsyncConnection.connect(**conf())
        try:
            cur = con.cursor()
            # the setup DDL/INSERTs are plain statements, run them on this connection
            await cur.execute(f"DROP TABLE IF EXISTS {TABLE}")
            await cur.execute(DDL)
            placeholders = ", ".join("?" for _ in COLUMNS)
            await cur.execute(f"INSERT INTO {TABLE} VALUES (1, {placeholders})", ROW_VALUES)
            await cur.execute(f"INSERT INTO {TABLE} VALUES (2, {placeholders})", [None] * len(COLUMNS))
            await cur.close()

            cur = con.cursor(binary=True) if binary else con.cursor()
            await cur.execute(SELECT, (1,))
            self.assertEqual(await cur.fetchone(), ROW_EXPECTED)
            await cur.execute(SELECT, (2,))
            self.assertEqual(await cur.fetchone(), NULL_EXPECTED)
            await cur.close()
        finally:
            cur = con.cursor()
            await cur.execute(f"DROP TABLE IF EXISTS {TABLE}")
            await cur.close()
            await con.close()

    async def test_text(self) -> None:
        await self._check(binary=False)

    async def test_binary(self) -> None:
        await self._check(binary=True)
