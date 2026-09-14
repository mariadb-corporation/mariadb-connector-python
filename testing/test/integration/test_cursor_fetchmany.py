#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""fetchmany() argument handling in the C row fetcher.

The row count used to be cast to an unsigned 64-bit value without checking
the conversion: a value out of range for a C long long set an OverflowError
that was left pending while every row was fetched, and surfaced as a
SystemError. A negative count meant "all remaining rows" only through the
unsigned wrap-around; it is now an explicit rule.
"""

import unittest

import mariadb

from test.base_test import create_connection


class TestCursorFetchmany(unittest.TestCase):

    def setUp(self):
        self.connection = create_connection()
        self.cursor = self.connection.cursor()
        self.cursor.execute("SELECT seq FROM seq_1_to_10")

    def tearDown(self):
        self.cursor.close()
        self.connection.close()
        del self.connection

    def test_negative_count_fetches_every_remaining_row(self):
        self.cursor.fetchmany(3)
        self.assertEqual([r[0] for r in self.cursor.fetchmany(-1)],
                         list(range(4, 11)))
        self.assertEqual(self.cursor.fetchmany(-1), [])

    def test_count_out_of_range_raises_overflow_error(self):
        with self.assertRaises(OverflowError):
            self.cursor.fetchmany(2 ** 64)
        # the cursor is still usable, nothing was consumed
        self.assertEqual([r[0] for r in self.cursor.fetchall()],
                         list(range(1, 11)))

    def test_count_larger_than_the_result_set(self):
        self.assertEqual(len(self.cursor.fetchmany(2 ** 62)), 10)
        self.assertEqual(self.cursor.fetchmany(5), [])

    def test_wrong_type(self):
        with self.assertRaises(TypeError):
            self.cursor.fetchmany("3")


if __name__ == "__main__":
    unittest.main()
