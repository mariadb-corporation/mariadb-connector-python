#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""
Integration tests for handling long data (>16MB)

Tests sending and receiving data larger than the default max_allowed_packet size.
"""

import os
import unittest
from mariadb_shared.sync_cursor_common import SyncCursorCommon
from ..base_test import create_connection, varied_bytes, varied_text


class LongDataTest(unittest.TestCase):
    """Test handling of long data packets"""

    def setUp(self):
        # Skip all tests if RUN_LONG_TEST is not set to "1"
        if os.environ.get('RUN_LONG_TEST') != '1':
            self.skipTest("Skipping long-running test. Set RUN_LONG_TEST=1 to run.")

        """Set up test connection and check max_allowed_packet"""
        self.connection = create_connection({'socket_timeout': 120})
        self.cursor = self.connection.cursor()
        
        # Check current max_allowed_packet setting
        self.cursor.execute("SELECT @@max_allowed_packet")
        self.max_allowed_packet = self.cursor.fetchone()[0]
        
        # Minimum required: 32MB for our tests
        self.min_required = 32 * 1024 * 1024
        
        if self.max_allowed_packet < self.min_required:
            self.skipTest(
                f"max_allowed_packet ({self.max_allowed_packet} bytes) is less than "
                f"required {self.min_required} bytes. "
                f"Set max_allowed_packet={self.min_required} in server config."
            )

    def tearDown(self):
        """Clean up test resources"""
        if hasattr(self, 'cursor') and self.cursor:
            self.cursor.close()
        if hasattr(self, 'connection') and self.connection:
            self.connection.close()

    def test_insert_long_varchar(self):
        """Test inserting and retrieving VARCHAR data >16MB"""
        # Create test table
        self.cursor.execute("""
            CREATE TEMPORARY TABLE test_long_varchar (
                id INT PRIMARY KEY AUTO_INCREMENT,
                data LONGTEXT
            )
        """)
        
        # Create data slightly larger than 16MB. Use a position-dependent
        # payload (not a repeated byte) so a misaligned fragment boundary is
        # actually detectable by the comparison.
        data_size = 17 * 1024 * 1024  # 17MB
        test_data = varied_text(data_size)
        with self.connection.cursor() as cursor:
            self.insert_long_varchar(test_data, data_size, cursor)
        self.cursor.execute('TRUNCATE TABLE test_long_varchar')

        with self.connection.cursor(binary=True) as cursor:
            self.insert_long_varchar(test_data, data_size, cursor)
    
    def insert_long_varchar(self, test_data: str, data_size: int, cursor):    
        # Insert long data
        cursor.execute(
            "INSERT INTO test_long_varchar (data) VALUES (?)",
            (test_data,)
        )
        self.connection.commit()
        
        # Retrieve and verify
        cursor.execute("SELECT data FROM test_long_varchar WHERE id = ?", (1,))
        result = cursor.fetchone()
        
        self.assertIsNotNone(result)
        self.assertEqual(len(result[0]), data_size)
        self.assertEqual(result[0], test_data)

    def test_insert_long_blob(self):
        """Test inserting and retrieving BLOB data >16MB"""
        # Create test table
        self.cursor.execute("""
            CREATE TEMPORARY TABLE test_long_blob (
                id INT PRIMARY KEY AUTO_INCREMENT,
                data LONGBLOB
            )
        """)
        
        # Create binary data slightly larger than 16MB
        data_size = 18 * 1024 * 1024  # 18MB
        test_data = varied_bytes(data_size)

        with self.connection.cursor() as cursor:
            self.insert_long_blob(test_data, data_size, cursor)
        self.cursor.execute('TRUNCATE TABLE test_long_blob')

        with self.connection.cursor(binary=True) as cursor:
            self.insert_long_blob(test_data, data_size, cursor)

    def insert_long_blob(self, test_data: bytes, data_size: int, cursor: SyncCursorCommon):
        # Insert long data
        cursor.execute(
            "INSERT INTO test_long_blob (data) VALUES (?)",
            (test_data,)
        )
        self.connection.commit()
        
        # Retrieve and verify
        cursor.execute("SELECT data FROM test_long_blob WHERE id = ?", (1,))
        result = cursor.fetchone()
        
        self.assertIsNotNone(result)
        self.assertEqual(len(result[0]), data_size)
        self.assertEqual(result[0], test_data)

    def test_insert_multiple_long_columns(self):
        """Test inserting multiple long columns in single row"""
        # Create test table with multiple LONGTEXT columns
        self.cursor.execute("""
            CREATE TEMPORARY TABLE test_multiple_long (
                id INT PRIMARY KEY AUTO_INCREMENT,
                data1 LONGTEXT,
                data2 LONGTEXT,
                data3 LONGBLOB
            )
        """)
        
        # Create test data (smaller to fit multiple columns). Three *distinct*
        # position-dependent payloads so a fragment boundary landing mid-column
        # (or a cross-column swap) is caught.
        data_size = 6 * 1024 * 1024  # 6MB each
        test_data1 = varied_text(data_size)
        test_data2 = varied_text(data_size)[::-1]
        test_data3 = varied_bytes(data_size)
        
        with self.connection.cursor() as cursor:
            self.insert_multiple_long_columns(test_data1, test_data2, test_data3, data_size, cursor)
        self.cursor.execute('TRUNCATE TABLE test_multiple_long')

        with self.connection.cursor(binary=True) as cursor:
            self.insert_multiple_long_columns(test_data1, test_data2, test_data3, data_size, cursor)
    
    def insert_multiple_long_columns(self, test_data1: str, test_data2: str, test_data3: bytes, data_size: int, cursor: SyncCursorCommon):
        # Insert long data
        cursor.execute(
            "INSERT INTO test_multiple_long (data1, data2, data3) VALUES (?, ?, ?)",
            (test_data1, test_data2, test_data3)
        )
        self.connection.commit()
        
        # Retrieve and verify
        cursor.execute("SELECT data1, data2, data3 FROM test_multiple_long WHERE id = ?", (1,))
        result = cursor.fetchone()

        assert result is not None and not isinstance(result, dict)
        self.assertEqual(len(result[0]), data_size)
        self.assertEqual(len(result[1]), data_size)
        self.assertEqual(len(result[2]), data_size)
        self.assertEqual(result[0], test_data1)
        self.assertEqual(result[1], test_data2)
        self.assertEqual(result[2], test_data3)

    def test_executemany_with_long_data(self):
        """Test executemany with long data parameters"""
        # Create test table
        self.cursor.execute("""
            CREATE TEMPORARY TABLE test_executemany_long (
                id INT PRIMARY KEY AUTO_INCREMENT,
                name VARCHAR(50),
                data LONGTEXT
            )
        """)
        
        # Create test data (smaller for multiple rows). Overlapping windows of a
        # varied buffer give three distinct, position-dependent payloads.
        data_size = 5 * 1024 * 1024  # 5MB per row
        base = varied_text(data_size + 2)
        rows = [
            ('row1', base[0:data_size]),
            ('row2', base[1:data_size + 1]),
            ('row3', base[2:data_size + 2]),
        ]
        
        with self.connection.cursor() as cursor:
            self.executemany_with_long_data(rows, data_size, cursor)
        self.cursor.execute('TRUNCATE TABLE test_executemany_long')

        with self.connection.cursor(binary=True) as cursor:
            self.executemany_with_long_data(rows, data_size, cursor)
    
    def executemany_with_long_data(self, rows: list[tuple[str, bytes]], data_size: int, cursor):
        # Insert multiple rows with long data
        cursor.executemany(
            "INSERT INTO test_executemany_long (name, data) VALUES (?, ?)",
            rows
        )
        self.connection.commit()
        
        # Verify all rows
        cursor.execute("SELECT name, data FROM test_executemany_long ORDER BY id")
        results = cursor.fetchall()
        
        self.assertEqual(len(results), len(rows))
        for i, (name, data) in enumerate(results):
            self.assertEqual(name, rows[i][0])
            self.assertEqual(len(data), data_size)
            self.assertEqual(data, rows[i][1])

    def test_prepared_statement_with_long_data(self):
        """Test prepared statements with long data"""
        # Create test table
        self.cursor.execute("""
            CREATE TEMPORARY TABLE test_prepared_long (
                id INT PRIMARY KEY AUTO_INCREMENT,
                data LONGTEXT
            )
        """)
        
        # Create test data
        data_size = 17 * 1024 * 1024  # 17MB
        test_data = varied_text(data_size)

        with self.connection.cursor() as cursor:
            self.prepared_statement_with_long_data(test_data, data_size, cursor)
        self.cursor.execute('TRUNCATE TABLE test_prepared_long')

        with self.connection.cursor(binary=True) as cursor:
            self.prepared_statement_with_long_data(test_data, data_size, cursor)
    
    def prepared_statement_with_long_data(self, test_data: str, data_size: int, cursor):
        # Use prepared statement
        cursor.execute(
            "INSERT INTO test_prepared_long (data) VALUES (?)",
            (test_data,)
        )
        self.connection.commit()
        
        # Retrieve using prepared statement
        cursor.execute("SELECT data FROM test_prepared_long WHERE id = ?", (1,))
        result = cursor.fetchone()
        
        self.assertIsNotNone(result)
        self.assertEqual(len(result[0]), data_size)
        self.assertEqual(result[0], test_data)

    def test_long_data_with_unicode(self):
        """Test long data with Unicode characters"""
        # Create test table
        self.cursor.execute("""
            CREATE TEMPORARY TABLE test_long_unicode (
                id INT PRIMARY KEY AUTO_INCREMENT,
                data LONGTEXT CHARACTER SET utf8mb4
            )
        """)
        
        # Create Unicode test data (emoji and multi-byte characters)
        # Each emoji is typically 4 bytes in UTF-8
        base_string = '🔥🌟💻🚀🎉' * 1000  # ~20KB of emoji
        repetitions = (17 * 1024 * 1024) // len(base_string.encode('utf-8'))
        test_data = base_string * repetitions
        
        actual_size = len(test_data.encode('utf-8'))
        
        # Insert long Unicode data
        self.cursor.execute(
            "INSERT INTO test_long_unicode (data) VALUES (?)",
            (test_data,)
        )
        self.connection.commit()
        
        # Retrieve and verify
        self.cursor.execute("SELECT data FROM test_long_unicode WHERE id = ?", (1,))
        result = self.cursor.fetchone()
        
        self.assertIsNotNone(result)
        self.assertEqual(result[0], test_data)

    def test_update_with_long_data(self):
        """Test updating existing row with long data"""
        # Create test table
        self.cursor.execute("""
            CREATE TEMPORARY TABLE test_update_long (
                id INT PRIMARY KEY AUTO_INCREMENT,
                data LONGTEXT
            )
        """)
        
        # Insert initial small data
        self.cursor.execute("INSERT INTO test_update_long (data) VALUES (?)", ('initial',))
        self.connection.commit()
        
        # Update with long data
        data_size = 17 * 1024 * 1024  # 17MB
        test_data = varied_text(data_size)

        self.cursor.execute(
            "UPDATE test_update_long SET data = ? WHERE id = 1",
            (test_data,)
        )
        self.connection.commit()
        
        # Verify update
        self.cursor.execute("SELECT data FROM test_update_long WHERE id = ?", (1,))
        result = self.cursor.fetchone()
        
        self.assertIsNotNone(result)
        self.assertEqual(len(result[0]), data_size)
        self.assertEqual(result[0], test_data)

    def test_select_where_long_data(self):
        """Test SELECT with long data in WHERE clause"""
        # Create test table
        self.cursor.execute("""
            CREATE TEMPORARY TABLE test_where_long (
                id INT PRIMARY KEY AUTO_INCREMENT,
                data LONGTEXT,
                name VARCHAR(50)
            )
        """)
        
        # Create test data (smaller for WHERE clause)
        data_size = 1 * 1024 * 1024  # 1MB
        test_data = varied_text(data_size)
        
        # Insert test rows
        self.cursor.execute(
            "INSERT INTO test_where_long (data, name) VALUES (?, ?)",
            (test_data, 'found')
        )
        self.cursor.execute(
            "INSERT INTO test_where_long (data, name) VALUES (?, ?)",
            ('different', 'not_found')
        )
        self.connection.commit()
        
        # Query with long data in WHERE clause
        self.cursor.execute(
            "SELECT name FROM test_where_long WHERE data = ?",
            (test_data,)
        )
        result = self.cursor.fetchone()
        
        self.assertIsNotNone(result)
        self.assertEqual(result[0], 'found')

    def test_max_packet_size_boundary(self):
        """Test data size approaching max_allowed_packet boundary"""
        # Create test table
        self.cursor.execute("""
            CREATE TEMPORARY TABLE test_boundary (
                id INT PRIMARY KEY AUTO_INCREMENT,
                data LONGBLOB
            )
        """)
        
        # Use 90% of max_allowed_packet to leave room for protocol overhead
        data_size = int(self.max_allowed_packet * 0.9)
        test_data = varied_bytes(data_size)
        
        # Insert data near boundary
        self.cursor.execute(
            "INSERT INTO test_boundary (data) VALUES (?)",
            (test_data,)
        )
        self.connection.commit()
        
        # Retrieve and verify
        self.cursor.execute("SELECT data FROM test_boundary WHERE id = ?", (1,))
        result = self.cursor.fetchone()
        
        self.assertIsNotNone(result)
        self.assertEqual(len(result[0]), len(test_data))
        self.assertEqual(result[0], test_data)


if __name__ == '__main__':
    unittest.main()
