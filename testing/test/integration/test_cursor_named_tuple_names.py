#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""Regression tests for CONPY-379.

The row type built for cursor(named_tuple=True) used to point each struct
sequence member name straight at MYSQL_FIELD.name, which is owned by the
result set. CPython copies the PyMemberDef array into the type but not the
strings it points to, so once the result set was released - on the next
execute(), on cursor.close() or on connection.close() - the type kept
dangling pointers.

Attribute access stayed correct because the member descriptor interns its own
copy of the name. repr() did not: struct sequence repr reads
tp_members[i].name directly and strlen()s it, so it printed whatever the
allocator had since put there, typically data from a later query on the same
connection, and segfaulted once the block had been returned to the OS.
"""

import unittest

from test.base_test import create_connection


class TestCursorNamedTupleNames(unittest.TestCase):

    def setUp(self):
        self.connection = create_connection()

    def tearDown(self):
        self.connection.close()
        del self.connection

    def test_repr_after_cursor_close(self):
        """Rows outliving their cursor must still repr their own names."""
        name = "a" * 32
        cursor = self.connection.cursor(named_tuple=True)
        cursor.execute("SELECT 1 AS %s" % name)
        rows = cursor.fetchall()
        cursor.close()

        self.assertIn(name, repr(rows[0]))
        self.assertEqual(rows[0][0], 1)
        self.assertEqual(getattr(rows[0], name), 1)

    def test_no_disclosure_from_later_query(self):
        """The freed field name buffer used to be recycled by a later query,
        which printed that query's data as the column name."""
        name = "a" * 32
        secret = "SECRET_" + "S" * 300

        cursor = self.connection.cursor(named_tuple=True)
        cursor.execute("SELECT 1 AS %s" % name)
        rows = cursor.fetchall()
        cursor.close()

        other = self.connection.cursor()
        other.execute("SELECT '%s'" % secret)
        other.fetchall()
        other.close()

        self.assertNotIn("SECRET_", repr(rows[0]))
        self.assertIn(name, repr(rows[0]))

    def test_repr_after_next_execute(self):
        """The result set is released by the next execute() on the same
        cursor, which is enough to reach the freed names."""
        cursor = self.connection.cursor(named_tuple=True)
        cursor.execute("SELECT 1 AS first_column")
        rows = cursor.fetchall()
        cursor.execute("SELECT 2 AS second_column")
        cursor.fetchall()

        self.assertIn("first_column", repr(rows[0]))
        cursor.close()

    def test_repr_after_connection_close(self):
        """Large field name blocks are released to the OS on close, which
        turned the dangling read into a segfault."""
        connection = create_connection()
        cursor = connection.cursor(named_tuple=True)
        cols = ",".join("1 AS %s%d" % ("z" * 200, i) for i in range(300))
        cursor.execute("SELECT " + cols)
        rows = cursor.fetchall()
        cursor.close()
        connection.close()

        self.assertIn("z" * 200, repr(rows[0]))
        self.assertEqual(len(rows[0]), 300)

    def test_column_named_like_internal_key(self):
        """The copied names are kept in an attribute on the row type. A column
        with that name must keep its own value."""
        cursor = self.connection.cursor(named_tuple=True)
        cursor.execute("SELECT 1 AS _mariadb_field_names, 2 AS other")
        rows = cursor.fetchall()
        cursor.close()

        self.assertEqual(rows[0]._mariadb_field_names, 1)
        self.assertEqual(rows[0].other, 2)
        self.assertIn("_mariadb_field_names", repr(rows[0]))


if __name__ == '__main__':
    unittest.main()
