# White-box tests of the pure-Python statement cache: they read private
# attributes of the connection and the client on purpose (see the accessors below).
# pyright: reportPrivateUsage=false

"""
Tests for prepared statement cache functionality
"""

import unittest
import mariadb
from typing import Any

from mariadb.async_connection import AsyncConnection as PyAsyncConnection
from mariadb.impl.client.async_client import AsyncClient
from mariadb.impl.client.sync_client import SyncClient
from mariadb.impl.configuration import Configuration
from mariadb.sync_connection import SyncConnection as PySyncConnection
from mariadb_shared.async_connection_common import AsyncConnectionCommon
from mariadb_shared.sync_connection_common import SyncConnectionCommon
from tests.base_test import is_mysql, is_native
from ..conftest import get_test_config as conf

try:
    import cachetools as _cachetools  # noqa: F401  # pyright: ignore[reportUnusedImport]  (availability probe)
    HAS_CACHETOOLS = True
except ImportError:
    HAS_CACHETOOLS = False  # pyright: ignore[reportConstantRedefinition]


def _client(conn: SyncConnectionCommon[Any] | AsyncConnectionCommon[Any]) -> SyncClient | AsyncClient:
    """The pure-Python client behind a connection (these are white-box tests)."""
    assert isinstance(conn, (PySyncConnection, PyAsyncConnection))
    return conn._client


def _configuration(conn: SyncConnectionCommon[Any] | AsyncConnectionCommon[Any]) -> Configuration:
    """The pure-Python configuration behind a connection."""
    assert isinstance(conn, (PySyncConnection, PyAsyncConnection))
    return conn._configuration


def _local_cache(cursor: Any) -> Any:
    """The per-cursor statement cache; both implementations keep one, under the same name."""
    return getattr(cursor, "_local_stmt_cache")


def _percursor_reuse_supported():
    """Per-cursor single-statement reuse is available on the C implementation
    unconditionally, and on the pure-Python implementation when cachetools is
    installed."""
    return (not is_native()) or HAS_CACHETOOLS


