#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""
Integration tests for cursor features including named_tuple, dictionary, and buffered cursors
"""

import unittest
import mariadb
from decimal import Decimal
from ..base_test import create_connection


class CursorFeaturesTest(unittest.TestCase):
    """Test cursor features like named_tuple, dictionary, and buffered modes"""

    def setUp(self):
        """Set up test connection"""
        self.connection = create_connection()
        self.cursor = self.connection.cursor()
        
        # Create test table
        self.cursor.execute("""
            CREATE TEMPORARY TABLE test_cursor_features (
                id INT PRIMARY KEY AUTO_INCREMENT,
                name VARCHAR(50),
                value DECIMAL(10,2),
                active BOOLEAN
            )
        """)
        
        # Insert test data
        test_data = [
            ('Alice', Decimal('100.50'), True),
            ('Bob', Decimal('200.75'), False),
            ('Charlie', Decimal('300.25'), True),
        ]
        self.cursor.executemany(
            "INSERT INTO test_cursor_features (name, value, active) VALUES (?, ?, ?)",
            test_data
        )
        self.connection.commit()

    def tearDown(self):
        """Clean up test resources"""
        if hasattr(self, 'cursor') and self.cursor:
            self.cursor.close()
        if hasattr(self, 'connection') and self.connection:
            self.connection.close()

    def test_named_tuple_cursor(self):
        """Test named_tuple cursor option"""
        cursor = self.connection.cursor(named_tuple=True)
        cursor.execute("SELECT id, name, value, active FROM test_cursor_features WHERE id = 1")
        row = cursor.fetchone()
        
        # Test attribute access
        self.assertEqual(row.id, 1)
        self.assertEqual(row.name, 'Alice')
        self.assertEqual(row.value, Decimal('100.50'))
        self.assertEqual(row.active, True)
        
        # Test index access still works
        self.assertEqual(row[0], 1)
        self.assertEqual(row[1], 'Alice')
        
        cursor.close()

    def test_named_tuple_cursor_with_alias(self):
        """Test named_tuple cursor with column aliases"""
        cursor = self.connection.cursor(named_tuple=True)
        cursor.execute("SELECT id as user_id, name as user_name FROM test_cursor_features WHERE id = 2")
        row = cursor.fetchone()
        
        # Test alias attribute access
        self.assertEqual(row.user_id, 2)
        self.assertEqual(row.user_name, 'Bob')
        
        cursor.close()

    def test_named_tuple_fetchall(self):
        """Test named_tuple cursor with fetchall"""
        cursor = self.connection.cursor(named_tuple=True)
        cursor.execute("SELECT id, name FROM test_cursor_features ORDER BY id")
        rows = cursor.fetchall()
        
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0].name, 'Alice')
        self.assertEqual(rows[1].name, 'Bob')
        self.assertEqual(rows[2].name, 'Charlie')
        
        cursor.close()

    def test_dictionary_cursor(self):
        """Test dictionary cursor option"""
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("SELECT id, name, value, active FROM test_cursor_features WHERE id = 1")
        row = cursor.fetchone()
        
        # Test dictionary access
        self.assertEqual(row['id'], 1)
        self.assertEqual(row['name'], 'Alice')
        self.assertEqual(row['value'], Decimal('100.50'))
        self.assertEqual(row['active'], True)
        
        # Test keys
        self.assertIn('id', row)
        self.assertIn('name', row)
        
        cursor.close()

    def test_dictionary_cursor_with_alias(self):
        """Test dictionary cursor with column aliases"""
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("SELECT id as user_id, name as user_name FROM test_cursor_features WHERE id = 2")
        row = cursor.fetchone()
        
        # Test alias dictionary access
        self.assertEqual(row['user_id'], 2)
        self.assertEqual(row['user_name'], 'Bob')
        
        cursor.close()

    def test_dictionary_fetchall(self):
        """Test dictionary cursor with fetchall"""
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("SELECT id, name FROM test_cursor_features ORDER BY id")
        rows = cursor.fetchall()
        
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]['name'], 'Alice')
        self.assertEqual(rows[1]['name'], 'Bob')
        self.assertEqual(rows[2]['name'], 'Charlie')
        
        cursor.close()

    def test_buffered_cursor(self):
        """Test buffered cursor option"""
        cursor = self.connection.cursor(buffered=True)
        cursor.execute("SELECT id, name FROM test_cursor_features ORDER BY id")
        
        # With buffered cursor, rowcount should be available immediately
        self.assertEqual(cursor.rowcount, 3)
        
        # Can still fetch rows
        rows = cursor.fetchall()
        self.assertEqual(len(rows), 3)
        
        cursor.close()

    def test_buffered_named_tuple_cursor(self):
        """Test combining buffered and named_tuple options"""
        cursor = self.connection.cursor(buffered=True, named_tuple=True)
        cursor.execute("SELECT id, name FROM test_cursor_features ORDER BY id")
        
        self.assertEqual(cursor.rowcount, 3)
        row = cursor.fetchone()
        self.assertEqual(row.name, 'Alice')
        
        cursor.close()

    def test_buffered_dictionary_cursor(self):
        """Test combining buffered and dictionary options"""
        cursor = self.connection.cursor(buffered=True, dictionary=True)
        cursor.execute("SELECT id, name FROM test_cursor_features ORDER BY id")
        
        self.assertEqual(cursor.rowcount, 3)
        row = cursor.fetchone()
        self.assertEqual(row['name'], 'Alice')
        
        cursor.close()

    def test_cursor_iterator_named_tuple(self):
        """Test cursor iterator with named_tuple"""
        cursor = self.connection.cursor(named_tuple=True)
        cursor.execute("SELECT id, name FROM test_cursor_features ORDER BY id")
        
        names = [row.name for row in cursor]
        self.assertEqual(names, ['Alice', 'Bob', 'Charlie'])
        
        cursor.close()

    def test_cursor_iterator_dictionary(self):
        """Test cursor iterator with dictionary"""
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("SELECT id, name FROM test_cursor_features ORDER BY id")
        
        names = [row['name'] for row in cursor]
        self.assertEqual(names, ['Alice', 'Bob', 'Charlie'])
        
        cursor.close()

    def test_fetchmany_named_tuple(self):
        """Test fetchmany with named_tuple cursor"""
        cursor = self.connection.cursor(named_tuple=True)
        cursor.execute("SELECT id, name FROM test_cursor_features ORDER BY id")
        
        rows = cursor.fetchmany(2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].name, 'Alice')
        self.assertEqual(rows[1].name, 'Bob')
        
        rows = cursor.fetchmany(2)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].name, 'Charlie')
        
        cursor.close()

    def test_fetchmany_dictionary(self):
        """Test fetchmany with dictionary cursor"""
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("SELECT id, name FROM test_cursor_features ORDER BY id")
        
        rows = cursor.fetchmany(2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['name'], 'Alice')
        self.assertEqual(rows[1]['name'], 'Bob')
        
        cursor.close()

    def test_cursor_description_named_tuple(self):
        """Test cursor description with named_tuple"""
        cursor = self.connection.cursor(named_tuple=True)
        cursor.execute("SELECT id, name, value FROM test_cursor_features LIMIT 1")
        
        # Description should be available
        self.assertIsNotNone(cursor.description)
        self.assertEqual(len(cursor.description), 3)
        
        # Check column names
        col_names = [desc[0] for desc in cursor.description]
        self.assertEqual(col_names, ['id', 'name', 'value'])
        
        cursor.close()

    def test_cursor_description_dictionary(self):
        """Test cursor description with dictionary"""
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("SELECT id, name, value FROM test_cursor_features LIMIT 1")
        
        # Description should be available
        self.assertIsNotNone(cursor.description)
        self.assertEqual(len(cursor.description), 3)
        
        cursor.close()

    def test_empty_result_named_tuple(self):
        """Test named_tuple cursor with empty result"""
        cursor = self.connection.cursor(named_tuple=True)
        cursor.execute("SELECT id, name FROM test_cursor_features WHERE id = 999")
        
        row = cursor.fetchone()
        self.assertIsNone(row)
        
        rows = cursor.fetchall()
        self.assertEqual(rows, [])
        
        cursor.close()

    def test_empty_result_dictionary(self):
        """Test dictionary cursor with empty result"""
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("SELECT id, name FROM test_cursor_features WHERE id = 999")
        
        row = cursor.fetchone()
        self.assertIsNone(row)
        
        rows = cursor.fetchall()
        self.assertEqual(rows, [])
        
        cursor.close()

    def test_null_values_named_tuple(self):
        """Test named_tuple cursor with NULL values"""
        self.cursor.execute("INSERT INTO test_cursor_features (name, value, active) VALUES (NULL, NULL, NULL)")
        self.connection.commit()
        
        cursor = self.connection.cursor(named_tuple=True)
        cursor.execute("SELECT name, value, active FROM test_cursor_features WHERE name IS NULL")
        row = cursor.fetchone()
        
        self.assertIsNone(row.name)
        self.assertIsNone(row.value)
        self.assertIsNone(row.active)
        
        cursor.close()

    def test_null_values_dictionary(self):
        """Test dictionary cursor with NULL values"""
        self.cursor.execute("INSERT INTO test_cursor_features (name, value, active) VALUES (NULL, NULL, NULL)")
        self.connection.commit()
        
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("SELECT name, value, active FROM test_cursor_features WHERE name IS NULL")
        row = cursor.fetchone()
        
        self.assertIsNone(row['name'])
        self.assertIsNone(row['value'])
        self.assertIsNone(row['active'])
        
        cursor.close()

    def test_special_column_names_named_tuple(self):
        """Test named_tuple with special column names"""
        cursor = self.connection.cursor(named_tuple=True)
        # Use aliases with special characters that need sanitization
        cursor.execute("SELECT id as `user-id`, name as `user name` FROM test_cursor_features WHERE id = 1")
        row = cursor.fetchone()
        
        # Should handle special characters in column names
        self.assertIsNotNone(row)
        # Access by index should work
        self.assertEqual(row[0], 1)
        self.assertEqual(row[1], 'Alice')
        
        cursor.close()

    def test_cursor_arraysize(self):
        """Test cursor arraysize property"""
        cursor = self.connection.cursor()
        
        # Default arraysize
        self.assertEqual(cursor.arraysize, 1)
        
        # Set custom arraysize
        cursor.arraysize = 5
        self.assertEqual(cursor.arraysize, 5)
        
        cursor.execute("SELECT id FROM test_cursor_features")
        rows = cursor.fetchmany()  # Should fetch arraysize rows
        self.assertEqual(len(rows), 3)  # Only 3 rows available
        
        cursor.close()

    def test_cursor_with_context_manager(self):
        """Test cursor with context manager"""
        with self.connection.cursor(named_tuple=True) as cursor:
            cursor.execute("SELECT id, name FROM test_cursor_features WHERE id = 1")
            row = cursor.fetchone()
            self.assertEqual(row.name, 'Alice')
        
        # Cursor should be closed after context
        # Note: Some implementations may not close cursor automatically

    def test_multiple_cursors_same_connection(self):
        """Test multiple cursors with different options on same connection"""
        cursor1 = self.connection.cursor(named_tuple=True)
        cursor2 = self.connection.cursor(dictionary=True)
        cursor3 = self.connection.cursor()
        
        cursor1.execute("SELECT id, name FROM test_cursor_features WHERE id = 1")
        cursor2.execute("SELECT id, name FROM test_cursor_features WHERE id = 2")
        cursor3.execute("SELECT id, name FROM test_cursor_features WHERE id = 3")
        
        row1 = cursor1.fetchone()
        row2 = cursor2.fetchone()
        row3 = cursor3.fetchone()
        
        # Each cursor should return data in its own format
        self.assertEqual(row1.name, 'Alice')  # named_tuple
        self.assertEqual(row2['name'], 'Bob')  # dictionary
        self.assertEqual(row3[1], 'Charlie')  # regular tuple
        
        cursor1.close()
        cursor2.close()
        cursor3.close()


if __name__ == '__main__':
    unittest.main()
