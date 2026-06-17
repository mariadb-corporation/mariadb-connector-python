#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""
Connector behaviors exercised against the in-process MySQL/MariaDB wire fake
server (tests/unit/_fakeserver.py) -- no database required.

* ``TestFakeServerCodecs`` -- result-value decoding that a real MariaDB server
  can't easily produce, e.g. a JSON (type 245) column: MariaDB sends JSON as
  LONGTEXT on the wire, so the type-245 byte layout is served by the fake server.
  Runs on both implementations.
* ``TestCExtAsyncCont`` -- the C extension's async ``*_cont`` continuation paths.
  On a fast localhost socket the ``*_start`` calls complete immediately, so the
  fake server drips command responses byte-by-byte (slow=True) to force the event
  loop through ``*_cont``. C extension only; the pure-Python async client uses a
  different (add_reader) mechanism covered by test_cursor_async /
  test_streaming_async.
"""

import unittest

import mariadb
from tests.base_test import is_native
from tests.unit._fakeserver import (
    FakeServer, scripted_handler, query_text, fake_conf,
    text_resultset, binary_resultset, text_multi_resultset, prepare_ok, ok,
    MYSQL_TYPE_LONG, MYSQL_TYPE_VAR_STRING,
)

_MARKER = "fake_table_marker"
_MYSQL_TYPE_JSON = 245


class TestFakeServerCodecs(unittest.TestCase):
    """Result decoding via the fake server (no DB); runs on both implementations."""

    def test_json_text_decode_fake(self):
        # text-protocol MYSQL_TYPE_JSON (245) decode (C: field_to_python JSON branch)
        cols = [("j", _MYSQL_TYPE_JSON)]
        payload = '{"a": 1}'
        h = scripted_handler(
            on_query=lambda p: text_resultset(cols, [(payload,)])
            if _MARKER in query_text(p) else ok())
        with FakeServer(h) as s:
            con = mariadb.connect(**fake_conf(s.port))
            cur = con.cursor()
            cur.execute(f"SELECT j FROM {_MARKER}")
            self.assertEqual(cur.fetchone()[0], payload)
            con.close()

    def test_json_binary_decode_fake(self):
        # binary-protocol MYSQL_TYPE_JSON (245) decode
        cols = [("j", _MYSQL_TYPE_JSON)]
        payload = '{"b": 2}'
        h = scripted_handler(
            on_prepare=lambda p: prepare_ok(stmt_id=1, columns=cols, num_params=1),
            on_execute=lambda p: binary_resultset(cols, [(payload,)]))
        with FakeServer(h) as s:
            con = mariadb.connect(**fake_conf(s.port))
            cur = con.cursor(binary=True)
            cur.execute(f"SELECT j FROM {_MARKER} WHERE j > ?", (0,))
            self.assertEqual(cur.fetchone()[0], payload)
            con.close()


class TestCExtAsyncCont(unittest.IsolatedAsyncioTestCase):
    """Drive the async *_cont continuation paths. On a fast localhost socket the
    *_start calls always complete immediately, so *_cont is never reached. Here a
    fake server drips command responses byte-by-byte (slow=True), forcing each
    _start to return a wait-status and the event loop to invoke _cont. C-only"""

    async def asyncSetUp(self):
        if is_native():
            self.skipTest("C-extension async continuation paths")

    async def test_text_query_and_fetch_cont(self):
        # MrdbConnection_async_real_query_cont + MrdbCursor_fetch_row_cont
        cols = [("a", MYSQL_TYPE_LONG), ("b", MYSQL_TYPE_VAR_STRING)]
        rows = [(1, "x"), (2, "y")]
        h = scripted_handler(
            on_query=lambda p: text_resultset(cols, rows) if _MARKER in query_text(p) else ok(),
            slow=True)
        with FakeServer(h) as s:
            con = await mariadb.asyncConnect(**fake_conf(s.port))
            cur = con.cursor()
            await cur.execute(f"SELECT a, b FROM {_MARKER}")
            self.assertEqual(await cur.fetchall(), [(1, "x"), (2, "y")])
            await con.close()

    async def test_binary_prepare_execute_fetch_cont(self):
        # MrdbCursor_stmt_prepare_cont + stmt_execute_cont + stmt_fetch_cont
        cols = [("n", MYSQL_TYPE_LONG)]
        rows = [(10,), (20,)]
        h = scripted_handler(
            on_prepare=lambda p: prepare_ok(stmt_id=1, columns=cols, num_params=1),
            on_execute=lambda p: binary_resultset(cols, rows),
            slow=True)
        with FakeServer(h) as s:
            con = await mariadb.asyncConnect(**fake_conf(s.port))
            cur = con.cursor(binary=True)
            await cur.execute(f"SELECT n FROM {_MARKER} WHERE n > ?", (5,))
            self.assertEqual(await cur.fetchall(), [(10,), (20,)])
            await con.close()

    async def test_next_result_cont(self):
        # MrdbCursor_async_next_result_cont (text multi-result, dripped)
        cols = [("v", MYSQL_TYPE_LONG)]
        sets = [(cols, [(100,)]), (cols, [(200,)])]
        h = scripted_handler(
            on_query=lambda p: text_multi_resultset(sets) if _MARKER in query_text(p) else ok(),
            slow=True)
        with FakeServer(h) as s:
            con = await mariadb.asyncConnect(**fake_conf(s.port))
            cur = con.cursor(buffered=False)
            await cur.execute(f"SELECT v FROM {_MARKER}")
            self.assertEqual((await cur.fetchone())[0], 100)
            self.assertTrue(await cur.nextset())
            self.assertEqual((await cur.fetchone())[0], 200)
            await con.close()

    async def test_connection_op_conts(self):
        # ping_cont / reset_cont / dump_debug_info_cont (default slow OK response)
        h = scripted_handler(slow=True)
        with FakeServer(h) as s:
            con = await mariadb.asyncConnect(**fake_conf(s.port))
            await con.ping()
            await con.reset()
            try:
                await con.dump_debug_info()
            except mariadb.Error:
                pass
            await con.close()


if __name__ == "__main__":
    unittest.main()
