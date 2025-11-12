#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""
Integration tests for error handling and edge cases
"""

import unittest
import mariadb
from ..base_test import create_connection, is_native
from ..conftest import get_test_config


class ErrorHandlingTest(unittest.TestCase):
    """Test error handling and edge cases"""

    def setUp(self):
        """Set up test connection"""
        self.connection = create_connection()
        self.cursor = self.connection.cursor()

    def tearDown(self):
        """Clean up test resources"""
        if hasattr(self, 'cursor') and self.cursor:
            try:
                self.cursor.close()
            except:
                pass
        if hasattr(self, 'connection') and self.connection:
            try:
                self.connection.close()
            except:
                pass

    def test_syntax_error(self):
        """Test SQL syntax error"""
        with self.assertRaises(mariadb.ProgrammingError):
            self.cursor.execute("SELCT * FROM nonexistent")

    def test_table_not_found(self):
        """Test table not found error"""
        with self.assertRaises(mariadb.ProgrammingError):
            self.cursor.execute("SELECT * FROM nonexistent_table_12345")

    def test_column_not_found(self):
        """Test column not found error"""
        self.cursor.execute("CREATE TEMPORARY TABLE test_col_error (id INT)")
        
        with self.assertRaises(mariadb.ProgrammingError):
            self.cursor.execute("SELECT nonexistent_column FROM test_col_error")

    def test_duplicate_key_error(self):
        """Test duplicate key error"""
        self.cursor.execute("""
            CREATE TEMPORARY TABLE test_dup_key (
                id INT PRIMARY KEY
            )
        """)
        self.cursor.execute("INSERT INTO test_dup_key VALUES (1)")
        
        with self.assertRaises(mariadb.IntegrityError):
            self.cursor.execute("INSERT INTO test_dup_key VALUES (1)")

    def test_null_constraint_violation(self):
        """Test NOT NULL constraint violation"""
        self.cursor.execute("""
            CREATE TEMPORARY TABLE test_not_null (
                id INT NOT NULL
            )
        """)
        
        with self.assertRaises(mariadb.IntegrityError):
            self.cursor.execute("INSERT INTO test_not_null VALUES (NULL)")

    def test_foreign_key_violation(self):
        """Test foreign key constraint violation"""
        self.cursor.execute("DROP TABLE IF EXISTS test_child")
        self.cursor.execute("DROP TABLE IF EXISTS test_parent")
        self.cursor.execute("""
            CREATE TABLE test_parent (
                id INT PRIMARY KEY
            ) ENGINE=InnoDB
        """)
        self.cursor.execute("""
            CREATE TABLE test_child (
                id INT,
                parent_id INT,
                FOREIGN KEY (parent_id) REFERENCES test_parent(id)
            ) ENGINE=InnoDB
        """)
        
        with self.assertRaises(mariadb.IntegrityError):
            self.cursor.execute("INSERT INTO test_child VALUES (1, 999)")
        self.cursor.execute("DROP TABLE IF EXISTS test_child")
        self.cursor.execute("DROP TABLE IF EXISTS test_parent")

    def test_data_too_long(self):
        """Test data too long error"""
        self.cursor.execute("""
            CREATE TEMPORARY TABLE test_too_long (
                val VARCHAR(10)
            )
        """)
        
        # Set strict mode
        self.cursor.execute("SET sql_mode='STRICT_ALL_TABLES'")
        
        with self.assertRaises(mariadb.DataError):
            self.cursor.execute("INSERT INTO test_too_long VALUES (?)", ('x' * 100,))

    def test_division_by_zero(self):
        """Test division by zero handling"""
        # In non-strict mode, this returns NULL
        self.cursor.execute("SET sql_mode=''")
        self.cursor.execute("SELECT 1/0")
        result = self.cursor.fetchone()
        self.assertIsNone(result[0])

    def test_execute_without_connection(self):
        """Test execute on closed connection"""
        conn = create_connection()
        cursor = conn.cursor()
        conn.close()
        
        with self.assertRaises((mariadb.Error, mariadb.ProgrammingError)):
            cursor.execute("SELECT 1")

    def test_fetch_without_execute(self):
        """Test fetch without execute"""
        cursor = self.connection.cursor()
        
        # Fetching without execute should raise error or return None
        with self.assertRaises(mariadb.ProgrammingError):
            cursor.fetchone()
        
        cursor.close()

    def test_fetchall_empty_result(self):
        """Test fetchall on empty result"""
        self.cursor.execute("CREATE TEMPORARY TABLE test_empty (id INT)")
        self.cursor.execute("SELECT * FROM test_empty")
        
        result = self.cursor.fetchall()
        self.assertEqual(result, [])

    def test_fetchmany_empty_result(self):
        """Test fetchmany on empty result"""
        self.cursor.execute("CREATE TEMPORARY TABLE test_empty2 (id INT)")
        self.cursor.execute("SELECT * FROM test_empty2")
        
        result = self.cursor.fetchmany(5)
        self.assertEqual(result, [])

    def test_fetchone_after_fetchall(self):
        """Test fetchone after fetchall"""
        self.cursor.execute("SELECT 1 UNION SELECT 2")
        self.cursor.fetchall()
        
        # Should return None after all rows fetched
        result = self.cursor.fetchone()
        self.assertIsNone(result)

    def test_invalid_parameter_count(self):
        """Test invalid parameter count in execute"""
        self.cursor.execute("CREATE TEMPORARY TABLE test_params (a INT, b INT)")
        
        with self.assertRaises((mariadb.ProgrammingError, TypeError)):
            self.cursor.execute("INSERT INTO test_params VALUES (?, ?)", (1,))  # Missing parameter

    def test_invalid_parameter_type(self):
        """Test invalid parameter type"""
        self.cursor.execute("CREATE TEMPORARY TABLE test_type (id INT)")
        
        # Some types may cause errors
        try:
            self.cursor.execute("INSERT INTO test_type VALUES (?)", (object(),))
            # If no error, that's also acceptable (implementation-specific)
        except (mariadb.ProgrammingError, mariadb.OperationalError, mariadb.DataError, TypeError):
            pass  # Expected

    def test_connection_invalid_host(self):
        """Test connection with invalid host"""
        config = get_test_config()
        config['host'] = 'invalid.host.that.does.not.exist.12345'
        config['connect_timeout'] = 2
        
        with self.assertRaises(mariadb.OperationalError):
            mariadb.connect(**config)

    def test_connection_invalid_port(self):
        """Test connection with invalid port"""
        config = get_test_config()
        config['port'] = 9999  # Unlikely to be used
        config['connect_timeout'] = 2
        if not is_native() and config['host'] == 'localhost':
            self.skipTest("skip test c wrapper and localhost, since using unix socket")
        with self.assertRaises(mariadb.OperationalError):
            mariadb.connect(**config)

    def test_connection_invalid_user(self):
        """Test connection with invalid user"""
        config = get_test_config()
        config['user'] = 'invalid_user_12345'
        config['password'] = 'wrong_password'
        
        with self.assertRaises((mariadb.OperationalError, mariadb.DatabaseError)):
            mariadb.connect(**config)

    def test_connection_invalid_database(self):
        """Test connection with invalid database"""
        config = get_test_config()
        config['database'] = 'invalid_database_12345'
        
        with self.assertRaises(mariadb.ProgrammingError):
            mariadb.connect(**config)

    def test_executemany_empty_list(self):
        """Test executemany with empty list"""
        self.cursor.execute("CREATE TEMPORARY TABLE test_empty_many (id INT)")
        
        # Should not raise error - empty list is valid
        self.cursor.executemany("INSERT INTO test_empty_many VALUES (?)", [])
        self.assertIn(self.cursor.rowcount, [0, -1])

    def test_executemany_invalid_parameters(self):
        """Test executemany with invalid parameter types"""
        self.cursor.execute("CREATE TEMPORARY TABLE test_invalid_params (id INT)")
        
        # None should raise error
        with self.assertRaises(mariadb.ProgrammingError):
            self.cursor.executemany("INSERT INTO test_invalid_params VALUES (?)", None)
        
        # String should raise error (not a valid sequence of sequences)
        with self.assertRaises(mariadb.ProgrammingError):
            self.cursor.executemany("INSERT INTO test_invalid_params VALUES (?)", "invalid")
        
        # Integer should raise error
        with self.assertRaises(mariadb.ProgrammingError):
            self.cursor.executemany("INSERT INTO test_invalid_params VALUES (?)", 123)

    def test_executemany_inconsistent_params(self):
        """Test executemany with inconsistent parameter counts"""
        self.cursor.execute("CREATE TEMPORARY TABLE test_inconsistent (a INT, b INT)")
        
        with self.assertRaises((mariadb.ProgrammingError, TypeError)):
            self.cursor.executemany(
                "INSERT INTO test_inconsistent VALUES (?, ?)",
                [(1, 2), (3,)]  # Second tuple has wrong count
            )

    def test_transaction_deadlock_detection(self):
        """Test transaction behavior (basic)"""
        conn1 = create_connection()
        conn1.autocommit = False
        cursor1 = conn1.cursor()
        
        cursor1.execute("CREATE TEMPORARY TABLE test_trans (id INT PRIMARY KEY, val INT) ENGINE=InnoDB")
        cursor1.execute("INSERT INTO test_trans VALUES (1, 100)")
        conn1.commit()
        
        # Start transaction
        cursor1.execute("UPDATE test_trans SET val = 200 WHERE id = 1")
        
        # Commit
        conn1.commit()
        
        # Verify
        cursor1.execute("SELECT val FROM test_trans WHERE id = 1")
        result = cursor1.fetchone()
        self.assertEqual(result[0], 200)
        
        cursor1.close()
        conn1.close()

    def test_cursor_close_twice(self):
        """Test closing cursor twice"""
        cursor = self.connection.cursor()
        cursor.close()
        
        # Closing again should not raise error
        cursor.close()

    def test_connection_close_twice(self):
        """Test closing connection twice"""
        conn = create_connection()
        conn.close()
        
        # Closing again should not raise error
        conn.close()

    def test_invalid_sql_statement_type(self):
        """Test invalid SQL statement type"""
        with self.assertRaises((TypeError, RuntimeError, mariadb.ProgrammingError)):
            self.cursor.execute(123)  # Not a string
        with self.assertRaises((TypeError, RuntimeError, mariadb.ProgrammingError)):
            self.cursor.executemany(123)  # Not a string

    def test_null_sql_statement(self):
        """Test None as SQL statement"""
        with self.assertRaises((TypeError, mariadb.ProgrammingError)):
            self.cursor.execute(None)

    def test_empty_sql_statement(self):
        """Test empty SQL statement"""
        with self.assertRaises((mariadb.ProgrammingError, ValueError)):
            self.cursor.execute("")

    def test_multiple_statements(self):
        """Test multiple statements in one execute"""
        # Multiple statements should raise error or only execute first
        try:
            self.cursor.execute("SELECT 1; SELECT 2")
            # If it succeeds, verify only first statement executed
            result = self.cursor.fetchone()
            self.assertEqual(result[0], 1)
        except mariadb.ProgrammingError:
            pass  # Expected for some implementations

    def test_special_characters_in_data(self):
        """Test special characters in data"""
        self.cursor.execute("CREATE TEMPORARY TABLE test_special (val VARCHAR(100))")
        
        special_strings = [
            "test'quote",
            'test"doublequote',
            "test\\backslash",
            "test\nnewline",
            "test\ttab",
            "test\x00null",
            "test\r\nwindows",
        ]
        
        for s in special_strings:
            self.cursor.execute("INSERT INTO test_special VALUES (?)", (s,))
        
        self.cursor.execute("SELECT * FROM test_special")
        results = self.cursor.fetchall()
        self.assertEqual(len(results), len(special_strings))

    def test_unicode_data(self):
        """Test Unicode data handling"""
        self.cursor.execute("CREATE TEMPORARY TABLE test_unicode (val VARCHAR(100)) CHARACTER SET utf8mb4")
        
        unicode_strings = [
            "Hello 世界",
            "Привет мир",
            "🔥🌟💻",
            "café",
            "Ñoño",
        ]
        
        for s in unicode_strings:
            self.cursor.execute("INSERT INTO test_unicode VALUES (?)", (s,))
        
        self.cursor.execute("SELECT * FROM test_unicode")
        results = self.cursor.fetchall()
        self.assertEqual(len(results), len(unicode_strings))
        
        # Verify data integrity
        for i, result in enumerate(results):
            self.assertEqual(result[0], unicode_strings[i])

    def test_very_large_result_set(self):
        """Test handling of large result set"""
        self.cursor.execute("CREATE TEMPORARY TABLE test_large (id INT)")
        
        # Insert many rows
        rows = [(i,) for i in range(1000)]
        self.cursor.executemany("INSERT INTO test_large VALUES (?)", rows)
        
        # Fetch all
        self.cursor.execute("SELECT * FROM test_large")
        results = self.cursor.fetchall()
        self.assertEqual(len(results), 1000)

    def test_cursor_description_before_execute(self):
        """Test cursor description before execute"""
        cursor = self.connection.cursor()
        
        # Description should be None before execute
        self.assertIsNone(cursor.description)
        
        cursor.close()

    def test_rowcount_before_execute(self):
        """Test rowcount before execute"""
        cursor = self.connection.cursor()
        
        # Rowcount should be -1 before execute
        self.assertEqual(cursor.rowcount, -1)
        
        cursor.close()

    def test_lastrowid_without_autoincrement(self):
        """Test lastrowid without auto_increment"""
        self.cursor.execute("CREATE TEMPORARY TABLE test_no_auto (id INT)")
        self.cursor.execute("INSERT INTO test_no_auto VALUES (100)")
        
        # lastrowid should be 0 or None without auto_increment
        last_id = self.cursor.lastrowid
        self.assertIn(last_id, [0, None])


if __name__ == '__main__':
    unittest.main()
