#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""
CONPY-380: when a result set cannot be initialised (here a named_tuple cursor
receiving a column name that is not valid UTF-8), the error must surface as a
regular exception, the pending result set must be dropped, and both the cursor
and the connection must stay usable. Catching the error and fetching anyway
used to segfault the C extension.

Both implementations raise UnicodeDecodeError. The C extension raises from
execute() and leaves the cursor without a result set; the pure-Python one
only decodes a column name when it is used, so it raises from the first
fetch (named_tuple, dictionary) or from cursor.description.

Ported from the 1.1 branch; drives both implementations against the
in-process wire fake server.
"""

import asyncio
import struct
import unittest

import mariadb
from tests.base_test import is_native
from tests.unit._fakeserver import (
    Handler, MYSQL_TYPE_LONG, MYSQL_TYPE_VAR_STRING, FakeServer, binary_resultset,
    fake_conf, ok, prepare_ok, query_text, scripted_handler, text_resultset,
)

BAD_NAME = b"\xe9"

BAD_QUERY = "SELECT 1 AS bad"
DUP_QUERY = "SELECT 1 AS a, 2 AS a"
GOOD_QUERY = "SELECT 42 AS answer, 'ok' AS status"
ALIVE_QUERY = "SELECT 'still alive'"

# query -> (columns, rows)
_RESULTS: dict[str, tuple[list[tuple[bytes | str, int]], list[tuple[object, ...]]]] = {
    BAD_QUERY: ([(BAD_NAME, MYSQL_TYPE_LONG)], [(1,)]),
    DUP_QUERY: ([("a", MYSQL_TYPE_LONG), ("a", MYSQL_TYPE_LONG)], [(1, 2)]),
    GOOD_QUERY: ([("answer", MYSQL_TYPE_LONG),
                  ("status", MYSQL_TYPE_VAR_STRING)],
                 [(42, "ok")]),
    ALIVE_QUERY: ([("still alive", MYSQL_TYPE_VAR_STRING)],
                  [("still alive",)]),
}


def _handler() -> Handler:
    """Answer the test queries on both the text and the prepared statement
    path; anything else gets an OK."""
    prepared: dict[int, tuple[list[tuple[bytes | str, int]], list[tuple[object, ...]]]] = {}

    def on_query(payload: bytes) -> bytes:
        hit = _RESULTS.get(query_text(payload))
        return ok() if hit is None else text_resultset(*hit)

    def on_prepare(payload: bytes) -> bytes:
        hit = _RESULTS.get(query_text(payload))
        if hit is None:
            return ok()
        stmt_id = len(prepared) + 1
        prepared[stmt_id] = hit
        return prepare_ok(stmt_id, columns=hit[0])

    def on_execute(payload: bytes) -> bytes:
        stmt_id = struct.unpack_from("<I", payload, 1)[0]
        return binary_resultset(*prepared[stmt_id])

    return scripted_handler(on_query=on_query, on_prepare=on_prepare,
                            on_execute=on_execute)


class TestCursorInvalidFieldName(unittest.TestCase):

    def setUp(self) -> None:
        self.server = FakeServer(_handler()).__enter__()
        self.connection = mariadb.connect(**fake_conf(self.server.port))

    def tearDown(self) -> None:
        self.connection.close()
        del self.connection
        self.server.__exit__(None, None, None)
        self.assertIsNone(self.server.error)

    def _undecodable_column(self, cursor: mariadb.Cursor) -> None:
        """Run BAD_QUERY on a cursor keyed by column name, whichever end raises."""
        with self.assertRaises(UnicodeDecodeError):
            cursor.execute(BAD_QUERY)
            cursor.fetchall()

    def test_fetch_after_failure_reports_no_result_set(self) -> None:
        """Catching the error and fetching anyway used to segfault."""
        if is_native():
            self.skipTest("C extension: the result set is dropped by execute()")
        cursor = self.connection.cursor(named_tuple=True)
        try:
            cursor.execute(BAD_QUERY)
        except Exception:
            pass

        with self.assertRaises(mariadb.ProgrammingError) as ctx:
            cursor.fetchall()
        self.assertIn("result set", str(ctx.exception))
        cursor.close()

    def test_cursor_usable_after_failure(self) -> None:
        """The cursor must recover for the next statement."""
        cursor = self.connection.cursor(named_tuple=True)
        self._undecodable_column(cursor)

        cursor.execute(GOOD_QUERY)
        row = cursor.fetchall()[0]
        self.assertEqual(row.answer, 42)
        self.assertEqual(row.status, "ok")
        cursor.close()

    def test_cursor_usable_after_failure_binary(self) -> None:
        """Same on the prepared statement path."""
        cursor = self.connection.cursor(named_tuple=True, binary=True)
        self._undecodable_column(cursor)

        cursor.execute(GOOD_QUERY)
        row = cursor.fetchall()[0]
        self.assertEqual(row.answer, 42)
        self.assertEqual(row.status, "ok")
        cursor.close()

    def test_connection_usable_after_failure(self) -> None:
        """The pending result set must be drained, not left on the wire."""
        cursor = self.connection.cursor(named_tuple=True)
        self._undecodable_column(cursor)
        cursor.close()

        other = self.connection.cursor()
        other.execute(ALIVE_QUERY)
        self.assertEqual(other.fetchall(), [("still alive",)])
        other.close()

    def test_connection_usable_after_failure_streaming(self) -> None:
        """Same with an unbuffered cursor: the rows still on the wire must be
        drained before the connection is reused."""
        cursor = self.connection.cursor(named_tuple=True, buffered=False)
        self._undecodable_column(cursor)
        cursor.close()

        other = self.connection.cursor(dictionary=True)
        other.execute(ALIVE_QUERY)
        self.assertEqual(other.fetchall(), [{"still alive": "still alive"}])
        other.close()

    def test_dictionary_cursor_fails_at_fetch(self) -> None:
        """Dictionary rows are keyed by name when they are fetched: both
        implementations accept the execute and fail the fetch."""
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute(BAD_QUERY)
        with self.assertRaises(UnicodeDecodeError):
            cursor.fetchall()
        cursor.execute(GOOD_QUERY)
        self.assertEqual(cursor.fetchall(), [{"answer": 42, "status": "ok"}])
        cursor.close()

    def test_duplicate_column_name(self) -> None:
        """The other reason a named tuple cannot be built, whichever end raises."""
        cursor = self.connection.cursor(named_tuple=True)
        with self.assertRaises(mariadb.ProgrammingError) as ctx:
            cursor.execute(DUP_QUERY)
            cursor.fetchall()
        self.assertIn("Duplicate column name 'a'", str(ctx.exception))

        cursor.execute(GOOD_QUERY)
        self.assertEqual(cursor.fetchall()[0].answer, 42)
        cursor.close()


class TestAsyncCursorInvalidFieldName(unittest.TestCase):
    """The async cursor takes the same paths."""

    def setUp(self) -> None:
        self.server = FakeServer(_handler()).__enter__()

    def tearDown(self) -> None:
        self.server.__exit__(None, None, None)
        self.assertIsNone(self.server.error)

    def test_cursor_and_connection_usable_after_failure(self) -> None:
        async def scenario() -> None:
            connection = await mariadb.AsyncConnection.connect(**fake_conf(self.server.port))
            for buffered in (True, False):
                cursor = connection.cursor(named_tuple=True, buffered=buffered)
                with self.assertRaises(UnicodeDecodeError):
                    await cursor.execute(BAD_QUERY)
                    await cursor.fetchall()

                await cursor.execute(GOOD_QUERY)
                row = (await cursor.fetchall())[0]
                self.assertEqual(row.answer, 42)
                await cursor.close()

            other = connection.cursor()
            await other.execute(ALIVE_QUERY)
            self.assertEqual(await other.fetchall(), [("still alive",)])
            await other.close()
            await connection.close()

        asyncio.run(scenario())


if __name__ == '__main__':
    unittest.main()
