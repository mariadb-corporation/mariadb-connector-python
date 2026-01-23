#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

import unittest
import mariadb
from ..base_test import conf


class TestMultiCursorUnbuffered(unittest.TestCase):
    """
    Integration tests for multi-cursor scenarios with unbuffered results.
    Tests the connection-level active_result_cursor tracking and automatic
    draining to prevent "Commands out of sync" errors.
    
    NOTE: These tests only run with the native C extension (mariadb_c) since
    the active_result_cursor tracking is implemented at the C level.
    """

    def setUp(self):
        config = conf()
        self.connection = mariadb.connect(**config)
        self.cursor = self.connection.cursor()
        
        # Clean up any existing table from previous failed tests
        try:
            self.cursor.execute("DROP TABLE IF EXISTS test_multi_cursor")
        except:
            pass
            
        self.cursor.execute("""
            CREATE TABLE test_multi_cursor (
                id INT PRIMARY KEY,
                value VARCHAR(100)
            )
        """)
        # Insert test data (20 rows is sufficient for testing)
        for i in range(20):
            self.cursor.execute(
                "INSERT INTO test_multi_cursor VALUES (?, ?)",
                (i, f"value_{i}")
            )
        self.connection.commit()

    def tearDown(self):
        self.cursor.execute("DROP TABLE IF EXISTS test_multi_cursor")
        self.cursor.close()
        self.connection.close()

    def test_two_cursors_unbuffered_partial_fetch(self):
        """
        Test that a second cursor can execute when first cursor has
        unbuffered result with partial fetch.
        """
        cursor1 = self.connection.cursor(buffered=False)
        cursor2 = self.connection.cursor()

        # Cursor1 executes and fetches only 1 row out of 20
        cursor1.execute("SELECT * FROM test_multi_cursor ORDER BY id")
        row = cursor1.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 0)

        # Cursor2 should be able to execute - connection should drain cursor1
        cursor2.execute("SELECT COUNT(*) FROM test_multi_cursor")
        result = cursor2.fetchone()
        self.assertEqual(result[0], 20)

        cursor1.close()
        cursor2.close()

    def test_same_cursor_reexecute_unbuffered(self):
        """
        Test that the same cursor can re-execute without finishing
        its previous unbuffered result.
        """
        cursor = self.connection.cursor(buffered=False)

        # First execute - fetch only 1 row
        cursor.execute("SELECT * FROM test_multi_cursor ORDER BY id")
        row = cursor.fetchone()
        self.assertEqual(row[0], 0)

        # Re-execute on same cursor - should drain previous result
        cursor.execute("SELECT COUNT(*) FROM test_multi_cursor")
        result = cursor.fetchone()
        self.assertEqual(result[0], 20)

        cursor.close()

    def test_unbuffered_partial_fetch_then_close(self):
        """
        Test scenario where cursor starts unbuffered, fetches partial,
        then is explicitly closed before another cursor executes.
        """
        cursor1 = self.connection.cursor(buffered=False)
        cursor2 = self.connection.cursor()

        # Cursor1 starts unbuffered and fetches partial
        cursor1.execute("SELECT * FROM test_multi_cursor ORDER BY id")
        row = cursor1.fetchone()
        self.assertEqual(row[0], 0)

        # Explicitly close cursor1 (should drain remaining result)
        cursor1.close()

        # Cursor2 executes - connection should be in good state
        cursor2.execute("SELECT COUNT(*) FROM test_multi_cursor")
        result = cursor2.fetchone()
        self.assertEqual(result[0], 20)

        cursor2.close()

    def test_multiple_cursors_sequential_unbuffered(self):
        """
        Test multiple cursors executing sequentially with unbuffered results.
        """
        cursor1 = self.connection.cursor(buffered=False)
        cursor2 = self.connection.cursor(buffered=False)
        cursor3 = self.connection.cursor(buffered=False)

        # Cursor1 executes and partially fetches
        cursor1.execute("SELECT * FROM test_multi_cursor WHERE id < 10")
        cursor1.fetchone()

        # Cursor2 executes - should drain cursor1
        cursor2.execute("SELECT * FROM test_multi_cursor WHERE id >= 10 AND id < 20")
        cursor2.fetchone()

        # Cursor3 executes - should drain cursor2
        cursor3.execute("SELECT COUNT(*) FROM test_multi_cursor")
        result = cursor3.fetchone()
        self.assertEqual(result[0], 20)

        cursor1.close()
        cursor2.close()
        cursor3.close()

    def test_unbuffered_no_fetch_then_execute(self):
        """
        Test cursor executes unbuffered query but doesn't fetch at all,
        then executes another query.
        """
        cursor = self.connection.cursor(buffered=False)

        # Execute but don't fetch
        cursor.execute("SELECT * FROM test_multi_cursor")

        # Execute again - should drain previous result
        cursor.execute("SELECT COUNT(*) FROM test_multi_cursor")
        result = cursor.fetchone()
        self.assertEqual(result[0], 20)

        cursor.close()

    def test_unbuffered_fetchall_completes_then_execute(self):
        """
        Test that fetchall() on unbuffered cursor properly completes
        and allows subsequent execute.
        """
        cursor = self.connection.cursor(buffered=False)

        # Execute and fetchall (completes the result)
        cursor.execute("SELECT * FROM test_multi_cursor WHERE id < 10")
        rows = cursor.fetchall()
        self.assertEqual(len(rows), 10)

        # Should be able to execute again without issues
        cursor.execute("SELECT COUNT(*) FROM test_multi_cursor")
        result = cursor.fetchone()
        self.assertEqual(result[0], 20)

        cursor.close()

    def test_cursor_close_with_active_unbuffered_result(self):
        """
        Test that closing a cursor with active unbuffered result
        properly unregisters it from connection.
        """
        cursor1 = self.connection.cursor(buffered=False)
        cursor2 = self.connection.cursor()

        # Cursor1 has active unbuffered result
        cursor1.execute("SELECT * FROM test_multi_cursor")
        cursor1.fetchone()

        # Close cursor1 while it has active result
        cursor1.close()

        # Cursor2 should be able to execute without issues
        cursor2.execute("SELECT COUNT(*) FROM test_multi_cursor")
        result = cursor2.fetchone()
        self.assertEqual(result[0], 20)

        cursor2.close()

    def test_cursor_dealloc_with_active_unbuffered_result(self):
        """
        Test that deleting a cursor with active unbuffered result
        properly unregisters it from connection (tests dealloc path).
        """
        cursor1 = self.connection.cursor(buffered=False)

        # Cursor1 has active unbuffered result
        cursor1.execute("SELECT * FROM test_multi_cursor")
        cursor1.fetchone()

        # Delete cursor1 (triggers dealloc)
        del cursor1

        # New cursor should be able to execute
        cursor2 = self.connection.cursor()
        cursor2.execute("SELECT COUNT(*) FROM test_multi_cursor")
        result = cursor2.fetchone()
        self.assertEqual(result[0], 20)

        cursor2.close()

    def test_unbuffered_cursor_execute_after_partial_fetchmany(self):
        """
        Test cursor with unbuffered result can execute after fetchmany.
        """
        cursor = self.connection.cursor(buffered=False)

        # Execute and fetch some rows with fetchmany
        cursor.execute("SELECT * FROM test_multi_cursor ORDER BY id")
        rows = cursor.fetchmany(5)
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0][0], 0)

        # Execute again - should drain remaining rows
        cursor.execute("SELECT COUNT(*) FROM test_multi_cursor")
        result = cursor.fetchone()
        self.assertEqual(result[0], 20)

        cursor.close()


if __name__ == '__main__':
    unittest.main()
