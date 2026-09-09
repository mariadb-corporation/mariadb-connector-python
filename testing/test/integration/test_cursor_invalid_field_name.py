#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""Regression tests for CONPY-380"""

import struct
import unittest

import mariadb

from test._fakeserver import (
    MYSQL_TYPE_LONG, MYSQL_TYPE_VAR_STRING, FakeServer, binary_resultset,
    fake_conf, ok, prepare_ok, query_text, scripted_handler, text_resultset,
)

BAD_NAME = b"\xe9"

BAD_QUERY = "SELECT 1 AS bad"
GOOD_QUERY = "SELECT 42 AS answer, 'ok' AS status"
ALIVE_QUERY = "SELECT 'still alive'"

# query -> (columns, rows)
_RESULTS = {
    BAD_QUERY: ([(BAD_NAME, MYSQL_TYPE_LONG)], [(1,)]),
    GOOD_QUERY: ([("answer", MYSQL_TYPE_LONG),
                  ("status", MYSQL_TYPE_VAR_STRING)],
                 [(42, "ok")]),
    ALIVE_QUERY: ([("still alive", MYSQL_TYPE_VAR_STRING)],
                  [("still alive",)]),
}


def _handler():
    """Answer the test queries on both the text and the prepared statement
    path; anything else gets an OK."""
    prepared = {}

    def on_query(payload):
        hit = _RESULTS.get(query_text(payload))
        return ok() if hit is None else text_resultset(*hit)

    def on_prepare(payload):
        hit = _RESULTS.get(query_text(payload))
        if hit is None:
            return ok()
        stmt_id = len(prepared) + 1
        prepared[stmt_id] = hit
        return prepare_ok(stmt_id, columns=hit[0])

    def on_execute(payload):
        stmt_id = struct.unpack_from("<I", payload, 1)[0]
        return binary_resultset(*prepared[stmt_id])

    return scripted_handler(on_query=on_query, on_prepare=on_prepare,
                            on_execute=on_execute)


class TestCursorInvalidFieldName(unittest.TestCase):

    def setUp(self):
        self.server = FakeServer(_handler()).__enter__()
        self.connection = mariadb.connect(**fake_conf(self.server.port))

    def tearDown(self):
        self.connection.close()
        del self.connection
        self.server.__exit__(None, None, None)
        self.assertIsNone(self.server.error)

    def _undecodable_column(self, cursor: mariadb.Cursor) -> None:
        with self.assertRaises(Exception) as ctx:
            cursor.execute(BAD_QUERY)
        # a real error, not "returned a result with an exception set"
        self.assertNotIsInstance(ctx.exception, SystemError)

    def test_fetch_after_failure_reports_no_result_set(self):
        """Catching the error and fetching anyway used to segfault."""
        cursor = self.connection.cursor(named_tuple=True)
        try:
            cursor.execute(BAD_QUERY)
        except Exception:
            pass

        with self.assertRaises(Exception) as ctx:
            cursor.fetchall()
        self.assertIn("result set", str(ctx.exception))
        cursor.close()

    def test_cursor_usable_after_failure(self):
        """The cursor must recover for the next statement."""
        cursor = self.connection.cursor(named_tuple=True)
        self._undecodable_column(cursor)

        cursor.execute(GOOD_QUERY)
        row = cursor.fetchall()[0]
        self.assertEqual(row.answer, 42)
        self.assertEqual(row.status, "ok")
        cursor.close()

    def test_cursor_usable_after_failure_binary(self):
        """Same on the prepared statement path."""
        cursor = self.connection.cursor(named_tuple=True, binary=True)
        self._undecodable_column(cursor)

        cursor.execute(GOOD_QUERY)
        row = cursor.fetchall()[0]
        self.assertEqual(row.answer, 42)
        self.assertEqual(row.status, "ok")
        cursor.close()

    def test_connection_usable_after_failure(self):
        """The pending result set must be drained, not left on the wire."""
        cursor = self.connection.cursor(named_tuple=True)
        self._undecodable_column(cursor)
        cursor.close()

        other = self.connection.cursor()
        other.execute(ALIVE_QUERY)
        self.assertEqual(other.fetchall(), [("still alive",)])
        other.close()


if __name__ == '__main__':
    unittest.main()
