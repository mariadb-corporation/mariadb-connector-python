#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""Regression test for CONPY-381.

Mrdb_GetFieldInfo() creates a struct sequence type per result set, but
nothing ever released it, so every execute() on a cursor(named_tuple=True)
leaked a heap type together with its dict and member descriptors. On a
long-lived pooled connection that accumulated for the life of the process.

The type is now released with the result set. Rows built from it hold their
own reference, so a row that outlives its cursor keeps its type - and the
field names attached to it by CONPY-379 - alive.
"""

import gc
import unittest

from test.base_test import create_connection


def live_row_types():
    gc.collect()
    return sum(1 for o in gc.get_objects()
               if isinstance(o, type) and getattr(o, "__name__", "") == "Row")


class TestCursorNamedTupleLeak(unittest.TestCase):

    def setUp(self):
        self.connection = create_connection()

    def tearDown(self):
        self.connection.close()
        del self.connection

    def test_row_type_released_on_reexecute(self):
        """One row type per cursor, not one per execute."""
        cursor = self.connection.cursor(named_tuple=True)
        cursor.execute("SELECT 1 AS a, 2 AS b")
        cursor.fetchall()
        before = live_row_types()

        for _ in range(300):
            cursor.execute("SELECT 1 AS a, 2 AS b")
            cursor.fetchall()

        self.assertEqual(live_row_types(), before)
        cursor.close()

    def test_row_type_released_with_cursor(self):
        """Closing a cursor releases its row type."""
        base = live_row_types()
        for _ in range(50):
            cursor = self.connection.cursor(named_tuple=True)
            cursor.execute("SELECT 1 AS a, 2 AS b")
            cursor.fetchall()
            cursor.close()
            del cursor

        self.assertLessEqual(live_row_types(), base + 1)

    def test_row_type_released_with_connection(self):
        """A cursor closed together with its connection must not pin its row
        type either."""
        base = live_row_types()
        for _ in range(50):
            connection = create_connection()
            cursor = connection.cursor(named_tuple=True)
            cursor.execute("SELECT 1 AS a, 2 AS b")
            cursor.fetchall()
            connection.close()
            del cursor, connection

        self.assertLessEqual(live_row_types(), base + 1)

    def test_surviving_row_keeps_its_type(self):
        """Releasing the type must not break rows that outlive the cursor."""
        cursor = self.connection.cursor(named_tuple=True)
        cursor.execute("SELECT 1 AS kept_column")
        rows = cursor.fetchall()

        for _ in range(50):
            cursor.execute("SELECT 2 AS other_column")
            cursor.fetchall()
        cursor.close()
        gc.collect()

        self.assertIn("kept_column", repr(rows[0]))
        self.assertEqual(rows[0].kept_column, 1)


if __name__ == '__main__':
    unittest.main()
