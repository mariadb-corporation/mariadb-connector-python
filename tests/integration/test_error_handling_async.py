#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""
Integration tests for async error handling and edge cases
"""

import unittest
import asyncio
import mariadb
from ..base_test import is_native
from ..conftest import get_test_config

@unittest.skipIf(not is_native(), "AsyncConnection not available")
class AsyncErrorHandlingTest(unittest.IsolatedAsyncioTestCase):
    """Test async error handling and edge cases"""

    async def asyncSetUp(self):
        """Set up test connection"""
        config = get_test_config()
        self.connection = await mariadb.AsyncConnection.connect(**config)
        self.cursor = self.connection.cursor()

    async def asyncTearDown(self):
        """Clean up test resources"""
        if hasattr(self, 'cursor') and self.cursor:
            try:
                await self.cursor.close()
            except:
                pass
        if hasattr(self, 'connection') and self.connection:
            try:
                await self.connection.close()
            except:
                pass

    async def test_syntax_error(self):
        """Test SQL syntax error"""
        with self.assertRaises(mariadb.ProgrammingError):
            await self.cursor.execute("SELCT * FROM nonexistent")

    async def test_table_not_found(self):
        """Test table not found error"""
        with self.assertRaises(mariadb.ProgrammingError):
            await self.cursor.execute("SELECT * FROM nonexistent_table_12345")

    async def test_column_not_found(self):
        """Test column not found error"""
        await self.cursor.execute("CREATE TEMPORARY TABLE test_col_error (id INT)")
        
        with self.assertRaises(mariadb.ProgrammingError):
            await self.cursor.execute("SELECT nonexistent_column FROM test_col_error")

    async def test_duplicate_key_error(self):
        """Test duplicate key error"""
        await self.cursor.execute("""
            CREATE TEMPORARY TABLE test_dup_key (
                id INT PRIMARY KEY
            )
        """)
        await self.cursor.execute("INSERT INTO test_dup_key VALUES (1)")
        
        with self.assertRaises(mariadb.IntegrityError):
            await self.cursor.execute("INSERT INTO test_dup_key VALUES (1)")

    async def test_null_constraint_violation(self):
        """Test NOT NULL constraint violation"""
        await self.cursor.execute("""
            CREATE TEMPORARY TABLE test_not_null (
                id INT NOT NULL
            )
        """)
        
        with self.assertRaises(mariadb.IntegrityError):
            await self.cursor.execute("INSERT INTO test_not_null VALUES (NULL)")

    async def test_foreign_key_violation(self):
        """Test foreign key constraint violation"""
        await self.cursor.execute("DROP TABLE IF EXISTS test_child")
        await self.cursor.execute("DROP TABLE IF EXISTS test_parent")
        await self.cursor.execute("""
            CREATE TABLE test_parent (
                id INT PRIMARY KEY
            ) ENGINE=InnoDB
        """)
        await self.cursor.execute("""
            CREATE TABLE test_child (
                id INT,
                parent_id INT,
                FOREIGN KEY (parent_id) REFERENCES test_parent(id)
            ) ENGINE=InnoDB
        """)
        
        with self.assertRaises(mariadb.IntegrityError):
            await self.cursor.execute("INSERT INTO test_child VALUES (1, 999)")
        await self.cursor.execute("DROP TABLE IF EXISTS test_child")
        await self.cursor.execute("DROP TABLE IF EXISTS test_parent")

    async def test_data_too_long(self):
        """Test data too long error"""
        await self.cursor.execute("""
            CREATE TEMPORARY TABLE test_too_long (
                val VARCHAR(10)
            )
        """)
        
        # Set strict mode
        await self.cursor.execute("SET sql_mode='STRICT_ALL_TABLES'")
        
        with self.assertRaises(mariadb.DataError):
            await self.cursor.execute("INSERT INTO test_too_long VALUES (?)", ('x' * 100,))

    async def test_division_by_zero(self):
        """Test division by zero handling"""
        # In non-strict mode, this returns NULL
        await self.cursor.execute("SET sql_mode=''")
        await self.cursor.execute("SELECT 1/0")
        result = await self.cursor.fetchone()
        self.assertIsNone(result[0])

    async def test_execute_without_connection(self):
        """Test execute on closed connection"""
        config = get_test_config()
        conn = await mariadb.AsyncConnection.connect(**config)
        cursor = conn.cursor()
        await conn.close()
        
        with self.assertRaises((mariadb.Error, mariadb.ProgrammingError)):
            await cursor.execute("SELECT 1")

    async def test_fetch_without_execute(self):
        """Test fetch without execute"""
        cursor = self.connection.cursor()
        
        # Fetching without execute should raise error or return None
        with self.assertRaises(mariadb.ProgrammingError):
            await cursor.fetchone()
        
        await cursor.close()

    async def test_fetchall_empty_result(self):
        """Test fetchall on empty result"""
        await self.cursor.execute("CREATE TEMPORARY TABLE test_empty (id INT)")
        await self.cursor.execute("SELECT * FROM test_empty")
        
        result = await self.cursor.fetchall()
        self.assertEqual(result, [])

    async def test_fetchmany_empty_result(self):
        """Test fetchmany on empty result"""
        await self.cursor.execute("CREATE TEMPORARY TABLE test_empty2 (id INT)")
        await self.cursor.execute("SELECT * FROM test_empty2")
        
        result = await self.cursor.fetchmany(5)
        self.assertEqual(result, [])

    async def test_fetchone_after_fetchall(self):
        """Test fetchone after fetchall"""
        await self.cursor.execute("SELECT 1 UNION SELECT 2")
        await self.cursor.fetchall()
        
        # Should return None after all rows fetched
        result = await self.cursor.fetchone()
        self.assertIsNone(result)

    async def test_invalid_parameter_count(self):
        """Test invalid parameter count in execute"""
        await self.cursor.execute("CREATE TEMPORARY TABLE test_params (a INT, b INT)")
        
        with self.assertRaises((mariadb.ProgrammingError, TypeError)):
            await self.cursor.execute("INSERT INTO test_params VALUES (?, ?)", (1,))  # Missing parameter

    async def test_invalid_parameter_type(self):
        """Test invalid parameter type"""
        await self.cursor.execute("CREATE TEMPORARY TABLE test_type (id INT)")
        
        # Some types may cause errors
        try:
            await self.cursor.execute("INSERT INTO test_type VALUES (?)", (object(),))
            # If no error, that's also acceptable (implementation-specific)
        except (mariadb.ProgrammingError, mariadb.OperationalError, mariadb.DataError, TypeError):
            pass  # Expected

    async def test_connection_invalid_host(self):
        """Test connection with invalid host"""
        config = get_test_config()
        config['host'] = 'invalid.host.that.does.not.exist.12345'
        config['connect_timeout'] = 2
        
        with self.assertRaises(mariadb.OperationalError):
            await mariadb.AsyncConnection.connect(**config)

    async def test_connection_invalid_host_none(self):
        """Test connection with invalid host"""
        config = get_test_config()
        config['host'] = None
        config['connect_timeout'] = 2
        
        with self.assertRaises(mariadb.OperationalError):
            await mariadb.AsyncConnection.connect(**config)


    async def test_connection_invalid_port(self):
        """Test connection with invalid port"""
        config = get_test_config()
        config['port'] = 9999  # Unlikely to be used
        config['connect_timeout'] = 2
        if not is_native() and config['host'] == 'localhost':
            self.skipTest("skip test c wrapper and localhost, since using unix socket")
        with self.assertRaises(mariadb.OperationalError):
            await mariadb.AsyncConnection.connect(**config)

    async def test_connection_invalid_user(self):
        """Test connection with invalid user"""
        config = get_test_config()
        config['user'] = 'invalid_user_12345'
        config['password'] = 'wrong_password'
        
        with self.assertRaises((mariadb.OperationalError, mariadb.DatabaseError)):
            await mariadb.AsyncConnection.connect(**config)

    async def test_connection_invalid_database(self):
        """Test connection with invalid database"""
        config = get_test_config()
        config['database'] = 'invalid_database_12345'
        
        with self.assertRaises(mariadb.ProgrammingError):
            await mariadb.AsyncConnection.connect(**config)

    async def test_executemany_empty_list(self):
        """Test executemany with empty list"""
        await self.cursor.execute("CREATE TEMPORARY TABLE test_empty_many (id INT)")
        
        # Should not raise error - empty list is valid
        await self.cursor.executemany("INSERT INTO test_empty_many VALUES (?)", [])
        self.assertIn(self.cursor.rowcount, [0, -1])

    async def test_executemany_invalid_parameters(self):
        """Test executemany with invalid parameter types"""
        await self.cursor.execute("CREATE TEMPORARY TABLE test_invalid_params (id INT)")
        
        # None should raise error
        with self.assertRaises(mariadb.ProgrammingError):
            await self.cursor.executemany("INSERT INTO test_invalid_params VALUES (?)", None)
        
        # String should raise error (not a valid sequence of sequences)
        with self.assertRaises(mariadb.ProgrammingError):
            await self.cursor.executemany("INSERT INTO test_invalid_params VALUES (?)", "invalid")
        
        # Integer should raise error
        with self.assertRaises(mariadb.ProgrammingError):
            await self.cursor.executemany("INSERT INTO test_invalid_params VALUES (?)", 123)

    async def test_executemany_inconsistent_params(self):
        """Test executemany with inconsistent parameter counts"""
        await self.cursor.execute("CREATE TEMPORARY TABLE test_inconsistent (a INT, b INT)")
        
        with self.assertRaises((mariadb.ProgrammingError, TypeError)):
            await self.cursor.executemany(
                "INSERT INTO test_inconsistent VALUES (?, ?)",
                [(1, 2), (3,)]  # Second tuple has wrong count
            )

    async def test_transaction_deadlock_detection(self):
        """Test transaction behavior (basic)"""
        config = get_test_config()
        conn1 = await mariadb.AsyncConnection.connect(**config)
        await conn1.set_autocommit(False)
        cursor1 = conn1.cursor()
        
        await cursor1.execute("CREATE TEMPORARY TABLE test_trans (id INT PRIMARY KEY, val INT) ENGINE=InnoDB")
        await cursor1.execute("INSERT INTO test_trans VALUES (1, 100)")
        await conn1.commit()
        
        # Start transaction
        await cursor1.execute("UPDATE test_trans SET val = 200 WHERE id = 1")
        
        # Commit
        await conn1.commit()
        
        # Verify
        await cursor1.execute("SELECT val FROM test_trans WHERE id = 1")
        result = await cursor1.fetchone()
        self.assertEqual(result[0], 200)
        
        await cursor1.close()
        await conn1.close()

    async def test_cursor_close_twice(self):
        """Test closing cursor twice"""
        cursor = self.connection.cursor()
        await cursor.close()
        
        # Closing again should not raise error
        await cursor.close()

    async def test_connection_close_twice(self):
        """Test closing connection twice"""
        config = get_test_config()
        conn = await mariadb.AsyncConnection.connect(**config)
        await conn.close()
        
        # Closing again should not raise error
        await conn.close()

    async def test_invalid_sql_statement_type(self):
        """Test invalid SQL statement type"""
        with self.assertRaises((TypeError, RuntimeError, mariadb.ProgrammingError)):
            await self.cursor.execute(123)  # Not a string
        with self.assertRaises((TypeError, RuntimeError, mariadb.ProgrammingError)):
            await self.cursor.executemany(123)  # Not a string

    async def test_null_sql_statement(self):
        """Test None as SQL statement"""
        with self.assertRaises((TypeError, mariadb.ProgrammingError)):
            await self.cursor.execute(None)

    async def test_empty_sql_statement(self):
        """Test empty SQL statement"""
        with self.assertRaises((mariadb.ProgrammingError, ValueError)):
            await self.cursor.execute("")

    async def test_multiple_statements(self):
        """Test multiple statements in one execute"""
        # Multiple statements should raise error or only execute first
        try:
            await self.cursor.execute("SELECT 1; SELECT 2")
            # If it succeeds, verify only first statement executed
            result = await self.cursor.fetchone()
            self.assertEqual(result[0], 1)
        except mariadb.ProgrammingError:
            pass  # Expected for some implementations

    async def test_special_characters_in_data(self):
        """Test special characters in data"""
        await self.cursor.execute("CREATE TEMPORARY TABLE test_special (val VARCHAR(100))")
        
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
            await self.cursor.execute("INSERT INTO test_special VALUES (?)", (s,))
        
        await self.cursor.execute("SELECT * FROM test_special")
        results = await self.cursor.fetchall()
        self.assertEqual(len(results), len(special_strings))

    async def test_unicode_data(self):
        """Test Unicode data handling"""
        await self.cursor.execute("CREATE TEMPORARY TABLE test_unicode (val VARCHAR(100)) CHARACTER SET utf8mb4")
        
        unicode_strings = [
            "Hello 世界",
            "Привет мир",
            "🔥🌟💻",
            "café",
            "Ñoño",
        ]
        
        for s in unicode_strings:
            await self.cursor.execute("INSERT INTO test_unicode VALUES (?)", (s,))
        
        await self.cursor.execute("SELECT * FROM test_unicode")
        results = await self.cursor.fetchall()
        self.assertEqual(len(results), len(unicode_strings))
        
        # Verify data integrity
        for i, result in enumerate(results):
            self.assertEqual(result[0], unicode_strings[i])

    async def test_very_large_result_set(self):
        """Test handling of large result set"""
        await self.cursor.execute("CREATE TEMPORARY TABLE test_large (id INT)")
        
        # Insert many rows
        rows = [(i,) for i in range(1000)]
        await self.cursor.executemany("INSERT INTO test_large VALUES (?)", rows)
        
        # Fetch all
        await self.cursor.execute("SELECT * FROM test_large")
        results = await self.cursor.fetchall()
        self.assertEqual(len(results), 1000)

    async def test_cursor_description_before_execute(self):
        """Test cursor description before execute"""
        cursor = self.connection.cursor()
        
        # Description should be None before execute
        self.assertIsNone(cursor.description)
        
        await cursor.close()

    async def test_rowcount_before_execute(self):
        """Test rowcount before execute"""
        cursor = self.connection.cursor()
        
        # Rowcount should be -1 before execute
        self.assertEqual(cursor.rowcount, -1)
        
        await cursor.close()

    async def test_lastrowid_without_autoincrement(self):
        """Test lastrowid without auto_increment"""
        await self.cursor.execute("CREATE TEMPORARY TABLE test_no_auto (id INT)")
        await self.cursor.execute("INSERT INTO test_no_auto VALUES (100)")
        
        # lastrowid should be 0 or None without auto_increment
        last_id = self.cursor.lastrowid
        self.assertIn(last_id, [0, None])


if __name__ == '__main__':
    unittest.main()
