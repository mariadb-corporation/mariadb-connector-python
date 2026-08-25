#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""
CONPY-382: values that cannot be serialized must raise, not crash the process.

Two families of parameter used to take down the interpreter with SIGSEGV in the
C extension rather than raising:

  1. a str that does not encode to UTF-8 -- one holding an unpaired surrogate,
     as produced by json.loads('"\\ud800"') or a surrogateescape decode. The
     conversion returns NULL and sets UnicodeEncodeError, and that NULL was
     handed straight to libmariadb as a buffer to read from.
  2. an empty array('f') in an executemany() batch. The bind structures are
     reused between rows, so the empty row kept the previous row's
     buffer_length against a NULL buffer.

What every test here asserts, beyond "an exception was raised", is that the
CONNECTION IS STILL USABLE afterwards. That is the part that distinguishes a
clean refusal from the two bad outcomes: a crash, or a value rejected halfway
through serialization, which desynchronizes the connection and makes the *next*
statement fail instead.

The exact exception differs by implementation and is intentionally not pinned:
the C extension surfaces the UnicodeEncodeError itself, while the pure-Python
client wraps it in a mariadb.Error. Both are acceptable; neither may crash.
"""

import array
import json
import unittest

import mariadb
from ..base_test import create_connection, is_mysql

# str values that have no UTF-8 encoding, from the two sources named in the
# ticket plus the bare literal.
BAD_STRINGS = (
    '\ud800',
    json.loads('"\\ud800"'),
    b'\xff'.decode('utf-8', 'surrogateescape'),
)

_RAISES = (UnicodeEncodeError, mariadb.Error)


class InvalidParamBindingTest(unittest.TestCase):

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
        try:
            self.connection.close()
        except mariadb.Error:
            pass

    def assert_connection_usable(self):
        """The connection must still work: no desync, no half-sent statement."""
        cursor = self.connection.cursor()
        cursor.execute("SELECT 1")
        self.assertEqual((1,), cursor.fetchone())
        cursor.close()

    # --- 1. str with no UTF-8 encoding ---------------------------------------

    def test_executemany_rejects_unencodable_string(self):
        for bad in BAD_STRINGS:
            with self.subTest(bad=ascii(bad)):
                with self.assertRaises(_RAISES):
                    self.cursor.executemany("INSERT INTO conpy382 VALUES (?)", [(bad,)])
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

    def test_database_setter_rejects_unencodable_string(self):
        with self.assertRaises(_RAISES):
            self.connection.database = '\ud800'
        self.assert_connection_usable()

    def test_tpc_xid_rejects_unencodable_string(self):
        with self.assertRaises(_RAISES):
            self.connection.tpc_begin(self.connection.xid(0, '\ud800', 'branch'))
        self.assert_connection_usable()

    def test_escape_string_handles_unencodable_string(self):
        # The C extension raises: it has to encode the string to hand it to
        # mysql_real_escape_string, so NULL there used to run the escaping over a
        # NULL pointer. The pure-Python client escapes with str.replace and never
        # encodes, so it returns the string and the error surfaces when the
        # statement is sent -- validating up front would cost more than the
        # escaping itself and buy only an earlier message. Either is fine; what
        # must hold is that neither crashes nor breaks the connection.
        if not hasattr(self.connection, 'escape_string'):
            self.skipTest("escape_string not available in this implementation")
        try:
            self.assertIsInstance(self.connection.escape_string('\ud800'), str)
        except _RAISES:
            pass
        self.assert_connection_usable()

    def test_escape_string_still_escapes_valid_input(self):
        if not hasattr(self.connection, 'escape_string'):
            self.skipTest("escape_string not available in this implementation")
        self.assertEqual("it\\'s", self.connection.escape_string("it's"))

    # --- regression guard: encodable strings must be unaffected --------------

    def test_valid_strings_still_bind(self):
        rows = [('ascii',), ('accentué',), ('emoji 😎',), ('',)]
        self.cursor.executemany("INSERT INTO conpy382 VALUES (?)", rows)
        self.cursor.execute("SELECT a FROM conpy382 ORDER BY a")
        self.assertEqual(sorted(r[0] for r in rows),
                         [r[0] for r in self.cursor.fetchall()])


class EmptyVectorBindingTest(unittest.TestCase):
    """An empty array('f') must not corrupt an executemany() batch."""

    def setUp(self):
        if is_mysql():
            self.skipTest("VECTOR columns are MariaDB-specific here")
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
        try:
            self.connection.close()
        except mariadb.Error:
            pass

    def assert_connection_usable(self):
        cursor = self.connection.cursor()
        cursor.execute("SELECT 1")
        self.assertEqual((1,), cursor.fetchone())
        cursor.close()

    def _executemany(self, rows):
        """Run the batch, tolerating the server's refusal of the empty vector.

        Both implementations send it as a zero-length value, which the server
        rejects; only the exception class differs. The crash and the
        desynchronized connection are what is asserted against here.
        """
        try:
            self.cursor.executemany("INSERT INTO conpy382v VALUES (?,?)", rows)
        except mariadb.Error:
            pass
        self.assert_connection_usable()

    def test_empty_vector_after_non_empty(self):
        # The original crash: row 2 inherits row 1's buffer_length.
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

    # --- regression guard: real vectors must round-trip ----------------------

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
