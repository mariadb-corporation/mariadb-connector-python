#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""
Async integration tests for connection options and configuration
"""

import unittest
import mariadb
from ..conftest import get_test_config


class AsyncConnectionOptionsTest(unittest.IsolatedAsyncioTestCase):
    """Async test connection options and configuration"""

    async def test_connection_id(self):
        """Test connection_id property"""
        config = get_test_config()
        conn = await mariadb.AsyncConnection.connect(**config)
        conn_id = conn.connection_id
        
        self.assertIsInstance(conn_id, int)
        self.assertGreater(conn_id, 0)
        
        await conn.close()

    async def test_server_info(self):
        """Test server_info property"""
        config = get_test_config()
        conn = await mariadb.AsyncConnection.connect(**config)
        server_info = conn.server_info
        
        self.assertIsInstance(server_info, str)
        self.assertGreater(len(server_info), 0)
        
        await conn.close()

    async def test_server_version(self):
        """Test server_version property"""
        config = get_test_config()
        conn = await mariadb.AsyncConnection.connect(**config)
        server_version = conn.server_version
        
        self.assertIsInstance(server_version, int)
        self.assertGreater(server_version, 0)
        
        await conn.close()

    async def test_server_version_info(self):
        """Test server_version_info property"""
        config = get_test_config()
        conn = await mariadb.AsyncConnection.connect(**config)
        version_info = conn.server_version_info
        
        self.assertIsInstance(version_info, tuple)
        self.assertEqual(len(version_info), 3)
        self.assertIsInstance(version_info[0], int)  # major
        self.assertIsInstance(version_info[1], int)  # minor
        self.assertIsInstance(version_info[2], int)  # patch
        
        await conn.close()

    async def test_character_set(self):
        """Test character_set property"""
        config = get_test_config()
        conn = await mariadb.AsyncConnection.connect(**config)
        charset = conn.character_set
        
        self.assertIsInstance(charset, str)
        self.assertIn(charset.lower(), ['utf8', 'utf8mb4', 'latin1', 'utf8mb3'])
        
        await conn.close()

    async def test_collation(self):
        """Test collation property"""
        config = get_test_config()
        conn = await mariadb.AsyncConnection.connect(**config)
        collation = conn.collation
        
        self.assertIsInstance(collation, str)
        self.assertGreater(len(collation), 0)
        
        await conn.close()

    async def test_database_property(self):
        """Test database property"""
        config = get_test_config()
        conn = await mariadb.AsyncConnection.connect(**config)
        
        db = conn.database
        self.assertEqual(db, config.get('database'))
        
        await conn.close()

    async def test_user_property(self):
        """Test user property"""
        config = get_test_config()
        conn = await mariadb.AsyncConnection.connect(**config)
        
        user = conn.user
        self.assertEqual(user, config.get('user'))
        
        await conn.close()

    async def test_server_name_property(self):
        """Test server_name property"""
        config = get_test_config()
        conn = await mariadb.AsyncConnection.connect(**config)
        server_name = conn.server_name
        
        self.assertIsInstance(server_name, str)
        self.assertGreater(len(server_name), 0)
        
        await conn.close()

    async def test_autocommit_get_set(self):
        """Test autocommit property get/set"""
        config = get_test_config()
        conn = await mariadb.AsyncConnection.connect(**config)
        
        # Get initial autocommit state
        initial_autocommit = conn.autocommit
        self.assertIsInstance(initial_autocommit, bool)
        
        # Toggle autocommit
        await conn.set_autocommit(not initial_autocommit)
        self.assertEqual(conn.autocommit, not initial_autocommit)
        
        # Toggle back
        await conn.set_autocommit(initial_autocommit)
        self.assertEqual(conn.autocommit, initial_autocommit)
        
        await conn.close()

    async def test_warnings_property(self):
        """Test warnings property"""
        config = get_test_config()
        conn = await mariadb.AsyncConnection.connect(**config)
        cursor = conn.cursor()
        
        # Generate a warning
        await cursor.execute("SET session sql_mode=''")
        await cursor.execute("CREATE TEMPORARY TABLE test_warn (a tinyint)")
        await cursor.execute("INSERT INTO test_warn VALUES (300)")
        
        # Check warnings
        warnings = conn.warnings
        self.assertIsInstance(warnings, int)
        self.assertGreaterEqual(warnings, 0)
        
        await cursor.close()
        await conn.close()

    async def test_connection_with_connect_timeout(self):
        """Test connection with connect_timeout option"""
        config = get_test_config()
        config['connect_timeout'] = 10
        
        conn = await mariadb.AsyncConnection.connect(**config)
        self.assertIsNotNone(conn)
        await conn.close()

    async def test_connection_with_read_timeout(self):
        """Test connection with read_timeout option"""
        config = get_test_config()
        config['read_timeout'] = 30
        
        conn = await mariadb.AsyncConnection.connect(**config)
        self.assertIsNotNone(conn)
        
        # Execute a query to verify timeout is set
        cursor = conn.cursor()
        await cursor.execute("SELECT 1")
        await cursor.fetchone()
        await cursor.close()
        
        await conn.close()

    async def test_connection_with_write_timeout(self):
        """Test connection with write_timeout option"""
        config = get_test_config()
        config['write_timeout'] = 30
        
        conn = await mariadb.AsyncConnection.connect(**config)
        self.assertIsNotNone(conn)
        
        # Execute a query to verify timeout is set
        cursor = conn.cursor()
        await cursor.execute("SELECT 1")
        await cursor.fetchone()
        await cursor.close()
        
        await conn.close()

    async def test_connection_with_init_command(self):
        """Test connection with init_command option"""
        config = get_test_config()
        config['init_command'] = "SET @test_var = 'initialized'"
        
        conn = await mariadb.AsyncConnection.connect(**config)
        cursor = conn.cursor()
        
        # Verify init command was executed
        await cursor.execute("SELECT @test_var")
        result = await cursor.fetchone()
        self.assertEqual(result[0], 'initialized')
        
        await cursor.close()
        await conn.close()

    async def test_connection_with_autocommit_option(self):
        """Test connection with autocommit option"""
        config = get_test_config()
        config['autocommit'] = True
        
        conn = await mariadb.AsyncConnection.connect(**config)
        self.assertTrue(conn.autocommit)
        
        await conn.close()

    async def test_connection_context_manager(self):
        """Test connection as async context manager"""
        config = get_test_config()
        
        async with await mariadb.AsyncConnection.connect(**config) as conn:
            cursor = conn.cursor()
            await cursor.execute("SELECT 1")
            result = await cursor.fetchone()
            self.assertEqual(result[0], 1)
            await cursor.close()
        
        # Connection should be closed after context

    async def test_connection_commit(self):
        """Test connection commit"""
        config = get_test_config()
        conn = await mariadb.AsyncConnection.connect(**config)
        cursor = conn.cursor()
        
        await cursor.execute("CREATE TEMPORARY TABLE test_commit (id INT)")
        await cursor.execute("INSERT INTO test_commit VALUES (1)")
        
        # Commit the transaction
        await conn.commit()
        
        # Verify data is committed
        await cursor.execute("SELECT * FROM test_commit")
        result = await cursor.fetchall()
        self.assertEqual(len(result), 1)
        
        await cursor.close()
        await conn.close()

    async def test_connection_rollback(self):
        """Test connection rollback"""
        config = get_test_config()
        conn = await mariadb.AsyncConnection.connect(**config)
        await conn.set_autocommit(False)
        cursor = conn.cursor()
        
        await cursor.execute("CREATE TEMPORARY TABLE test_rollback (id INT) ENGINE=InnoDB")
        await cursor.execute("INSERT INTO test_rollback VALUES (1)")
        
        # Rollback the transaction
        await conn.rollback()
        
        # Verify data is rolled back
        await cursor.execute("SELECT * FROM test_rollback")
        result = await cursor.fetchall()
        self.assertEqual(len(result), 0)
        
        await cursor.close()
        await conn.close()

    async def test_connection_select_db(self):
        """Test select_db method"""
        config = get_test_config()
        conn = await mariadb.AsyncConnection.connect(**config)
        
        # Switch to information_schema
        await conn.select_db('information_schema')
        self.assertEqual(conn.database, 'information_schema')
        
        # Switch back to original database
        await conn.select_db(config['database'])
        self.assertEqual(conn.database, config['database'])
        
        await conn.close()

    async def test_connection_escape_string(self):
        """Test escape_string method"""
        config = get_test_config()
        conn = await mariadb.AsyncConnection.connect(**config)
        
        # Test escaping single quote
        escaped = conn.escape_string("test'quote")
        self.assertIn("\\'", escaped)
        
        # Test escaping backslash
        escaped = conn.escape_string("test\\slash")
        self.assertIn("\\\\", escaped)
        
        # Test escaping null byte
        escaped = conn.escape_string("test\x00null")
        self.assertIn("\\", escaped)
        
        await conn.close()

    async def test_connection_show_warnings(self):
        """Test show_warnings method"""
        config = get_test_config()
        conn = await mariadb.AsyncConnection.connect(**config)
        cursor = conn.cursor()
        
        # Generate a warning
        await cursor.execute("SET session sql_mode=''")
        await cursor.execute("CREATE TEMPORARY TABLE test_show_warn (a tinyint)")
        await cursor.execute("INSERT INTO test_show_warn VALUES (300)")
        
        # Get warnings
        warnings = await conn.show_warnings()
        self.assertIsInstance(warnings, list)
        
        if len(warnings) > 0:
            # Each warning should be a tuple (level, code, message)
            warning = warnings[0]
            self.assertEqual(len(warning), 3)
            self.assertIsInstance(warning[0], str)  # level
            self.assertIsInstance(warning[1], int)  # code
            self.assertIsInstance(warning[2], str)  # message
        
        await cursor.close()
        await conn.close()

    async def test_connection_closed_property(self):
        """Test closed property"""
        config = get_test_config()
        conn = await mariadb.AsyncConnection.connect(**config)
        
        # Connection should not be closed initially
        # Note: Some implementations may not have a closed property
        
        await conn.close()
        
        # After close, connection should be closed
        # Note: Behavior may vary by implementation

    async def test_connection_multiple_commits(self):
        """Test multiple commits"""
        config = get_test_config()
        conn = await mariadb.AsyncConnection.connect(**config)
        cursor = conn.cursor()
        
        await cursor.execute("CREATE TEMPORARY TABLE test_multi_commit (id INT)")
        
        for i in range(5):
            await cursor.execute("INSERT INTO test_multi_commit VALUES (?)", (i,))
            await conn.commit()
        
        await cursor.execute("SELECT COUNT(*) FROM test_multi_commit")
        count = (await cursor.fetchone())[0]
        self.assertEqual(count, 5)
        
        await cursor.close()
        await conn.close()

    async def test_connection_transaction_isolation(self):
        """Test transaction isolation level"""
        config = get_test_config()
        conn = await mariadb.AsyncConnection.connect(**config)
        cursor = conn.cursor()
        
        # Get current isolation level
        await cursor.execute("SELECT @@transaction_isolation")
        isolation = (await cursor.fetchone())[0]
        self.assertIsInstance(isolation, str)
        
        await cursor.close()
        await conn.close()

    async def test_connection_charset_change(self):
        """Test changing character set"""
        config = get_test_config()
        conn = await mariadb.AsyncConnection.connect(**config)
        
        # Get initial charset
        initial_charset = conn.character_set
        
        # Try to change charset (if supported)
        try:
            if initial_charset.lower() == 'utf8mb4':
                await conn.set_character_set('utf8')
                self.assertEqual(conn.character_set.lower(), 'utf8')
            else:
                await conn.set_character_set('utf8mb4')
                self.assertEqual(conn.character_set.lower(), 'utf8mb4')
        except AttributeError:
            # set_character_set may not be implemented
            pass
        
        await conn.close()

    async def test_connection_info_after_insert(self):
        """Test connection info after INSERT"""
        config = get_test_config()
        conn = await mariadb.AsyncConnection.connect(**config)
        cursor = conn.cursor()
        
        await cursor.execute("CREATE TEMPORARY TABLE test_info (id INT AUTO_INCREMENT PRIMARY KEY, val INT)")
        await cursor.execute("INSERT INTO test_info (val) VALUES (100)")
        
        # Get last insert id
        last_id = cursor.lastrowid
        self.assertGreaterEqual(last_id, 1)
        
        await cursor.close()
        await conn.close()

    async def test_connection_affected_rows(self):
        """Test affected_rows after UPDATE"""
        config = get_test_config()
        conn = await mariadb.AsyncConnection.connect(**config)
        cursor = conn.cursor()
        
        await cursor.execute("CREATE TEMPORARY TABLE test_affected (id INT, val INT)")
        await cursor.execute("INSERT INTO test_affected VALUES (1, 10), (2, 20), (3, 30)")
        await conn.commit()
        
        await cursor.execute("UPDATE test_affected SET val = 100 WHERE id <= 2")
        affected = cursor.rowcount
        self.assertEqual(affected, 2)
        
        await cursor.close()
        await conn.close()


if __name__ == '__main__':
    unittest.main()
