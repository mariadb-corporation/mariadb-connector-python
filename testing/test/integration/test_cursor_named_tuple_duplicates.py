#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""cursor(named_tuple=True) must reject a result set with duplicate column
names.

The row type is a struct sequence built from the column names, and it can only
carry a given name once. Two columns sharing one - the usual case being a join
selecting an id from each table - used to be accepted with the member declared
twice, where the second shadows the first: repr() printed Row(id=1, id=2) but
row.id only ever reached the last of them.

Every column name is reachable, not just the ones that look like identifiers:
getattr(row, 'COUNT(*)') works. So any duplicate hides a column, whatever the
name looks like, and all of them are refused.

The names are checked while the result metadata is read, so the error comes
from execute(), and the result set it belongs to is dropped.
"""

import unittest

import mariadb

from test.base_test import create_connection


class TestCursorNamedTupleDuplicates(unittest.TestCase):

    def setUp(self):
        self.connection = create_connection()

    def tearDown(self):
        self.connection.close()
        del self.connection

    def test_duplicate_column_name_raises(self):
        cursor = self.connection.cursor(named_tuple=True)
        with self.assertRaises(mariadb.ProgrammingError) as exc:
            cursor.execute("SELECT 1 AS a, 2 AS a")
        cursor.close()
        self.assertIn("Duplicate column name 'a'", str(exc.exception))

    def test_duplicate_column_name_from_join_raises(self):
        cursor = self.connection.cursor(named_tuple=True)
        with self.assertRaises(mariadb.ProgrammingError) as exc:
            cursor.execute("SELECT 1 AS id, 'x' AS id")
        cursor.close()
        self.assertIn("Duplicate column name 'id'", str(exc.exception))

    def test_duplicate_name_that_is_no_identifier_raises(self):
        """getattr(row, 'COUNT(*)') works, so such a duplicate hides a column
        just the same."""
        for statement in ("SELECT COUNT(*), COUNT(*)",
                          "SELECT 1 AS `_foo`, 2 AS `_foo`",
                          "SELECT 1 AS `def`, 2 AS `def`"):
            with self.subTest(statement=statement):
                cursor = self.connection.cursor(named_tuple=True)
                with self.assertRaises(mariadb.ProgrammingError):
                    cursor.execute(statement)
                cursor.close()

    def test_more_than_two_duplicates_raise(self):
        cursor = self.connection.cursor(named_tuple=True)
        with self.assertRaises(mariadb.ProgrammingError):
            cursor.execute("SELECT 1 AS a, 2 AS a, 3 AS a")
        cursor.close()

    def test_distinct_column_names_still_work(self):
        cursor = self.connection.cursor(named_tuple=True)
        cursor.execute("SELECT 1 AS a, 2 AS b")
        row = cursor.fetchone()
        cursor.close()

        self.assertEqual(tuple(row), (1, 2))
        self.assertEqual(row.a, 1)
        self.assertEqual(row.b, 2)

    def test_cursor_has_no_result_set_after_the_error(self):
        """The result set is already stored when the names are checked; it has
        to be dropped, or a fetch walks a row buffer that was never
        allocated."""
        for buffered in (True, False):
            with self.subTest(buffered=buffered):
                cursor = self.connection.cursor(named_tuple=True,
                                                buffered=buffered)
                with self.assertRaises(mariadb.ProgrammingError):
                    cursor.execute("SELECT 1 AS a, 2 AS a")
                self.assertIsNone(cursor.description)
                with self.assertRaises(mariadb.ProgrammingError):
                    cursor.fetchone()
                cursor.close()

    def test_connection_is_usable_after_the_error(self):
        """A pending result set must be drained, or the connection goes out of
        sync."""
        cursor = self.connection.cursor(named_tuple=True, buffered=False)
        with self.assertRaises(mariadb.ProgrammingError):
            cursor.execute("SELECT 1 AS a, 2 AS a UNION ALL SELECT 3, 4")
        cursor.close()

        cursor = self.connection.cursor()
        cursor.execute("SELECT 42")
        self.assertEqual(cursor.fetchone(), (42,))
        cursor.close()

    def test_other_result_formats_are_unaffected(self):
        for kwargs in ({}, {"dictionary": True}):
            with self.subTest(kwargs=kwargs):
                cursor = self.connection.cursor(**kwargs)
                cursor.execute("SELECT 1 AS a, 2 AS a")
                self.assertIsNotNone(cursor.fetchone())
                cursor.close()


if __name__ == '__main__':
    unittest.main()
