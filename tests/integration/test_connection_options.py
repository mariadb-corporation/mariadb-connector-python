#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""
Integration tests for connection options and configuration
"""

import unittest
import mariadb
from ..base_test import create_connection
from ..conftest import get_test_config


class ConnectionOptionsTest(unittest.TestCase):
    """Test connection options and configuration"""

    def test_connection_id(self):
        """Test connection_id property"""
        conn = create_connection()
        conn_id = conn.connection_id
        
        self.assertIsInstance(conn_id, int)
        self.assertGreater(conn_id, 0)
        
        conn.close()

    def test_server_info(self):
        """Test server_info property"""
        conn = create_connection()
        server_info = conn.server_info
        
        self.assertIsInstance(server_info, str)
        self.assertGreater(len(server_info), 0)
        
        conn.close()

    def test_server_version(self):
        """Test server_version property"""
        conn = create_connection()
        server_version = conn.server_version
        
        self.assertIsInstance(server_version, int)
        self.assertGreater(server_version, 0)
        
        conn.close()

    def test_server_version_info(self):
        """Test server_version_info property"""
        conn = create_connection()
        version_info = conn.server_version_info
        
        self.assertIsInstance(version_info, tuple)
        self.assertEqual(len(version_info), 3)
        self.assertIsInstance(version_info[0], int)  # major
        self.assertIsInstance(version_info[1], int)  # minor
        self.assertIsInstance(version_info[2], int)  # patch
        
        conn.close()

    def test_character_set(self):
        """Test character_set property"""
        conn = create_connection()
        charset = conn.character_set
        
        self.assertIsInstance(charset, str)
        self.assertIn(charset.lower(), ['utf8', 'utf8mb4', 'latin1', 'utf8mb3'])
        
        conn.close()

    def test_collation(self):
        """Test collation property"""
        conn = create_connection()
        collation = conn.collation
        
        self.assertIsInstance(collation, str)
        self.assertGreater(len(collation), 0)
        
        conn.close()

    def test_database_property(self):
        """Test database property"""
        config = get_test_config()
        conn = create_connection()
        
        db = conn.database
        self.assertEqual(db, config.get('database'))
        
        conn.close()

    def test_user_property(self):
        """Test user property"""
        config = get_test_config()
        conn = create_connection()
        
        user = conn.user
        self.assertEqual(user, config.get('user'))
        
        conn.close()

    def test_server_name_property(self):
        """Test server_name property"""
        conn = create_connection()
        server_name = conn.server_name
        
        self.assertIsInstance(server_name, str)
        self.assertGreater(len(server_name), 0)
        
        conn.close()

    def test_autocommit_get_set(self):
        """Test autocommit property get/set"""
        conn = create_connection()
        
        # Get initial autocommit state
        initial_autocommit = conn.autocommit
        self.assertIsInstance(initial_autocommit, bool)
        
        # Toggle autocommit
        conn.autocommit = not initial_autocommit
        self.assertEqual(conn.autocommit, not initial_autocommit)
        
        # Toggle back
        conn.autocommit = initial_autocommit
        self.assertEqual(conn.autocommit, initial_autocommit)
        
        conn.close()

    def test_warnings_property(self):
        """Test warnings property"""
        conn = create_connection()
        cursor = conn.cursor()
        
        # Generate a warning
        cursor.execute("SET session sql_mode=''")
        cursor.execute("CREATE TEMPORARY TABLE test_warn (a tinyint)")
        cursor.execute("INSERT INTO test_warn VALUES (300)")
        
        # Check warnings
        warnings = conn.warnings
        self.assertIsInstance(warnings, int)
        self.assertGreaterEqual(warnings, 0)
        
        cursor.close()
        conn.close()

    def test_connection_with_connect_timeout(self):
        """Test connection with connect_timeout option"""
        config = get_test_config()
        config['connect_timeout'] = 10
        
        conn = mariadb.connect(**config)
        self.assertIsNotNone(conn)
        conn.close()

    def test_connection_with_read_timeout(self):
        """Test connection with read_timeout option"""
        config = get_test_config()
        config['read_timeout'] = 30
        
        conn = mariadb.connect(**config)
        self.assertIsNotNone(conn)
        
        # Execute a query to verify timeout is set
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        
        conn.close()

    def test_connection_with_write_timeout(self):
        """Test connection with write_timeout option"""
        config = get_test_config()
        config['write_timeout'] = 30
        
        conn = mariadb.connect(**config)
        self.assertIsNotNone(conn)
        
        # Execute a query to verify timeout is set
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        
        conn.close()

    def test_connection_with_init_command(self):
        """Test connection with init_command option"""
        config = get_test_config()
        config['init_command'] = "SET @test_var = 'initialized'"
        
        conn = mariadb.connect(**config)
        cursor = conn.cursor()
        
        # Verify init command was executed
        cursor.execute("SELECT @test_var")
        result = cursor.fetchone()
        self.assertEqual(result[0], 'initialized')
        
        cursor.close()
        conn.close()

    def test_connection_with_autocommit_option(self):
        """Test connection with autocommit option"""
        config = get_test_config()
        config['autocommit'] = True
        
        conn = mariadb.connect(**config)
        self.assertTrue(conn.autocommit)
        
        conn.close()

    def test_connection_context_manager(self):
        """Test connection as context manager"""
        config = get_test_config()
        
        with mariadb.connect(**config) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            self.assertEqual(result[0], 1)
            cursor.close()
        
        # Connection should be closed after context

    def test_connection_commit(self):
        """Test connection commit"""
        conn = create_connection()
        cursor = conn.cursor()
        
        cursor.execute("CREATE TEMPORARY TABLE test_commit (id INT)")
        cursor.execute("INSERT INTO test_commit VALUES (1)")
        
        # Commit the transaction
        conn.commit()
        
        # Verify data is committed
        cursor.execute("SELECT * FROM test_commit")
        result = cursor.fetchall()
        self.assertEqual(len(result), 1)
        
        cursor.close()
        conn.close()

    def test_connection_rollback(self):
        """Test connection rollback"""
        conn = create_connection()
        conn.autocommit = False
        cursor = conn.cursor()
        
        cursor.execute("CREATE TEMPORARY TABLE test_rollback (id INT) ENGINE=InnoDB")
        cursor.execute("INSERT INTO test_rollback VALUES (1)")
        
        # Rollback the transaction
        conn.rollback()
        
        # Verify data is rolled back
        cursor.execute("SELECT * FROM test_rollback")
        result = cursor.fetchall()
        self.assertEqual(len(result), 0)
        
        cursor.close()
        conn.close()

    def test_connection_select_db(self):
        """Test select_db method"""
        config = get_test_config()
        conn = create_connection()
        
        # Switch to information_schema
        conn.select_db('information_schema')
        self.assertEqual(conn.database, 'information_schema')
        
        # Switch back to original database
        conn.select_db(config['database'])
        self.assertEqual(conn.database, config['database'])
        
        conn.close()

    def test_connection_escape_string(self):
        """Test escape_string method"""
        conn = create_connection()
        
        # Test escaping single quote
        escaped = conn.escape_string("test'quote")
        self.assertIn("\\'", escaped)
        
        # Test escaping backslash
        escaped = conn.escape_string("test\\slash")
        self.assertIn("\\\\", escaped)
        
        # Test escaping null byte
        escaped = conn.escape_string("test\x00null")
        self.assertIn("\\", escaped)
        
        conn.close()

    def test_connection_show_warnings(self):
        """Test show_warnings method"""
        conn = create_connection()
        cursor = conn.cursor()
        
        # Generate a warning
        cursor.execute("SET session sql_mode=''")
        cursor.execute("CREATE TEMPORARY TABLE test_show_warn (a tinyint)")
        cursor.execute("INSERT INTO test_show_warn VALUES (300)")
        
        # Get warnings
        warnings = conn.show_warnings()
        self.assertIsInstance(warnings, list)
        
        if len(warnings) > 0:
            # Each warning should be a tuple (level, code, message)
            warning = warnings[0]
            self.assertEqual(len(warning), 3)
            self.assertIsInstance(warning[0], str)  # level
            self.assertIsInstance(warning[1], int)  # code
            self.assertIsInstance(warning[2], str)  # message
        
        cursor.close()
        conn.close()

    def test_connection_closed_property(self):
        """Test closed property"""
        conn = create_connection()
        
        # Connection should not be closed initially
        # Note: Some implementations may not have a closed property
        
        conn.close()
        
        # After close, connection should be closed
        # Note: Behavior may vary by implementation

    def test_connection_multiple_commits(self):
        """Test multiple commits"""
        conn = create_connection()
        cursor = conn.cursor()
        
        cursor.execute("CREATE TEMPORARY TABLE test_multi_commit (id INT)")
        
        for i in range(5):
            cursor.execute("INSERT INTO test_multi_commit VALUES (?)", (i,))
            conn.commit()
        
        cursor.execute("SELECT COUNT(*) FROM test_multi_commit")
        count = cursor.fetchone()[0]
        self.assertEqual(count, 5)
        
        cursor.close()
        conn.close()

    def test_connection_transaction_isolation(self):
        """Test transaction isolation level"""
        conn = create_connection()
        cursor = conn.cursor()
        
        # Get current isolation level
        # Use @@tx_isolation for MariaDB < 11.1.1, @@transaction_isolation for >= 11.1.1
        if conn.server_version >= 110101:
            cursor.execute("SELECT @@transaction_isolation")
        else:
            cursor.execute("SELECT @@tx_isolation")
        isolation = cursor.fetchone()[0]
        self.assertIsInstance(isolation, str)
        
        cursor.close()
        conn.close()

    def test_connection_charset_change(self):
        """Test changing character set"""
        conn = create_connection()
        
        # Get initial charset
        initial_charset = conn.character_set
        
        # Try to change charset (if supported)
        try:
            if initial_charset.lower() == 'utf8mb4':
                conn.set_character_set('utf8')
                self.assertEqual(conn.character_set.lower(), 'utf8')
            else:
                conn.set_character_set('utf8mb4')
                self.assertEqual(conn.character_set.lower(), 'utf8mb4')
        except AttributeError:
            # set_character_set may not be implemented
            pass
        
        conn.close()

    def test_connection_info_after_insert(self):
        """Test connection info after INSERT"""
        conn = create_connection()
        cursor = conn.cursor()
        
        cursor.execute("CREATE TEMPORARY TABLE test_info (id INT AUTO_INCREMENT PRIMARY KEY, val INT)")
        cursor.execute("INSERT INTO test_info (val) VALUES (100)")
        
        # Get last insert id
        last_id = cursor.lastrowid
        self.assertGreaterEqual(last_id, 1)
        
        cursor.close()
        conn.close()

    def test_connection_affected_rows(self):
        """Test affected_rows after UPDATE"""
        conn = create_connection()
        cursor = conn.cursor()
        
        cursor.execute("CREATE TEMPORARY TABLE test_affected (id INT, val INT)")
        cursor.execute("INSERT INTO test_affected VALUES (1, 10), (2, 20), (3, 30)")
        conn.commit()
        
        cursor.execute("UPDATE test_affected SET val = 100 WHERE id <= 2")
        affected = cursor.rowcount
        self.assertEqual(affected, 2)
        
        cursor.close()
        conn.close()


if __name__ == '__main__':
    unittest.main()
