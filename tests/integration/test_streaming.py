#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

import unittest
import mariadb
from tests.base_test import is_native

from ..conftest import get_test_config as conf


class TestStreaming(unittest.TestCase):
    """Test streaming (unbuffered) result sets"""

    def setUp(self):
        self.connection = mariadb.connect(**conf())
        self.cursor = self.connection.cursor()
        
        # Create test table with data
        self.cursor.execute("DROP TABLE IF EXISTS test_streaming")
        self.cursor.execute("""
            CREATE TABLE test_streaming (
                id INT PRIMARY KEY,
                value VARCHAR(50)
            )
        """)
        
        # Insert test data (20 rows)
        for i in range(1, 21):
            self.cursor.execute(
                "INSERT INTO test_streaming VALUES (?, ?)",
                (i, f"value_{i}")
            )
        self.connection.commit()

    def tearDown(self):
        try:
            self.cursor.execute("DROP TABLE IF EXISTS test_streaming")
            self.connection.commit()
        except:
            pass
        finally:
            self.cursor.close()
            self.connection.close()

    def test_fetch_remaining_buffered(self):
        """Test fetch_remaining on buffered cursor"""
        cursor = self.connection.cursor(buffered=True)
        cursor.execute("SELECT * FROM test_streaming ORDER BY id")
        
        # Fetch a few rows
        row1 = cursor.fetchone()
        self.assertEqual(row1[0], 1)
        row2 = cursor.fetchone()
        self.assertEqual(row2[0], 2)
        
        cursor.execute("SELECT 10")
        
        row1 = cursor.fetchone()
        self.assertEqual(row1[0], 10)
        cursor.close()

    def test_fetch_remaining_streaming(self):
        """Test fetch_remaining on streaming cursor"""
        cursor = self.connection.cursor(buffered=False)
        cursor.execute("SELECT * FROM test_streaming ORDER BY id")
        
        # Fetch a few rows
        row1 = cursor.fetchone()
        self.assertEqual(row1[0], 1)
        row2 = cursor.fetchone()
        self.assertEqual(row2[0], 2)
        
        cursor.execute("SELECT 10")
        row1 = cursor.fetchone()
        self.assertEqual(row1[0], 10)
        cursor.close()

    def test_scroll_relative_buffered(self):
        """Test scroll with relative mode on buffered cursor"""
        cursor = self.connection.cursor(buffered=True)
        cursor.execute("SELECT * FROM test_streaming ORDER BY id")
        
        # Scroll forward 5 rows
        cursor.scroll(5, mode='relative')
        row = cursor.fetchone()
        self.assertEqual(row[0], 6)
        
        # Scroll forward 3 more rows
        cursor.scroll(3, mode='relative')
        row = cursor.fetchone()
        self.assertEqual(row[0], 10)
        
        # Scroll backward 5 rows
        cursor.scroll(-5, mode='relative')
        row = cursor.fetchone()
        self.assertEqual(row[0], 6)
        
        # Scroll 0 (no movement)
        cursor.scroll(0, mode='relative')
        row = cursor.fetchone()
        self.assertEqual(row[0], 7)
        
        cursor.close()

    def test_scroll_absolute_buffered(self):
        """Test scroll with absolute mode on buffered cursor"""
        cursor = self.connection.cursor(buffered=True)
        cursor.execute("SELECT * FROM test_streaming ORDER BY id")
        
        # Scroll to position 10 (0-indexed, so row 10)
        cursor.scroll(10, mode='absolute')
        row = cursor.fetchone()
        self.assertEqual(row[0], 11)
        
        # Scroll to position 0 (before first row)
        cursor.scroll(0, mode='absolute')
        row = cursor.fetchone()
        self.assertEqual(row[0], 1)
        
        # Scroll to position 15
        cursor.scroll(15, mode='absolute')
        row = cursor.fetchone()
        self.assertEqual(row[0], 16)
        
        cursor.close()

    def test_scroll_invalid_mode_buffered(self):
        """Test scroll with invalid mode on buffered cursor"""
        cursor = self.connection.cursor(buffered=True)
        cursor.execute("SELECT * FROM test_streaming ORDER BY id")
        
        # Invalid mode should raise ValueError
        with self.assertRaises(mariadb.ProgrammingError) as cm:
            cursor.scroll(5, mode='invalid')
        self.assertIn("Invalid", str(cm.exception))
        
        cursor.close()

    def test_scroll_out_of_range_buffered(self):
        """Test scroll out of range on buffered cursor"""
        cursor = self.connection.cursor(buffered=True)
        cursor.execute("SELECT * FROM test_streaming ORDER BY id")
        
        # Scroll past end
        with self.assertRaises(mariadb.ProgrammingError) as cm:
            cursor.scroll(100, mode='relative')
        self.assertIn("out of range", str(cm.exception))
        
        # Scroll before start with absolute
        with self.assertRaises(mariadb.ProgrammingError) as cm:
            cursor.scroll(-5, mode='absolute')
        self.assertIn("out of range", str(cm.exception))
        
        cursor.close()

    def test_scroll_relative_streaming(self):
        """Test scroll with relative mode on streaming cursor"""
        cursor = self.connection.cursor(buffered=False)
        cursor.execute("SELECT * FROM test_streaming ORDER BY id")
        
        # Fetch first row
        row = cursor.fetchone()
        self.assertEqual(row[0], 1)
        
        # Scroll forward 5 rows (skips rows 2-6)
        if is_native():
            cursor.scroll(5, mode='relative')
            row = cursor.fetchone()
            self.assertEqual(row[0], 7)
            
            # Scroll forward 3 more rows (skips rows 8-10)
            cursor.scroll(3, mode='relative')
            row = cursor.fetchone()
            self.assertEqual(row[0], 11)
            
            # Scroll 0 (no movement)
            cursor.scroll(0, mode='relative')
            row = cursor.fetchone()
            self.assertEqual(row[0], 12)
        
        cursor.close()

    def test_scroll_absolute_streaming_not_supported(self):
        """Test that absolute mode is not supported on streaming cursor"""
        cursor = self.connection.cursor(buffered=False)
        cursor.execute("SELECT * FROM test_streaming ORDER BY id")
        
        # Absolute mode should raise ValueError
        with self.assertRaises(mariadb.ProgrammingError) as cm:
            cursor.scroll(5, mode='absolute')
        if (is_native()):
            self.assertIn("Streaming cursors only support relative scroll mode", str(cm.exception))
        else:
            self.assertIn("This method is available only for cursors with a buffered result set", str(cm.exception))
        
        cursor.close()

    def test_scroll_negative_streaming_not_supported(self):
        """Test that negative scroll is not supported on streaming cursor"""
        cursor = self.connection.cursor(buffered=False)
        cursor.execute("SELECT * FROM test_streaming ORDER BY id")
        
        # Fetch a row first
        cursor.fetchone()
        
        # Negative scroll should raise ValueError
        with self.assertRaises(mariadb.ProgrammingError) as cm:
            cursor.scroll(-1, mode='relative')
        
        cursor.close()

    def test_scroll_past_end_streaming(self):
        """Test scrolling past end on streaming cursor"""
        cursor = self.connection.cursor(buffered=False)
        cursor.execute("SELECT * FROM test_streaming ORDER BY id LIMIT 5")
        
        # Fetch first row
        cursor.fetchone()
        
        # Try to scroll past end
        with self.assertRaises(mariadb.ProgrammingError) as cm:
            cursor.scroll(10, mode='relative')
        
        cursor.close()

    def test_scroll_invalid_mode_streaming(self):
        """Test scroll with invalid mode on streaming cursor"""
        cursor = self.connection.cursor(buffered=False)
        cursor.execute("SELECT * FROM test_streaming ORDER BY id")
        
        # Invalid mode should raise ValueError
        with self.assertRaises(mariadb.ProgrammingError) as cm:
            cursor.scroll(5, mode='invalid')
        
        cursor.close()

    def test_streaming_result_consumed_before_new_query(self):
        """Test that streaming results are consumed before executing new query"""
        cursor = self.connection.cursor(buffered=False)
        
        # Execute first query
        cursor.execute("SELECT * FROM test_streaming ORDER BY id")
        
        # Fetch only a few rows
        cursor.fetchone()
        cursor.fetchone()
        
        # Execute new query - should consume remaining rows from first query
        cursor.execute("SELECT COUNT(*) FROM test_streaming")
        row = cursor.fetchone()
        self.assertEqual(row[0], 20)
        
        cursor.close()

    def test_buffered_vs_streaming_behavior(self):
        """Test difference between buffered and streaming cursors"""
        # Buffered cursor - all rows loaded immediately
        buffered_cursor = self.connection.cursor(buffered=True)
        buffered_cursor.execute("SELECT * FROM test_streaming ORDER BY id")
        self.assertEqual(buffered_cursor.rowcount, 20)
        
        # Streaming cursor - rows loaded on demand
        streaming_cursor = self.connection.cursor(buffered=False)
        streaming_cursor.execute("SELECT * FROM test_streaming ORDER BY id")
        self.assertEqual(streaming_cursor.rowcount, 0)
        
        # Fetch all rows
        rows = streaming_cursor.fetchall()
        self.assertEqual(len(rows), 20)
        
        buffered_cursor.close()
        streaming_cursor.close()
