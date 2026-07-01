#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""
Integration tests for the 'binary' protocol option at connection and cursor levels.

Tests verify:
1. Connection-level binary=False (default) uses text protocol
2. Connection-level binary=True uses binary protocol
3. Cursor-level binary= overrides connection default
4. Dict parameters always force text protocol, even when binary=True
"""

import unittest
import datetime
import decimal
import mariadb
from ..base_test import create_connection, is_native


class TestBinaryOptionDefault(unittest.TestCase):
    """Test default behavior: binary=False at connection level"""

    def test_default_uses_text(self):
        """Default connection uses text protocol for parameterized queries"""
        conn = create_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT ? as val", (42,))
        row = cursor.fetchone()
        self.assertEqual(row[0], 42)
        cursor.close()
        conn.close()

    def test_default_no_params_text(self):
        """Default connection uses text protocol for non-parameterized queries"""
        conn = create_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 as val")
        row = cursor.fetchone()
        self.assertEqual(row[0], 1)
        cursor.close()
        conn.close()


class TestBinaryOptionConnection(unittest.TestCase):
    """Test connection-level binary=True"""

    def test_connection_binary_true(self):
        """Connection with binary=True uses binary protocol for params"""
        conn = create_connection({"binary": True})
        cursor = conn.cursor()
        cursor.execute("SELECT ? as val", (42,))
        row = cursor.fetchone()
        self.assertEqual(row[0], 42)
        cursor.close()
        conn.close()

    def test_connection_binary_true_string(self):
        """Connection with binary=True handles string params"""
        conn = create_connection({"binary": True})
        cursor = conn.cursor()
        cursor.execute("SELECT ? as val", ("hello",))
        row = cursor.fetchone()
        self.assertEqual(row[0], "hello")
        cursor.close()
        conn.close()

    def test_connection_binary_true_multiple_types(self):
        """Connection with binary=True handles multiple param types"""
        conn = create_connection({"binary": True})
        cursor = conn.cursor()
        cursor.execute(
            "SELECT ? as i, ? as s, ? as d",
            (42, "hello", decimal.Decimal("3.14"))
        )
        row = cursor.fetchone()
        self.assertEqual(row[0], 42)
        self.assertEqual(row[1], "hello")
        self.assertEqual(row[2], decimal.Decimal("3.14"))
        cursor.close()
        conn.close()

    def test_connection_binary_true_no_params(self):
        """Connection with binary=True still uses text for no-param queries"""
        conn = create_connection({"binary": True})
        cursor = conn.cursor()
        cursor.execute("SELECT 1 as val")
        row = cursor.fetchone()
        self.assertEqual(row[0], 1)
        cursor.close()
        conn.close()

    def test_connection_binary_false_explicit(self):
        """Connection with explicit binary=False uses text protocol"""
        conn = create_connection({"binary": False})
        cursor = conn.cursor()
        cursor.execute("SELECT ? as val", (42,))
        row = cursor.fetchone()
        self.assertEqual(row[0], 42)
        cursor.close()
        conn.close()


class TestBinaryOptionCursor(unittest.TestCase):
    """Test cursor-level binary= override"""

    def test_cursor_binary_true_overrides_connection_false(self):
        """Cursor binary=True overrides connection binary=False"""
        conn = create_connection()  # binary=False default
        cursor = conn.cursor(binary=True)
        cursor.execute("SELECT ? as val", (42,))
        row = cursor.fetchone()
        self.assertEqual(row[0], 42)
        cursor.close()
        conn.close()

    def test_cursor_binary_false_overrides_connection_true(self):
        """Cursor binary=False overrides connection binary=True"""
        conn = create_connection({"binary": True})
        cursor = conn.cursor(binary=False)
        cursor.execute("SELECT ? as val", (42,))
        row = cursor.fetchone()
        self.assertEqual(row[0], 42)
        cursor.close()
        conn.close()

    def test_cursor_inherits_connection_binary(self):
        """Cursor without binary= inherits connection's binary setting"""
        conn = create_connection({"binary": True})
        cursor = conn.cursor()
        # Should use binary protocol (inherited from connection)
        cursor.execute("SELECT ? as val", (42,))
        row = cursor.fetchone()
        self.assertEqual(row[0], 42)
        cursor.close()
        conn.close()

    def test_multiple_cursors_different_binary(self):
        """Multiple cursors on same connection can have different binary settings"""
        conn = create_connection()
        cursor_text = conn.cursor(binary=False)
        cursor_bin = conn.cursor(binary=True)

        cursor_text.execute("SELECT ? as val", (1,))
        row1 = cursor_text.fetchone()
        cursor_text.close()

        cursor_bin.execute("SELECT ? as val", (2,))
        row2 = cursor_bin.fetchone()
        cursor_bin.close()

        self.assertEqual(row1[0], 1)
        self.assertEqual(row2[0], 2)
        conn.close()