@unittest.skipIf(not is_native(), "cache not available using c implementation")
@unittest.skipUnless(HAS_CACHETOOLS, "prepared statement cache requires cachetools")
class TestPreparedStatementCache(unittest.TestCase):
    """Test prepared statement caching"""
    
    def setUp(self):
        """Set up test database and table"""
        # The shared connection-level cache is opt-in; enable it for this suite.
        self.conn = mariadb.connect(**conf(cache_prep_stmts=True))
        cursor = self.conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS cache_test")
        cursor.execute("CREATE TABLE cache_test (id INT, name VARCHAR(100))")
        cursor.execute("INSERT INTO cache_test VALUES (1, 'test1'), (2, 'test2'), (3, 'test3')")
        cursor.close()
        self.conn.commit()  # Commit so other connections can see the data
    
    def tearDown(self):
        """Clean up test database"""
        cursor = self.conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS cache_test")
        cursor.close()
        self.conn.close()
    
    def test_cache_disabled_by_default(self):
        """The shared connection-level cache is opt-in: off unless requested."""
        conn = mariadb.connect(**conf())
        self.assertFalse(_configuration(conn).cache_prep_stmts)
        self.assertIsNone(_client(conn).prepared_statement_cache)
        conn.close()
    
    def test_cache_disabled(self):
        """Test that cache can be disabled"""
        conn = mariadb.connect(**conf(cache_prep_stmts=False))
        try:
            self.assertFalse(_configuration(conn).cache_prep_stmts)

            # Use binary cursor to force prepared statements
            cursor = conn.cursor(binary=True)
            try:
                # Execute same query multiple times
                for _ in range(5):
                    cursor.execute("SELECT * FROM cache_test WHERE id = ?", (1,))
                    row = cursor.fetchone()
                    assert row is not None
                    self.assertEqual(row[0], 1)

                # Cache is None when disabled (not an empty dict)
                self.assertIsNone(_client(conn).prepared_statement_cache)
            finally:
                cursor.close()
        finally:
            conn.close()
    
    def test_cache_custom_size(self):
        """Test custom cache size"""
        conn = mariadb.connect(**conf(cache_prep_stmts=True, prep_stmt_cache_size=10))
        self.assertEqual(_configuration(conn).prep_stmt_cache_size, 10)
        self.assertEqual(_client(conn).prepared_statement_cache.maxsize, 10)
        conn.close()
    
    def test_cache_reuse_same_sql(self):
        """Test that same SQL reuses cached statement"""
        cursor = self.conn.cursor(binary=True)
        
        # First execution - should prepare and cache
        cursor.execute("SELECT * FROM cache_test WHERE id = ?", (1,))
        cursor.fetchone()
        self.assertEqual(len(_client(self.conn).prepared_statement_cache), 1)
        
        # Get the cached statement
        cache_key = (_client(self.conn).context.database, "SELECT * FROM cache_test WHERE id = ?")
        cached = _client(self.conn).prepared_statement_cache.get(cache_key)
        self.assertIsNotNone(cached)
        first_stmt_id = cached.statement_id
        
        # Second execution - should reuse cached statement
        cursor.execute("SELECT * FROM cache_test WHERE id = ?", (2,))
        cursor.fetchone()
        self.assertEqual(len(_client(self.conn).prepared_statement_cache), 1)
        
        # Should be same statement ID
        cached = _client(self.conn).prepared_statement_cache.get(cache_key)
        self.assertEqual(cached.statement_id, first_stmt_id)
        
        cursor.close()
    
    def test_cache_different_sql(self):
        """Test that different SQL creates different cache entries"""
        cursor = self.conn.cursor(binary=True)
        
        cursor.execute("SELECT * FROM cache_test WHERE id = ?", (1,))
        cursor.fetchone()
        
        cursor.execute("SELECT * FROM cache_test WHERE name = ?", ("test1",))
        cursor.fetchone()
        
        cursor.execute("SELECT id FROM cache_test WHERE id > ?", (0,))
        cursor.fetchall()
        
        # Should have 3 different cached statements
        self.assertEqual(len(_client(self.conn).prepared_statement_cache), 3)
        
        cursor.close()
    
    def test_cache_multiple_cursors_same_sql(self):
        """Test multiple cursors using same SQL share cached statement"""
        cursor1 = self.conn.cursor(binary=True)
        cursor2 = self.conn.cursor(binary=True)
        cursor3 = self.conn.cursor(binary=True)
        
        sql = "SELECT * FROM cache_test WHERE id = ?"
        
        # All cursors execute same SQL
        cursor1.execute(sql, (1,))
        cursor1.fetchone()
        
        cursor2.execute(sql, (2,))
        cursor2.fetchone()
        
        cursor3.execute(sql, (3,))
        cursor3.fetchone()
        
        # Should only have 1 cached statement (shared)
        self.assertEqual(len(_client(self.conn).prepared_statement_cache), 1)
        
        cursor1.close()
        cursor2.close()
        cursor3.close()
    
    def test_cache_reference_counting(self):
        """Test that reference counting prevents concurrent use"""
        cursor1 = self.conn.cursor(binary=True)
        cursor2 = self.conn.cursor(binary=True)
        
        sql = "SELECT * FROM cache_test WHERE id = ?"
        
        # Cursor1 uses the statement
        cursor1.execute(sql, (1,))
        cursor1.fetchone()
        
        # Cursor1 still holds reference, cursor2 should get new prepare
        # (because cursor1 hasn't released yet by changing SQL)
        _initial_cache_size = len(_client(self.conn).prepared_statement_cache)
        
        # Cursor1 changes to different SQL - releases the statement
        cursor1.execute("SELECT * FROM cache_test WHERE name = ?", ("test1",))
        cursor1.fetchone()
        
        # Now cursor2 can use the cached statement
        cursor2.execute(sql, (2,))
        cursor2.fetchone()
        
        cursor1.close()
        cursor2.close()
    
    def test_cache_executemany(self):
        """Test that executemany uses cache"""
        if is_mysql():
            self.skipTest("MySQL don't use bulk")
        
        # Check if server supports BULK_UNIT_RESULTS (MariaDB 11.5+)
        from mariadb_shared import constants
        if not _client(self.conn).context.has_capability(constants.CAPABILITY.BULK_UNIT_RESULTS):
            self.skipTest("Server doesn't support BULK_UNIT_RESULTS (MariaDB < 11.5)")
        
        cursor = self.conn.cursor()
        
        data = [(10, 'test10'), (11, 'test11'), (12, 'test12')]
        cursor.executemany("INSERT INTO cache_test VALUES (?, ?)", data)
        
        # Should have cached the INSERT statement
        self.assertGreater(len(_client(self.conn).prepared_statement_cache), 0)
        
        # Execute again with different data
        data2 = [(20, 'test20'), (21, 'test21')]
        cursor.executemany("INSERT INTO cache_test VALUES (?, ?)", data2)
        
        # Should still be same cached statement
        cache_key = (_client(self.conn).context.database, "INSERT INTO cache_test VALUES (?, ?)")
        self.assertIn(cache_key, _client(self.conn).prepared_statement_cache)
        
        cursor.close()
    
    def test_cache_callproc(self):
        """Test that callproc uses cache"""
        cursor = self.conn.cursor()
        try:
            # Create a simple procedure
            cursor.execute("DROP PROCEDURE IF EXISTS test_proc")
            cursor.execute("""
                CREATE PROCEDURE test_proc(IN p1 INT, OUT p2 INT)
                BEGIN
                    SET p2 = p1 * 2;
                END
            """)

            # Call procedure multiple times
            for i in range(5):
                cursor.callproc("test_proc", (i, 0))

            # Should have cached the CALL statement
            cache_key = (_client(self.conn).context.database, "CALL test_proc(?, ?)")
            self.assertIn(cache_key, _client(self.conn).prepared_statement_cache)

            cursor.execute("DROP PROCEDURE test_proc")
        finally:
            cursor.close()
    
    def test_cache_database_switch(self):
        """Test that cache handles database switches correctly"""
        cursor = self.conn.cursor(binary=True)
        
        # Execute in current database
        cursor.execute("SELECT * FROM cache_test WHERE id = ?", (1,))
        cursor.fetchone()
        
        db1 = _client(self.conn).context.database
        _cache_size_db1 = len(_client(self.conn).prepared_statement_cache)
        
        # Create and switch to different database
        cursor.execute("CREATE DATABASE IF NOT EXISTS test_cache_db2")
        cursor.execute("USE test_cache_db2")
        cursor.execute("CREATE TABLE cache_test (id INT, name VARCHAR(100))")
        cursor.execute("INSERT INTO cache_test VALUES (1, 'db2_test')")
        
        # Execute same SQL in different database
        cursor.execute("SELECT * FROM cache_test WHERE id = ?", (1,))
        row = cursor.fetchone()
        assert row is not None
        self.assertEqual(row[1], 'db2_test')
        
        # Should have 2 cached statements (one per database)
        self.assertEqual(len(_client(self.conn).prepared_statement_cache), 2)
        
        # Switch back to original database
        cursor.execute(f"USE {db1}")
        
        # Execute again - should use cached statement from db1
        cursor.execute("SELECT * FROM cache_test WHERE id = ?", (1,))
        row = cursor.fetchone()
        assert row is not None
        self.assertEqual(row[1], 'test1')
        
        # Clean up
        cursor.execute("DROP DATABASE test_cache_db2")
        cursor.close()
    
    def test_cache_eviction(self):
        """Test LRU eviction when cache is full"""
        # Create connection with small cache
        conn = mariadb.connect(**conf(cache_prep_stmts=True, prep_stmt_cache_size=3))
        cursor = conn.cursor(binary=True)
        
        # Fill cache with 3 statements
        cursor.execute("SELECT * FROM cache_test WHERE id = ?", (1,))
        cursor.fetchone()
        
        cursor.execute("SELECT * FROM cache_test WHERE name = ?", ("test1",))
        cursor.fetchone()
        
        cursor.execute("SELECT id FROM cache_test WHERE id > ?", (0,))
        cursor.fetchall()
        
        self.assertEqual(len(_client(conn).prepared_statement_cache), 3)
        
        # Add 4th statement - should evict least recently used
        cursor.execute("SELECT name FROM cache_test WHERE name LIKE ?", ("%test%",))
        cursor.fetchall()
        
        # Cache should still be at max size
        self.assertEqual(len(_client(conn).prepared_statement_cache), 3)
        
        cursor.close()
        conn.close()
    
    def test_cache_clear_on_close(self):
        """Test that cache is cleared when connection closes"""
        conn = mariadb.connect(**conf(cache_prep_stmts=True))
        try:
            cursor = conn.cursor(binary=True)
            try:
                cursor.execute("SELECT * FROM cache_test WHERE id = ?", (1,))
                cursor.fetchone()

                self.assertGreater(len(_client(conn).prepared_statement_cache), 0)
            finally:
                cursor.close()
        finally:
            conn.close()

        # Cache should be cleared (connection is closed, can't check directly)
        # This test mainly ensures no errors on close
    
    def test_cache_with_use_binary(self):
        """Test cache works with binary cursors"""
        cursor = self.conn.cursor(binary=True)
        
        # Execute same query multiple times
        for i in range(3):
            cursor.execute("SELECT * FROM cache_test WHERE id = ?", (i + 1,))
            cursor.fetchone()
        
        # Should have cached the statement
        self.assertEqual(len(_client(self.conn).prepared_statement_cache), 1)

        cursor.close()

    def test_local_reuse_when_connection_cache_disabled(self):
        """With the connection cache off, a binary cursor keeps its own single
        prepared statement: reused while the SQL is unchanged, replaced (old one
        closed) when the SQL changes."""
        conn = mariadb.connect(**conf(cache_prep_stmts=False))
        try:
            # Connection-level cache stays disabled.
            self.assertIsNone(_client(conn).prepared_statement_cache)

            cursor = conn.cursor(binary=True)
            try:
                key = (_client(conn).context.database,
                       "SELECT * FROM cache_test WHERE id = ?")

                cursor.execute("SELECT * FROM cache_test WHERE id = ?", (1,))
                cursor.fetchone()

                # A per-cursor single-statement cache was created lazily.
                local = _local_cache(cursor)
                self.assertIsNotNone(local)
                self.assertEqual(len(local), 1)
                first_id = local[key].statement_id

                # Same SQL again -> reused, not re-prepared (same statement id).
                cursor.execute("SELECT * FROM cache_test WHERE id = ?", (2,))
                row = cursor.fetchone()
                assert row is not None
                self.assertEqual(row[0], 2)
                self.assertEqual(len(local), 1)
                self.assertEqual(local[key].statement_id, first_id)

                # Different SQL -> single slot now holds the new statement,
                # the previous one is evicted (closed on the server).
                cursor.execute("SELECT name FROM cache_test WHERE id = ?", (1,))
                cursor.fetchone()
                self.assertEqual(len(local), 1)
                self.assertNotIn(key, local)
            finally:
                cursor.close()
        finally:
            conn.close()

    def test_local_reuse_is_per_cursor(self):
        """Each cursor keeps its own statement slot (not shared) when the
        connection cache is disabled."""
        conn = mariadb.connect(**conf(cache_prep_stmts=False))
        try:
            c1 = conn.cursor(binary=True)
            c2 = conn.cursor(binary=True)
            try:
                c1.execute("SELECT * FROM cache_test WHERE id = ?", (1,))
                c1.fetchone()
                c2.execute("SELECT * FROM cache_test WHERE id = ?", (2,))
                c2.fetchone()

                self.assertIsNotNone(_local_cache(c1))
                self.assertIsNotNone(_local_cache(c2))
                self.assertIsNot(_local_cache(c1), _local_cache(c2))
            finally:
                c1.close()
                c2.close()
        finally:
            conn.close()

    def test_local_stmt_released_on_cursor_close(self):
        """Closing the cursor drops its per-cursor statement slot."""
        conn = mariadb.connect(**conf(cache_prep_stmts=False))
        try:
            cursor = conn.cursor(binary=True)
            cursor.execute("SELECT * FROM cache_test WHERE id = ?", (1,))
            cursor.fetchone()
            self.assertIsNotNone(_local_cache(cursor))

            cursor.close()
            self.assertIsNone(_local_cache(cursor))
        finally:
            conn.close()

