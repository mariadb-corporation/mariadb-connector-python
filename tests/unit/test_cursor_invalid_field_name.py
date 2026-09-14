#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""A column name that is not valid UTF-8 on a named_tuple cursor (CONPY-380).

Building the row type used to fail on such a name in the C extension and,
when the error was caught, a fetch walked a result set whose row buffer was
never allocated and segfaulted. The name is now treated like any other name a
named tuple cannot carry, in both implementations: the member is called after
its position, 'column_<index>', and the statement succeeds.

Drives both implementations against the in-process wire fake server.
"""

import asyncio
import struct
import unittest

import mariadb
from tests.unit._fakeserver import (
    Handler, MYSQL_TYPE_LONG, MYSQL_TYPE_VAR_STRING, FakeServer,
    binary_resultset, fake_conf, ok, prepare_ok, query_text, scripted_handler,
    text_resultset,
)

BAD_NAME = b"\xe9"

BAD_QUERY = "SELECT 1 AS bad"
GOOD_QUERY = "SELECT 42 AS answer, 'ok' AS status"
ALIVE_QUERY = "SELECT 'still alive'"

# query -> (columns, rows)
_RESULTS: dict[str, tuple[list[tuple[bytes | str, int]], list[tuple[object, ...]]]] = {
    BAD_QUERY: ([(BAD_NAME, MYSQL_TYPE_LONG), ("fine", MYSQL_TYPE_LONG)],
                [(1, 2)]),
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

    def test_undecodable_name_is_renamed(self) -> None:
        for binary in (False, True):
            with self.subTest(binary=binary):
                cursor = self.connection.cursor(named_tuple=True, binary=binary)
                cursor.execute(BAD_QUERY)
                row = cursor.fetchone()
                assert row is not None
                self.assertEqual((row.column_0, row.fine), (1, 2))
                self.assertIn("column_0=1", repr(row))
                cursor.close()

    def test_cursor_and_connection_stay_usable(self) -> None:
        cursor = self.connection.cursor(named_tuple=True)
        cursor.execute(BAD_QUERY)
        cursor.fetchall()
        cursor.execute(GOOD_QUERY)
        row = cursor.fetchall()[0]
        self.assertEqual((row.answer, row.status), (42, "ok"))
        cursor.close()

        other = self.connection.cursor()
        other.execute(ALIVE_QUERY)
        self.assertEqual(other.fetchall(), [("still alive",)])
        other.close()


class TestAsyncCursorInvalidFieldName(unittest.TestCase):
    """The async cursor takes the same paths."""

    def setUp(self) -> None:
        self.server = FakeServer(_handler()).__enter__()

    def tearDown(self) -> None:
        self.server.__exit__(None, None, None)
        self.assertIsNone(self.server.error)

    def test_undecodable_name_is_renamed(self) -> None:
        async def scenario() -> None:
            connection = await mariadb.AsyncConnection.connect(**fake_conf(self.server.port))
            for buffered in (True, False):
                cursor = connection.cursor(named_tuple=True, buffered=buffered)
                await cursor.execute(BAD_QUERY)
                row = (await cursor.fetchall())[0]
                self.assertEqual((row.column_0, row.fine), (1, 2))
                await cursor.close()
            await connection.close()

        asyncio.run(scenario())


if __name__ == '__main__':
    unittest.main()