class TestBinaryOptionDictParams(unittest.TestCase):
    """Test that dict parameters always force text protocol"""

    def test_dict_params_with_connection_binary_true(self):
        """Dict params force text even when connection binary=True"""
        conn = create_connection({"binary": True})
        cursor = conn.cursor()
        cursor.execute("SELECT %(val)s as val", {"val": 42})
        row = cursor.fetchone()
        self.assertEqual(row[0], 42)
        cursor.close()
        conn.close()

    def test_dict_params_with_cursor_binary_true(self):
        """Dict params force text even when cursor binary=True"""
        conn = create_connection()
        cursor = conn.cursor(binary=True)
        cursor.execute("SELECT %(val)s as val", {"val": 42})
        row = cursor.fetchone()
        self.assertEqual(row[0], 42)
        cursor.close()
        conn.close()

    def test_dict_params_with_both_binary_true(self):
        """Dict params force text even when both connection and cursor binary=True"""
        conn = create_connection({"binary": True})
        cursor = conn.cursor(binary=True)
        cursor.execute("SELECT %(val)s as val", {"val": "hello"})
        row = cursor.fetchone()
        self.assertEqual(row[0], "hello")
        cursor.close()
        conn.close()

    def test_dict_params_pyformat_style(self):
        """Dict params with %(name)s style force text"""
        conn = create_connection({"binary": True})
        cursor = conn.cursor(binary=True)
        cursor.execute("SELECT %(val)s as val", {"val": 42})
        row = cursor.fetchone()
        self.assertEqual(row[0], 42)
        cursor.close()
        conn.close()


