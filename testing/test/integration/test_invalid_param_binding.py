#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""Regression tests for CONPY-382: unserializable parameters segfaulted.

Two families of value crashed the interpreter instead of raising:

    a str with no UTF-8 encoding (an unpaired surrogate, as produced by
    json.loads('"\\ud800"') or a surrogateescape decode) -- the conversion
    returns NULL and sets UnicodeEncodeError, and that NULL was passed on as a
    buffer to read from, a statement to send, or a string to escape

    an empty array('f') in an executemany() batch -- the bind structures are
    reused between rows, so the empty row kept the previous row's
    buffer_length against a NULL buffer

Every test below also asserts the CONNECTION IS STILL USABLE afterwards, which
is what separates a clean refusal from a value rejected halfway through
serialization, where the next statement fails instead of this one.
"""

import array
import json
import unittest

import mariadb
from test.base_test import create_connection

BAD_STRINGS = (
    '\ud800',
    json.loads('"\\ud800"'),
    b'\xff'.decode('utf-8', 'surrogateescape'),
)

_RAISES = (UnicodeEncodeError, mariadb.Error)


class TestInvalidParamBinding(unittest.TestCase):

    def setUp(self):
        self.connection = create_connection()
        self.cursor = self.connection.cursor()
        self.cursor.execute("DROP TABLE IF EXISTS conpy382")
        self.cursor.execute("CREATE TABLE conpy382 (a TEXT)")

    def tearDown(self):
        try:
            self.cursor.execute("DROP TABLE IF EXISTS conpy382")
            self.cursor.close()
        except mariadb.Error:
            pass
        self.connection.close()
        del self.connection

    def assert_connection_usable(self):
        cursor = self.connection.cursor()
        cursor.execute("SELECT 1")
        self.assertEqual((1,), cursor.fetchone())
        cursor.close()

    def test_executemany_rejects_unencodable_string(self):
        for bad in BAD_STRINGS:
            with self.subTest(bad=ascii(bad)):
                with self.assertRaises(_RAISES):
                    self.cursor.executemany("INSERT INTO conpy382 VALUES (?)",
                                            [(bad,)])
                self.assert_connection_usable()

    def test_execute_rejects_unencodable_string(self):
        for bad in BAD_STRINGS:
            with self.subTest(bad=ascii(bad)):
                with self.assertRaises(_RAISES):
                    self.cursor.execute("INSERT INTO conpy382 VALUES (?)", (bad,))
                self.assert_connection_usable()

    def test_executemany_rejects_unencodable_string_in_later_row(self):
        # The unencodable row is never written. How much of the rest survives
        # depends on the protocol: with MariaDB's bulk protocol the batch is one
        # packet and nothing lands, while a server without it (MySQL) falls back
        # to a row-by-row loop and keeps the rows written before the failure.
        with self.assertRaises(_RAISES):
            self.cursor.executemany("INSERT INTO conpy382 VALUES (?)",
                                    [('valid',), ('\ud800',)])
        self.assert_connection_usable()
        self.cursor.execute("SELECT COUNT(*) FROM conpy382")
        self.assertLessEqual(self.cursor.fetchone()[0], 1)

    def test_rejects_unencodable_str_representation(self):
        # An object whose __str__ returns an unpaired surrogate: this one is
        # caught while the parameter is being bound, not before.
        class BadStr:
            def __str__(self):
                return '\ud800'

        with self.assertRaises(_RAISES):
            self.cursor.executemany("INSERT INTO conpy382 VALUES (?)", [(BadStr(),)])
        self.assert_connection_usable()

    def test_unencodable_statement_is_rejected(self):
        with self.assertRaises(_RAISES):
            self.cursor.execute("SELECT '\ud800'")
        self.assert_connection_usable()

    def test_database_setter_rejects_unencodable_string(self):
        with self.assertRaises(_RAISES):
            self.connection.database = '\ud800'
        self.assert_connection_usable()

    def test_tpc_xid_rejects_unencodable_string(self):
        with self.assertRaises(_RAISES):
            self.connection.tpc_begin(self.connection.xid(0, '\ud800', 'branch'))
        self.assert_connection_usable()

    def test_escape_string_rejects_unencodable_string(self):
        with self.assertRaises(_RAISES):
            self.connection.escape_string('\ud800')
        self.assert_connection_usable()

    def test_valid_strings_still_bind(self):
        rows = [('ascii',), ('accentué',), ('emoji 😎',), ('',)]
        self.cursor.executemany("INSERT INTO conpy382 VALUES (?)", rows)
        self.cursor.execute("SELECT a FROM conpy382 ORDER BY a")
        self.assertEqual(sorted(r[0] for r in rows),
                         [r[0] for r in self.cursor.fetchall()])

    def test_escape_string_still_escapes_valid_input(self):
        self.assertEqual("it\\'s", self.connection.escape_string("it's"))


class TestEmptyVectorBinding(unittest.TestCase):
    """An empty array('f') must not corrupt an executemany() batch."""

    def setUp(self):
        self.connection = create_connection()
        if self.connection.server_version < 110702:
            self.connection.close()
            self.skipTest("Requires server version >= 11.7.2 for VECTOR")
        self.cursor = self.connection.cursor()
        self.cursor.execute("DROP TABLE IF EXISTS conpy382v")
        self.cursor.execute("CREATE TABLE conpy382v (id INT, v VECTOR(2))")

    def tearDown(self):
        try:
            self.cursor.execute("DROP TABLE IF EXISTS conpy382v")
            self.cursor.close()
        except mariadb.Error:
            pass
        self.connection.close()
        del self.connection

    def assert_connection_usable(self):
        cursor = self.connection.cursor()
        cursor.execute("SELECT 1")
        self.assertEqual((1,), cursor.fetchone())
        cursor.close()

    def _executemany(self, rows):
        # The server rejects the zero-length value; only the crash and the
        # desynchronized connection are what these tests guard against.
        try:
            self.cursor.executemany("INSERT INTO conpy382v VALUES (?,?)", rows)
        except mariadb.Error:
            pass
        self.assert_connection_usable()

    def test_empty_vector_after_non_empty(self):
        self._executemany([(1, array.array('f', [1.0, 2.0])),
                           (2, array.array('f', []))])

    def test_empty_vector_before_non_empty(self):
        self._executemany([(1, array.array('f', [])),
                           (2, array.array('f', [1.0, 2.0]))])

    def test_empty_vector_between_non_empty(self):
        self._executemany([(1, array.array('f', [1.0, 2.0])),
                           (2, array.array('f', [])),
                           (3, array.array('f', [3.0, 4.0]))])

    def test_empty_vector_alone(self):
        self._executemany([(1, array.array('f', []))])

    def test_valid_vectors_still_bind(self):
        vectors = [array.array('f', [1.0, 2.0]), array.array('f', [3.0, 4.0])]
        self.cursor.executemany("INSERT INTO conpy382v VALUES (?,?)",
                                [(1, vectors[0]), (2, vectors[1])])
        self.cursor.execute("SELECT id, v FROM conpy382v ORDER BY id")
        rows = self.cursor.fetchall()
        self.assertEqual(2, len(rows))
        for (_, stored), expected in zip(rows, vectors):
            self.assertEqual(expected.tobytes(), bytes(stored))


if __name__ == '__main__':
    unittest.main()
