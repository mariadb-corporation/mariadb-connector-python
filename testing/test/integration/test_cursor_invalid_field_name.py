#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""Regression tests for CONPY-380.

A column name which is not valid UTF-8 makes PyStructSequence_NewType() fail
when the row type for cursor(named_tuple=True) is built. The failure was not
reported, so execute() surfaced it as a bare SystemError while the cursor
still advertised a result set with no row type and no values array. An
application which caught the error and kept using the cursor then segfaulted
on the next fetch, which a hostile server could trigger by answering with a
column name that does not decode.

The result set is now dropped when initialisation fails, so a later fetch
reports that there is none and the cursor stays usable.

SET character_set_results=latin1 makes a stock server encode U+00E9 as the
single byte 0xE9. Note that the connector only rejects a non-utf8mb4
character_set_client, not character_set_results.
"""

import unittest

from test.base_test import create_connection


class TestCursorInvalidFieldName(unittest.TestCase):

    def setUp(self):
        self.connection = create_connection()

    def tearDown(self):
        self.connection.close()
        del self.connection

    def _undecodable_column(self, cursor):
        cursor.execute("SET character_set_results=latin1")
        with self.assertRaises(Exception) as ctx:
            cursor.execute("SELECT 1 AS `é`")
        # a real error, not "returned a result with an exception set"
        self.assertNotIsInstance(ctx.exception, SystemError)
        cursor.execute("SET character_set_results=utf8mb4")

    def test_fetch_after_failure_reports_no_result_set(self):
        """Catching the error and fetching anyway used to segfault."""
        cursor = self.connection.cursor(named_tuple=True)
        cursor.execute("SET character_set_results=latin1")
        try:
            cursor.execute("SELECT 1 AS `é`")
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

        cursor.execute("SELECT 42 AS answer, 'ok' AS status")
        row = cursor.fetchall()[0]
        self.assertEqual(row.answer, 42)
        self.assertEqual(row.status, "ok")
        cursor.close()

    def test_cursor_usable_after_failure_binary(self):
        """Same on the prepared statement path."""
        cursor = self.connection.cursor(named_tuple=True, binary=True)
        self._undecodable_column(cursor)

        cursor.execute("SELECT 42 AS answer")
        self.assertEqual(cursor.fetchall()[0].answer, 42)
        cursor.close()

    def test_connection_usable_after_failure(self):
        """The pending result set must be drained, not left on the wire."""
        cursor = self.connection.cursor(named_tuple=True)
        self._undecodable_column(cursor)
        cursor.close()

        other = self.connection.cursor()
        other.execute("SELECT 'still alive'")
        self.assertEqual(other.fetchall(), [("still alive",)])
        other.close()


if __name__ == '__main__':
    unittest.main()