class TestBinaryOptionDataTypes(unittest.TestCase):
    """Test various data types work correctly with both protocols"""

    def _test_roundtrip(self, binary, params, expected):
        """Helper: execute with params and verify result"""
        conn = create_connection({"binary": binary})
        cursor = conn.cursor()
        placeholders = ", ".join(["?"] * len(params))
        cursor.execute(f"SELECT {placeholders}", params)
        row = cursor.fetchone()
        for i, exp in enumerate(expected):
            self.assertEqual(row[i], exp, f"Mismatch at index {i}: {row[i]} != {exp}")
        cursor.close()
        conn.close()

    def test_int_text(self):
        self._test_roundtrip(False, (42,), (42,))

    def test_int_binary(self):
        self._test_roundtrip(True, (42,), (42,))

    def test_string_text(self):
        self._test_roundtrip(False, ("hello",), ("hello",))

    def test_string_binary(self):
        self._test_roundtrip(True, ("hello",), ("hello",))

    def test_float_text(self):
        conn = create_connection({"binary": False})
        cursor = conn.cursor()
        cursor.execute("SELECT ?", (3.14,))
        row = cursor.fetchone()
        self.assertAlmostEqual(float(row[0]), 3.14, places=2)
        cursor.close()
        conn.close()

    def test_float_binary(self):
        conn = create_connection({"binary": True})
        cursor = conn.cursor()
        cursor.execute("SELECT ?", (3.14,))
        row = cursor.fetchone()
        self.assertAlmostEqual(row[0], 3.14, places=2)
        cursor.close()
        conn.close()

    def test_decimal_text(self):
        self._test_roundtrip(False, (decimal.Decimal("123.45"),), (decimal.Decimal("123.45"),))

    def test_decimal_binary(self):
        self._test_roundtrip(True, (decimal.Decimal("123.45"),), (decimal.Decimal("123.45"),))

    def test_none_text(self):
        self._test_roundtrip(False, (None,), (None,))

    def test_none_binary(self):
        self._test_roundtrip(True, (None,), (None,))

    def test_datetime_text(self):
        """CONPY-343: text protocol must preserve datetime type via SQL TIMESTAMP literal."""
        dt = datetime.datetime(2025, 1, 15, 10, 30, 0)
        conn = create_connection({"binary": False})
        cursor = conn.cursor()
        cursor.execute("SELECT ?", (dt,))
        row = cursor.fetchone()
        self.assertIsInstance(row[0], datetime.datetime)
        self.assertEqual(row[0], dt)
        cursor.close()
        conn.close()

    def test_datetime_binary(self):
        dt = datetime.datetime(2025, 1, 15, 10, 30, 0)
        self._test_roundtrip(True, (dt,), (dt,))

    def test_bytes_text(self):
        """bytes roundtrip via VARBINARY column in text mode"""
        b = b'\x00\x01\x02\x03'
        conn = create_connection({"binary": False})
        cursor = conn.cursor()
        cursor.execute("CREATE TEMPORARY TABLE _test_bytes_text (v VARBINARY(255))")
        cursor.execute("INSERT INTO _test_bytes_text VALUES (?)", (b,))
        cursor.execute("SELECT v FROM _test_bytes_text")
        row = cursor.fetchone()
        self.assertEqual(row[0], b)
        cursor.close()
        conn.close()

    def test_bytes_binary(self):
        """bytes roundtrip via VARBINARY column in binary mode"""
        b = b'\x00\x01\x02\x03'
        conn = create_connection({"binary": True})
        cursor = conn.cursor()
        cursor.execute("CREATE TEMPORARY TABLE _test_bytes_bin (v VARBINARY(255))")
        cursor.execute("INSERT INTO _test_bytes_bin VALUES (?)", (b,))
        cursor.execute("SELECT v FROM _test_bytes_bin")
        row = cursor.fetchone()
        self.assertEqual(row[0], b)
        cursor.close()
        conn.close()


class TestBinaryOptionWithTable(unittest.TestCase):
    """Test binary option with actual table operations"""

    def setUp(self):
        self.conn = create_connection()
        cursor = self.conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS test_binary_opt")
        cursor.execute(
            "CREATE TEMPORARY TABLE test_binary_opt ("
            "id INT PRIMARY KEY, "
            "name VARCHAR(50), "
            "val DECIMAL(10,2), "
            "ts DATETIME"
            ")"
        )
        cursor.close()

    def tearDown(self):
        self.conn.close()

    def test_insert_select_text(self):
        """Insert and select with text protocol"""
        cursor = self.conn.cursor(binary=False)
        cursor.execute(
            "INSERT INTO test_binary_opt VALUES (?, ?, ?, ?)",
            (1, "text_mode", decimal.Decimal("99.99"), datetime.datetime(2025, 6, 15, 12, 0, 0))
        )
        cursor.execute("SELECT * FROM test_binary_opt WHERE id = ?", (1,))
        row = cursor.fetchone()
        self.assertEqual(row[0], 1)
        self.assertEqual(row[1], "text_mode")
        self.assertEqual(row[2], decimal.Decimal("99.99"))
        cursor.close()

    def test_insert_select_binary(self):
        """Insert and select with binary protocol"""
        cursor = self.conn.cursor(binary=True)
        cursor.execute(
            "INSERT INTO test_binary_opt VALUES (?, ?, ?, ?)",
            (2, "binary_mode", decimal.Decimal("88.88"), datetime.datetime(2025, 6, 15, 12, 0, 0))
        )
        cursor.execute("SELECT * FROM test_binary_opt WHERE id = ?", (2,))
        row = cursor.fetchone()
        self.assertEqual(row[0], 2)
        self.assertEqual(row[1], "binary_mode")
        self.assertEqual(row[2], decimal.Decimal("88.88"))
        cursor.close()

    def test_insert_text_select_binary(self):
        """Insert with text, select with binary"""
        cursor_text = self.conn.cursor(binary=False)
        cursor_text.execute(
            "INSERT INTO test_binary_opt VALUES (?, ?, ?, ?)",
            (3, "cross_mode", decimal.Decimal("77.77"), datetime.datetime(2025, 6, 15, 12, 0, 0))
        )
        cursor_text.close()

        cursor_bin = self.conn.cursor(binary=True)
        cursor_bin.execute("SELECT * FROM test_binary_opt WHERE id = ?", (3,))
        row = cursor_bin.fetchone()
        self.assertEqual(row[0], 3)
        self.assertEqual(row[1], "cross_mode")
        self.assertEqual(row[2], decimal.Decimal("77.77"))
        cursor_bin.close()

    def test_insert_dict_params_with_binary_connection(self):
        """Dict params use text protocol even with binary connection"""
        conn = create_connection({"binary": True})
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS test_binary_opt2")
        cursor.execute(
            "CREATE TEMPORARY TABLE test_binary_opt2 ("
            "id INT PRIMARY KEY, name VARCHAR(50))"
        )
        cursor.execute(
            "INSERT INTO test_binary_opt2 VALUES (%(id)s, %(name)s)",
            {"id": 1, "name": "dict_mode"}
        )
        cursor.execute("SELECT * FROM test_binary_opt2 WHERE id = %(id)s", {"id": 1})
        row = cursor.fetchone()
        self.assertEqual(row[0], 1)
        self.assertEqual(row[1], "dict_mode")
        cursor.close()
        conn.close()