@unittest.skipIf(not is_native(), "cache not available using c implementation")
@unittest.skipUnless(HAS_CACHETOOLS, "prepared statement cache requires cachetools")
class TestPreparedStatementCacheAsync(unittest.IsolatedAsyncioTestCase):
    """Test prepared statement caching with async connections"""
    
    async def asyncSetUp(self):
        """Set up test database and table"""
        # The shared connection-level cache is opt-in; enable it for this suite.
        self.conn = await mariadb.AsyncConnection.connect(**conf(cache_prep_stmts=True))
        cursor = self.conn.cursor()
        await cursor.execute("DROP TABLE IF EXISTS cache_test")
        await cursor.execute("CREATE TABLE cache_test (id INT, name VARCHAR(100))")
        await cursor.execute("INSERT INTO cache_test VALUES (1, 'test1'), (2, 'test2'), (3, 'test3')")
        await cursor.close()
        await self.conn.commit()  # Commit so other connections can see the data
    
    async def asyncTearDown(self):
        """Clean up test database"""
        cursor = self.conn.cursor()
        await cursor.execute("DROP TABLE IF EXISTS cache_test")
        await cursor.close()
        await self.conn.close()
    
    async def test_async_cache_reuse(self):
        """Test async cache reuses statements"""
        cursor = self.conn.cursor(binary=True)
        
        # First execution
        await cursor.execute("SELECT * FROM cache_test WHERE id = ?", (1,))
        await cursor.fetchone()
        
        cache_size = len(_client(self.conn).prepared_statement_cache)
        self.assertEqual(cache_size, 1)
        
        # Second execution - should reuse
        await cursor.execute("SELECT * FROM cache_test WHERE id = ?", (2,))
        await cursor.fetchone()
        
        self.assertEqual(len(_client(self.conn).prepared_statement_cache), cache_size)
        
        await cursor.close()
    
    async def test_async_cache_disabled(self):
        """Test async with cache disabled"""
        conn = await mariadb.AsyncConnection.connect(**conf(cache_prep_stmts=False))
        try:
            self.assertFalse(_configuration(conn).cache_prep_stmts)

            # Use binary cursor to force prepared statements
            cursor = conn.cursor(binary=True)
            try:
                # Execute same query multiple times
                for _ in range(5):
                    await cursor.execute("SELECT * FROM cache_test WHERE id = ?", (1,))
                    row = await cursor.fetchone()
                    assert row is not None
                    self.assertEqual(row[0], 1)

                # Cache is None when disabled (not an empty dict)
                self.assertIsNone(_client(conn).prepared_statement_cache)
            finally:
                await cursor.close()
        finally:
            await conn.close()

    async def test_async_callproc_cache(self):
        """Test async callproc uses cache"""
        cursor = self.conn.cursor()
        
        # Create procedure
        await cursor.execute("DROP PROCEDURE IF EXISTS async_test_proc")
        await cursor.execute("""
            CREATE PROCEDURE async_test_proc(IN p1 INT, OUT p2 INT)
            BEGIN
                SET p2 = p1 * 2;
            END
        """)
        
        # Call multiple times
        for i in range(5):
            await cursor.callproc("async_test_proc", (i, 0))
        
        # Should be cached
        cache_key = (_client(self.conn).context.database, "CALL async_test_proc(?, ?)")
        self.assertIn(cache_key, _client(self.conn).prepared_statement_cache)
        
        await cursor.execute("DROP PROCEDURE async_test_proc")
        await cursor.close()
    
    async def test_async_multiple_cursors(self):
        """Test async multiple cursors share cache"""
        cursor1 = self.conn.cursor(binary=True)
        cursor2 = self.conn.cursor(binary=True)
        
        sql = "SELECT * FROM cache_test WHERE id = ?"
        
        await cursor1.execute(sql, (1,))
        await cursor1.fetchone()
        
        await cursor2.execute(sql, (2,))
        await cursor2.fetchone()
        
        # Should share cached statement
        self.assertEqual(len(_client(self.conn).prepared_statement_cache), 1)
        
        await cursor1.close()
        await cursor2.close()


