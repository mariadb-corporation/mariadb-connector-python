#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""
Protocol-level unit tests driving the real connector against an in-process
MySQL/MariaDB wire fake server (tests/unit/_fakeserver.py).

Covers the text, binary (prepared) and bulk protocols for both the sync and
async clients.
"""

import unittest

import pytest

import mariadb
from tests.base_test import is_native
from tests.unit._fakeserver import (
    FakeServer, scripted_handler, query_text, fake_conf,
    text_resultset, binary_resultset, ok, prepare_ok,
    MARIADB_CLIENT_BULK_UNIT_RESULTS, MARIADB_CLIENT_STMT_BULK_OPERATIONS,
    MYSQL_TYPE_LONG, MYSQL_TYPE_VAR_STRING,
)

_MARKER = "fake_table_marker"


def _text_responder(columns, rows):
    def on_query(payload):
        sql = query_text(payload)
        if _MARKER in sql:
            return text_resultset(columns, rows)
        return ok()             # connect-time SET autocommit / SET NAMES, etc.
    return on_query


def _prepare_responder(columns, num_params):
    def on_prepare(payload):
        return prepare_ok(stmt_id=1, columns=columns, num_params=num_params)
    return on_prepare


def _binary_exec_responder(columns, rows):
    def on_execute(payload):
        return binary_resultset(columns, rows)
    return on_execute


# ===========================================================================
# TEXT protocol
# ===========================================================================
TEXT_COLS = [("a", MYSQL_TYPE_VAR_STRING), ("b", MYSQL_TYPE_VAR_STRING)]
TEXT_ROWS = [("1", "x"), ("2", "y"), (None, "z")]
TEXT_EXPECTED = [("1", "x"), ("2", "y"), (None, "z")]


def test_text_select_sync():
    handler = scripted_handler(on_query=_text_responder(TEXT_COLS, TEXT_ROWS))
    with FakeServer(handler) as s:
        con = mariadb.connect(**fake_conf(s.port))
        cur = con.cursor()
        cur.execute(f"SELECT a, b FROM {_MARKER}")
        rows = cur.fetchall()
        con.close()
    assert rows == TEXT_EXPECTED


class TestTextAsync(unittest.IsolatedAsyncioTestCase):
    async def test_text_select_async(self):
        handler = scripted_handler(on_query=_text_responder(TEXT_COLS, TEXT_ROWS))
        with FakeServer(handler) as s:
            con = await mariadb.asyncConnect(**fake_conf(s.port))
            cur = con.cursor()
            await cur.execute(f"SELECT a, b FROM {_MARKER}")
            rows = await cur.fetchall()
            await con.close()
        self.assertEqual(rows, TEXT_EXPECTED)


# ===========================================================================
# BINARY (prepared) protocol
# ===========================================================================
BIN_COLS = [("n", MYSQL_TYPE_LONG), ("s", MYSQL_TYPE_VAR_STRING)]
BIN_ROWS = [(10, "ten"), (20, "twenty"), (None, None)]
BIN_EXPECTED = [(10, "ten"), (20, "twenty"), (None, None)]


def test_binary_execute_sync():
    handler = scripted_handler(
        on_prepare=_prepare_responder(BIN_COLS, num_params=1),
        on_execute=_binary_exec_responder(BIN_COLS, BIN_ROWS))
    with FakeServer(handler) as s:
        con = mariadb.connect(**fake_conf(s.port))
        cur = con.cursor(binary=True)
        cur.execute(f"SELECT n, s FROM {_MARKER} WHERE n > ?", (5,))
        rows = cur.fetchall()
        con.close()
    assert rows == BIN_EXPECTED


class TestBinaryAsync(unittest.IsolatedAsyncioTestCase):
    async def test_binary_execute_async(self):
        handler = scripted_handler(
            on_prepare=_prepare_responder(BIN_COLS, num_params=1),
            on_execute=_binary_exec_responder(BIN_COLS, BIN_ROWS))
        with FakeServer(handler) as s:
            con = await mariadb.asyncConnect(**fake_conf(s.port))
            cur = con.cursor(binary=True)
            await cur.execute(f"SELECT n, s FROM {_MARKER} WHERE n > ?", (5,))
            rows = await cur.fetchall()
            await con.close()
        self.assertEqual(rows, BIN_EXPECTED)


# ===========================================================================
# BULK protocol (executemany)
# ===========================================================================
_BULK_ROWCOUNT = 3


def _bulk_handler():
    # Advertise BULK_UNIT_RESULTS so executemany takes the COM_STMT_BULK_EXECUTE
    # path; respond to PREPARE then to the bulk/execute with an OK carrying the
    # batch affected-row count.
    return scripted_handler(
        on_prepare=_prepare_responder([], num_params=1),
        on_execute=lambda payload: ok(affected_rows=1),
        on_bulk=lambda payload: ok(affected_rows=_BULK_ROWCOUNT),
        extended_caps=MARIADB_CLIENT_BULK_UNIT_RESULTS | MARIADB_CLIENT_STMT_BULK_OPERATIONS)


def test_bulk_executemany_sync():
    with FakeServer(_bulk_handler()) as s:
        con = mariadb.connect(**fake_conf(s.port))
        cur = con.cursor()
        cur.executemany(f"INSERT INTO {_MARKER} VALUES (?)", [(1,), (2,), (3,)])
        rowcount = cur.rowcount
        con.close()
    assert rowcount == _BULK_ROWCOUNT


class TestBulkAsync(unittest.IsolatedAsyncioTestCase):
    async def test_bulk_executemany_async(self):
        with FakeServer(_bulk_handler()) as s:
            con = await mariadb.asyncConnect(**fake_conf(s.port))
            cur = con.cursor()
            await cur.executemany(f"INSERT INTO {_MARKER} VALUES (?)", [(1,), (2,), (3,)])
            rowcount = cur.rowcount
            await con.close()
        self.assertEqual(rowcount, _BULK_ROWCOUNT)


# ===========================================================================
# Streaming multi-result-set nextset() — sync & async parity
# ===========================================================================
from tests.unit._fakeserver import text_multi_resultset

_MULTI_COLS = [("v", MYSQL_TYPE_LONG)]
_MULTI_SETS = [(_MULTI_COLS, [(100,)]), (_MULTI_COLS, [(200,)])]


# These validate the pure-Python sync/async parity fix; the C extension's
# multi-result handling is libmariadb's and is covered by the real-DB
# integration tests (test_streaming_async.py), and the fake server's two-set
# framing is not a reliable target for libmariadb's stricter sync path.
py_only = pytest.mark.skipif(not is_native(),
                             reason="pure-Python parity fix; C multi-result covered by integration tests")


def _multi_responder():
    def on_query(payload):
        if _MARKER in query_text(payload):
            return text_multi_resultset(_MULTI_SETS)
        return ok()
    return on_query


@py_only
def test_streaming_multi_resultset_sync():
    """Sync streaming (buffered=False) cursor must advance across result sets
    via nextset() (parity with async)."""
    with FakeServer(scripted_handler(on_query=_multi_responder())) as s:
        con = mariadb.connect(**fake_conf(s.port))
        cur = con.cursor(buffered=False)
        cur.execute(f"SELECT v FROM {_MARKER}")
        first = cur.fetchone()
        has_next = cur.nextset()
        second = cur.fetchone()
        con.close()
    assert first == (100,)
    assert has_next is True
    assert second == (200,)


class TestStreamingMultiAsync(unittest.IsolatedAsyncioTestCase):
    @py_only
    async def test_streaming_multi_resultset_async(self):
        with FakeServer(scripted_handler(on_query=_multi_responder())) as s:
            con = await mariadb.asyncConnect(**fake_conf(s.port))
            cur = con.cursor(buffered=False)
            await cur.execute(f"SELECT v FROM {_MARKER}")
            first = await cur.fetchone()
            has_next = await cur.nextset()
            second = await cur.fetchone()
            await con.close()
        self.assertEqual(first, (100,))
        self.assertIs(has_next, True)
        self.assertEqual(second, (200,))


# ===========================================================================
# Binary streaming multi-result guard (pure-Python)
# ===========================================================================
class TestBinaryStreamingGuard(unittest.IsolatedAsyncioTestCase):
    async def test_binary_streaming_nextset_raises(self):
        """The pure-Python async client guards binary streaming multi-result
        nextset() with NotSupportedError instead of corrupting the stream. The C
        extension handles binary streaming natively, so this is python-only."""
        if not is_native():
            self.skipTest("guard is pure-Python only; C handles binary streaming natively")
        cols = [("n", MYSQL_TYPE_LONG)]
        handler = scripted_handler(
            on_prepare=_prepare_responder(cols, num_params=1),
            # First binary set carries MORE_RESULTS_EXIST (last=False).
            on_execute=lambda payload: binary_resultset(cols, [(1,)], last=False))
        with FakeServer(handler) as s:
            con = await mariadb.asyncConnect(**fake_conf(s.port))
            cur = con.cursor(binary=True, buffered=False)
            # A parameter forces the binary (prepared) protocol path.
            await cur.execute(f"SELECT n FROM {_MARKER} WHERE n > ?", (0,))
            self.assertEqual(await cur.fetchone(), (1,))
            with self.assertRaises(mariadb.NotSupportedError):
                await cur.nextset()
            await con.close()


if __name__ == "__main__":
    unittest.main()