class TestPreparedOptionCompat(unittest.TestCase):
    """Test the deprecated 1.x 'prepared' cursor option."""

    @staticmethod
    def _prepared_cursor(conn):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            return conn.cursor(prepared=True)

    def test_prepared_true_emits_deprecation_warning(self):
        """cursor(prepared=True) warns DeprecationWarning"""
        conn = create_connection()
        with self.assertWarns(DeprecationWarning):
            cursor = conn.cursor(prepared=True)
        cursor.close()
        conn.close()

    def test_prepared_true_enables_binary(self):
        """cursor(prepared=True) runs via the binary (prepared statement) protocol"""
        conn = create_connection()  # binary=False default
        cursor = self._prepared_cursor(conn)
        self.assertTrue(cursor._use_binary)
        cursor.execute("SELECT ? as val", (42,))
        self.assertEqual(cursor.fetchone()[0], 42)
        cursor.close()
        conn.close()

    def test_prepared_ignores_sql_after_first_execute(self):
        """After the first execute() the SQL is ignored (1.x behavior)"""
        conn = create_connection()
        cursor = self._prepared_cursor(conn)
        # First execute() prepares "SELECT ? as val".
        cursor.execute("SELECT ? as val", (1,))
        self.assertEqual(cursor.fetchone()[0], 1)
        # A completely different SQL is ignored; the prepared statement runs.
        cursor.execute("SELECT ? + 999 as other", (2,))
        self.assertEqual(cursor.fetchone()[0], 2)
        # Even an empty SQL string is accepted and ignored.
        cursor.execute("", (3,))
        self.assertEqual(cursor.fetchone()[0], 3)
        cursor.close()
        conn.close()

    def test_non_prepared_cursor_honors_sql(self):
        """A normal binary cursor honors each execute()'s SQL (contrast)"""
        conn = create_connection()
        cursor = conn.cursor(binary=True)
        cursor.execute("SELECT ? as val", (1,))
        self.assertEqual(cursor.fetchone()[0], 1)
        cursor.execute("SELECT ? + 100 as val", (2,))
        self.assertEqual(cursor.fetchone()[0], 102)
        cursor.close()
        conn.close()

    def test_prepared_false_uses_text(self):
        """cursor(prepared=False) leaves binary disabled and does not pin SQL"""
        conn = create_connection()
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            cursor = conn.cursor(prepared=False)
        self.assertFalse(cursor._use_binary)
        cursor.execute("SELECT ? as val", (7,))
        self.assertEqual(cursor.fetchone()[0], 7)
        cursor.execute("SELECT ? + 1 as val", (7,))
        self.assertEqual(cursor.fetchone()[0], 8)
        cursor.close()
        conn.close()


if __name__ == '__main__':
    unittest.main()