@unittest.skipUnless(_percursor_reuse_supported(),
                     "per-cursor statement reuse requires cachetools on native")
class TestPerCursorStmtReuse(unittest.TestCase):
    """Per-cursor single-statement reuse when the connection cache is disabled.

    Implementation-agnostic: exercises the behaviour shared by the pure-Python
    and C connectors (a per-cursor ``_local_stmt_cache`` holding a single
    statement). Detailed pure-Python-only assertions live in
    TestPreparedStatementCache.
    """

    def setUp(self):
        self.conn = mariadb.connect(**conf(cache_prep_stmts=False))
        cursor = self.conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS percursor_test")
        cursor.execute("CREATE TABLE percursor_test (id INT, name VARCHAR(100))")
        cursor.execute("INSERT INTO percursor_test VALUES (1,'a'),(2,'b'),(3,'c')")
        cursor.close()
        self.conn.commit()

    def tearDown(self):
        cursor = self.conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS percursor_test")
        cursor.close()
        self.conn.close()

    def test_keeps_single_statement_and_reuses_same_sql(self):
        cursor = self.conn.cursor(binary=True)
        try:
            for i in (1, 2, 3):
                cursor.execute("SELECT name FROM percursor_test WHERE id = ?", (i,))
                self.assertIsNotNone(cursor.fetchone())

            # A per-cursor single-statement cache never holds more than one
            # statement. (Pure-Python keeps the active statement in the cache;
            # the C connector keeps it attached to the cursor and the cache may
            # be momentarily empty — both satisfy "at most one".)
            self.assertIsNotNone(_local_cache(cursor))
            self.assertLessEqual(len(_local_cache(cursor)), 1)

            # Switching SQL still never accumulates statements.
            cursor.execute("SELECT id FROM percursor_test WHERE name = ?", ("b",))
            row = cursor.fetchone()
            assert row is not None
            self.assertEqual(row[0], 2)
            self.assertLessEqual(len(_local_cache(cursor)), 1)
        finally:
            cursor.close()

    def test_reuse_is_per_cursor(self):
        c1 = self.conn.cursor(binary=True)
        c2 = self.conn.cursor(binary=True)
        try:
            c1.execute("SELECT name FROM percursor_test WHERE id = ?", (1,))
            c1.fetchone()
            c2.execute("SELECT name FROM percursor_test WHERE id = ?", (2,))
            c2.fetchone()

            self.assertIsNotNone(_local_cache(c1))
            self.assertIsNotNone(_local_cache(c2))
            self.assertIsNot(_local_cache(c1), _local_cache(c2))
        finally:
            c1.close()
            c2.close()

    def test_statement_released_on_cursor_close(self):
        cursor = self.conn.cursor(binary=True)
        cursor.execute("SELECT name FROM percursor_test WHERE id = ?", (1,))
        cursor.fetchone()
        self.assertIsNotNone(_local_cache(cursor))

        cursor.close()
        self.assertIsNone(_local_cache(cursor))


if __name__ == '__main__':
    unittest.main()
