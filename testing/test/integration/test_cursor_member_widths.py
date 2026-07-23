#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""Regression tests for the C cursor PyMemberDef type/width mismatches.

Several MrdbCursor members declared a PyMemberDef type whose width did not
match the backing struct field, so CPython's generated getter/setter touched
the wrong number of bytes:

    _reprepare  T_UINT  over  uint8_t                 -> out-of-bounds write
    arraysize   T_LONG  over  uint32_t row_array_size -> over-write / bad read
    insert_id   T_UINT  over  uint64_t lastrow_id     -> truncated read
    _command    T_BYTE  over  a 4-byte enum           -> short read

The _reprepare over-write is the severe one: where ``reprepare`` is the last
struct member (e.g. once the trailing weakreflist is removed) the 4-byte store
lands on the Python subclass ``__dict__`` pointer and segfaults on every
parameterized execute.
"""

import unittest

from test.base_test import create_connection


class TestCursorMemberWidths(unittest.TestCase):

    def setUp(self):
        self.connection = create_connection()

    def tearDown(self):
        self.connection.close()
        del self.connection

    def test_parameterized_reexecute_stability(self):
        """_reprepare is written on every parameterized execute; a mismatched
        member width corrupted the cursor object and crashed here."""
        cursor = self.connection.cursor()
        for i in range(25):
            cursor.execute("SELECT ? AS v", (i,))
            self.assertEqual(cursor.fetchone(), (i,))
        cursor.close()

    def test_arraysize_roundtrip(self):
        """arraysize was T_LONG (8 bytes) over a uint32_t field. Guard that the
        member round-trips and that fetchmany honours it. (The deterministic
        width-mismatch catch is test_lastrowid_above_32bit; arraysize's overrun
        lands in the adjacent ``paraminfo`` pointer, which Python cannot observe
        without crashing, so this stays a behavioural smoke test.)"""
        cursor = self.connection.cursor()
        cursor.arraysize = 3
        self.assertEqual(cursor.arraysize, 3)
        cursor.execute("SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4")
        self.assertEqual(len(cursor.fetchmany()), 3)  # honours arraysize=3
        cursor.close()

    def test_lastrowid_above_32bit(self):
        """insert_id was T_UINT (4 bytes) over a uint64_t field, truncating
        auto-increment ids above 2**32."""
        big = 5000000000  # > 2**32 (4294967296)
        cursor = self.connection.cursor()
        cursor.execute("DROP TABLE IF EXISTS conpy_member_width")
        cursor.execute(
            "CREATE TABLE conpy_member_width "
            "(id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, x INT)")
        try:
            cursor.execute(
                "ALTER TABLE conpy_member_width AUTO_INCREMENT = %d" % big)
            cursor.execute("INSERT INTO conpy_member_width (x) VALUES (1)")
            self.assertEqual(cursor.lastrowid, big)
        finally:
            cursor.execute("DROP TABLE IF EXISTS conpy_member_width")
        cursor.close()


if __name__ == "__main__":
    unittest.main()
