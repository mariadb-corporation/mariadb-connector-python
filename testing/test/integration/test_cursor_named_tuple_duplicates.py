#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""Member names of cursor(named_tuple=True) rows.

The row type is a struct sequence built from the column names, and it can only
carry a given name once. Two columns sharing one - the usual case being a join
selecting an id from each table - used to be accepted with the member declared
twice, where the second shadows the first: repr() printed Row(id=1, id=2) but
row.id only ever reached the last of them.

One rule, shared with the pure-Python implementation which builds its rows
with collections.namedtuple: a column name is kept when namedtuple() accepts
it, i.e. it is a valid identifier, not a keyword, does not start with an
underscore and is not already used by an earlier column. Any other name is
replaced by the column position, "column_<index>", with "_1", "_2", ...
appended should that name itself be taken. Every column stays reachable as an
attribute, no member shadows another, and the statement never fails because
of its column names. cursor.description keeps the names as the server sent
them.
"""

import unittest

from test.base_test import create_connection


class TestCursorNamedTupleDuplicates(unittest.TestCase):

    def setUp(self):
        self.connection = create_connection()

    def tearDown(self):
        self.connection.close()
        del self.connection

    def _row(self, sql, **kwargs):
        cursor = self.connection.cursor(named_tuple=True, **kwargs)
        cursor.execute(sql)
        row = cursor.fetchone()
        description = cursor.description
        cursor.close()
        return row, [d[0] for d in description]

    def test_duplicate_column_name_is_renamed(self):
        row, names = self._row("SELECT 1 AS a, 2 AS a")
        self.assertEqual(row.a, 1)
        self.assertEqual(row.column_1, 2)
        self.assertEqual(tuple(row), (1, 2))
        self.assertEqual(names, ["a", "a"])

    def test_duplicate_column_name_from_join(self):
        row, _ = self._row("SELECT 1 AS id, 'x' AS id")
        self.assertEqual(row.id, 1)
        self.assertEqual(row.column_1, "x")

    def test_more_than_two_duplicates(self):
        row, _ = self._row("SELECT 1 AS a, 2 AS a, 3 AS a")
        self.assertEqual((row.a, row.column_1, row.column_2), (1, 2, 3))

    def test_name_namedtuple_cannot_carry_is_renamed(self):
        for statement, expected in (
                ("SELECT 1 AS `COUNT(*)`, 2 AS `not an id`",
                 ("column_0", "column_1")),
                ("SELECT 1 AS `_foo`, 2 AS `_bar`", ("column_0", "column_1")),
                ("SELECT 1 AS `def`, 2 AS `class`, 3 AS ok",
                 ("column_0", "column_1", "ok")),
                ("SELECT COUNT(*), COUNT(*) + 1", ("column_0", "column_1"))):
            with self.subTest(statement=statement):
                row, _ = self._row(statement)
                for i, name in enumerate(expected):
                    self.assertEqual(getattr(row, name), i + 1)
                self.assertIn("%s=1" % expected[0], repr(row))

    def test_identifiers_are_kept(self):
        row, names = self._row("SELECT 1 AS héllo, 2 AS `日本`, 3 AS count, 4 AS `index`")
        self.assertEqual(names, ["héllo", "日本", "count", "index"])
        self.assertEqual((getattr(row, "héllo"), getattr(row, "日本"),
                          row.count, row.index), (1, 2, 3, 4))

    def test_positional_name_already_taken_by_a_column(self):
        """A column may itself be called column_1; the replacement then gets
        a counter until it is free."""
        row, _ = self._row("SELECT 1 AS column_1, 2 AS column_1")
        self.assertEqual((row.column_1, row.column_1_1), (1, 2))

        row, _ = self._row("SELECT 1 AS a, 2 AS a, 3 AS column_1")
        self.assertEqual((row.a, row.column_1, row.column_2), (1, 2, 3))

        row, _ = self._row("SELECT 1 AS `def`, 2 AS column_0")
        self.assertEqual((row.column_0, row.column_1), (1, 2))

    def test_distinct_column_names_still_work(self):
        row, _ = self._row("SELECT 1 AS a, 2 AS b")
        self.assertEqual(tuple(row), (1, 2))
        self.assertEqual(row.a, 1)
        self.assertEqual(row.b, 2)

    def test_unbuffered_cursor(self):
        row, _ = self._row("SELECT 1 AS a, 2 AS a UNION ALL SELECT 3, 4",
                           buffered=False)
        self.assertEqual((row.a, row.column_1), (1, 2))

    def test_cursor_is_reusable(self):
        cursor = self.connection.cursor(named_tuple=True)
        cursor.execute("SELECT 1 AS a, 2 AS a")
        self.assertEqual(cursor.fetchone().column_1, 2)
        cursor.execute("SELECT 3 AS a, 4 AS b")
        self.assertEqual(cursor.fetchone().b, 4)
        cursor.close()


if __name__ == '__main__':
    unittest.main()
