#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""fetchmany() argument handling.

A negative count means every remaining row, in both implementations. In the
C extension the count used to be cast to an unsigned 64-bit value without
checking the conversion: a value out of range for a C long long left an
OverflowError pending while every row was fetched, and surfaced as a
SystemError.
"""

import unittest

import mariadb
from tests.base_test import create_connection, is_native
from tests.conftest import get_test_config as conf


class TestCursorFetchmany(unittest.TestCase):

    def setUp(self) -> None:
        self.connection = create_connection()
        self.cursor = self.connection.cursor()
        # a plain table rather than the sequence engine: the suite also runs
        # against MySQL
        self.cursor.execute("CREATE TEMPORARY TABLE test_fetchmany (seq INT)")
        self.cursor.executemany("INSERT INTO test_fetchmany VALUES (?)",
                                [(i,) for i in range(1, 11)])
        self.cursor.execute("SELECT seq FROM test_fetchmany ORDER BY seq")

    def tearDown(self) -> None:
        self.cursor.close()
        self.connection.close()
        del self.connection

    def test_negative_count_fetches_every_remaining_row(self) -> None:
        self.cursor.fetchmany(3)
        self.assertEqual([r[0] for r in self.cursor.fetchmany(-1)],
                         list(range(4, 11)))
        self.assertEqual(self.cursor.fetchmany(-1), [])

    def test_count_out_of_range(self) -> None:
        if is_native():
            # Python integers are unbounded: the count is simply larger than
            # the result set
            self.assertEqual(len(self.cursor.fetchmany(2 ** 64)), 10)
            return
        with self.assertRaises(OverflowError):
            self.cursor.fetchmany(2 ** 64)
        # the cursor is still usable, nothing was consumed
        self.assertEqual([r[0] for r in self.cursor.fetchall()],
                         list(range(1, 11)))

    def test_count_larger_than_the_result_set(self) -> None:
        self.assertEqual(len(self.cursor.fetchmany(2 ** 62)), 10)
        self.assertEqual(self.cursor.fetchmany(5), [])

    def test_wrong_type(self) -> None:
        with self.assertRaises(TypeError):
            self.cursor.fetchmany("3")  # type: ignore[arg-type]


class TestAsyncCursorFetchmany(unittest.IsolatedAsyncioTestCase):

    async def test_negative_count_fetches_every_remaining_row(self) -> None:
        for buffered in (True, False):
            with self.subTest(buffered=buffered):
                connection = await mariadb.asyncConnect(**conf())
                cursor = connection.cursor(buffered=buffered)
                await cursor.execute("CREATE TEMPORARY TABLE test_fetchmany (seq INT)")
                await cursor.executemany("INSERT INTO test_fetchmany VALUES (?)",
                                         [(i,) for i in range(1, 11)])
                await cursor.execute("SELECT seq FROM test_fetchmany ORDER BY seq")
                await cursor.fetchmany(3)
                self.assertEqual([r[0] for r in await cursor.fetchmany(-1)],
                                 list(range(4, 11)))
                self.assertEqual(await cursor.fetchmany(-1), [])
                await cursor.close()
                await connection.close()


if __name__ == "__main__":
    unittest.main()
