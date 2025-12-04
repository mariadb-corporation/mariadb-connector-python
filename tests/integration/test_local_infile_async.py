#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add the mariadb source module to the path BEFORE importing
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import mariadb
from ..base_test import is_native
from ..conftest import get_test_config as conf

def create_async_connection_url():
    """Create connection URL from config"""
    default_conf = conf()
    user = default_conf.get('user', 'root')
    password = default_conf.get('password', '')
    host = default_conf.get('host', 'localhost')
    port = default_conf.get('port', 3306)
    database = default_conf.get('database', 'test')
    return f"mariadb://{user}:{password}@{host}:{port}/{database}?autocommit=True"


@unittest.skipIf(not is_native(), "AsyncConnection not available")
class TestLocalInfileAsync(unittest.IsolatedAsyncioTestCase):
    """Test LOAD DATA LOCAL INFILE functionality (async)"""

    async def asyncSetUp(self):
        """Setup for each test - check if local_infile is enabled"""
        url = create_async_connection_url()
        conn = await mariadb.asyncConnect(url, autocommit=True, local_infile=True)
        cursor = conn.cursor()
        await cursor.execute("SELECT @@local_infile")
        row = await cursor.fetchone()
        self.local_infile_enabled = row[0] == 1 if row else False
        await cursor.close()
        await conn.close()

    @classmethod
    def setUpClass(cls):
        """Create test tables (sync setup)"""
        # Use sync connection for setup
        default_conf = conf()
        default_conf['autocommit'] = True
        conn = mariadb.connect(**default_conf)
        cursor = conn.cursor()
        
        # Drop tables if they exist
        cursor.execute("DROP TABLE IF EXISTS local_infile_test_async")
        cursor.execute("DROP TABLE IF EXISTS local_infile_empty_async")
        cursor.execute("DROP TABLE IF EXISTS local_infile_large_async")
        
        # Create test tables
        cursor.execute("""
            CREATE TABLE local_infile_test_async (
                id INT,
                name VARCHAR(100)
            )
        """)
        cursor.execute("""
            CREATE TABLE local_infile_empty_async (
                id INT,
                name VARCHAR(100)
            )
        """)
        cursor.execute("""
            CREATE TABLE local_infile_large_async (
                a VARCHAR(50),
                b VARCHAR(50)
            )
        """)
        
        conn.commit()
        cursor.close()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        """Drop test tables (sync teardown)"""
        try:
            default_conf = conf()
            default_conf['autocommit'] = True
            conn = mariadb.connect(**default_conf)
            cursor = conn.cursor()
            cursor.execute("DROP TABLE IF EXISTS local_infile_test_async")
            cursor.execute("DROP TABLE IF EXISTS local_infile_empty_async")
            cursor.execute("DROP TABLE IF EXISTS local_infile_large_async")
            cursor.close()
            conn.close()
        except:
            pass

    async def test_load_data_basic_async(self):
        """Test basic LOAD DATA LOCAL INFILE (async)"""
        if not self.local_infile_enabled:
            self.skipTest("local_infile not enabled on server")
        
        # Create temp file with test data
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("1\thello\n")
            f.write("2\tworld\n")
            f.write("3\ttest\n")
            temp_path = f.name
        
        try:
            url = create_async_connection_url()
            conn = await mariadb.asyncConnect(url, autocommit=True, local_infile=True)
            cursor = conn.cursor()
            
            await cursor.execute("TRUNCATE local_infile_test_async")
            
            sql = f"LOAD DATA LOCAL INFILE '{temp_path.replace(chr(92), '/')}' INTO TABLE local_infile_test_async (id, name)"
            await cursor.execute(sql)
            
            await cursor.execute("SELECT * FROM local_infile_test_async ORDER BY id")
            rows = await cursor.fetchall()
            
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0], (1, 'hello'))
            self.assertEqual(rows[1], (2, 'world'))
            self.assertEqual(rows[2], (3, 'test'))
            
            await cursor.close()
            await conn.close()
        finally:
            os.unlink(temp_path)

    async def test_load_data_empty_file_async(self):
        """Test LOAD DATA LOCAL INFILE with empty file (async)"""
        if not self.local_infile_enabled:
            self.skipTest("local_infile not enabled on server")
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            temp_path = f.name
        
        try:
            url = create_async_connection_url()
            conn = await mariadb.asyncConnect(url, autocommit=True, local_infile=True)
            cursor = conn.cursor()
            
            await cursor.execute("TRUNCATE local_infile_empty_async")
            
            sql = f"LOAD DATA LOCAL INFILE '{temp_path.replace(chr(92), '/')}' INTO TABLE local_infile_empty_async (id, name)"
            await cursor.execute(sql)
            
            await cursor.execute("SELECT COUNT(*) FROM local_infile_empty_async")
            count = (await cursor.fetchone())[0]
            self.assertEqual(count, 0)
            
            await cursor.close()
            await conn.close()
        finally:
            os.unlink(temp_path)

    async def test_load_data_file_not_found_async(self):
        """Test LOAD DATA LOCAL INFILE with non-existent file (async)"""
        if not self.local_infile_enabled:
            self.skipTest("local_infile not enabled on server")
        
        url = create_async_connection_url()
        conn = await mariadb.asyncConnect(url, autocommit=True, local_infile=True)
        cursor = conn.cursor()
        
        try:
            sql = "LOAD DATA LOCAL INFILE '/nonexistent/file.txt' INTO TABLE local_infile_test_async (id, name)"
            await cursor.execute(sql)
            self.fail("Should have raised an error for non-existent file")
        except (mariadb.OperationalError, mariadb.InternalError) as e:
            # Should get "Could not send file" or "File not found" error
            self.assertTrue("Could not send file" in str(e) or "not found" in str(e))
        finally:
            # Connection should still be valid
            await cursor.execute("SELECT 1")
            result = await cursor.fetchone()
            self.assertEqual(result[0], 1)
            await cursor.close()
            await conn.close()

    async def test_load_data_large_file_async(self):
        """Test LOAD DATA LOCAL INFILE with larger file (async)"""
        if not self.local_infile_enabled:
            self.skipTest("local_infile not enabled on server")
        
        row_count = 1000
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            for i in range(row_count):
                f.write(f"{i}\trow_{i}\n")
            temp_path = f.name
        
        try:
            url = create_async_connection_url()
            conn = await mariadb.asyncConnect(url, autocommit=True, local_infile=True)
            cursor = conn.cursor()
            
            await cursor.execute("TRUNCATE local_infile_test_async")
            
            sql = f"LOAD DATA LOCAL INFILE '{temp_path.replace(chr(92), '/')}' INTO TABLE local_infile_test_async (id, name)"
            await cursor.execute(sql)
            
            await cursor.execute("SELECT COUNT(*) FROM local_infile_test_async")
            count = (await cursor.fetchone())[0]
            self.assertEqual(count, row_count)
            
            # Verify some rows
            await cursor.execute("SELECT * FROM local_infile_test_async WHERE id IN (0, 500, 999) ORDER BY id")
            rows = await cursor.fetchall()
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0], (0, 'row_0'))
            self.assertEqual(rows[1], (500, 'row_500'))
            self.assertEqual(rows[2], (999, 'row_999'))
            
            await cursor.close()
            await conn.close()
        finally:
            os.unlink(temp_path)

    async def test_load_data_with_custom_delimiters_async(self):
        """Test LOAD DATA LOCAL INFILE with custom delimiters (async)"""
        if not self.local_infile_enabled:
            self.skipTest("local_infile not enabled on server")
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
            f.write('"a","b"\n')
            f.write('"c","d"\n')
            temp_path = f.name
        
        try:
            url = create_async_connection_url()
            conn = await mariadb.asyncConnect(url, autocommit=True, local_infile=True)
            cursor = conn.cursor()
            
            await cursor.execute("TRUNCATE local_infile_large_async")
            
            sql = f"""
                LOAD DATA LOCAL INFILE '{temp_path.replace(chr(92), '/')}'
                INTO TABLE local_infile_large_async
                FIELDS TERMINATED BY ',' ENCLOSED BY '"'
                LINES TERMINATED BY '\\n'
                (a, b)
            """
            await cursor.execute(sql)
            
            await cursor.execute("SELECT * FROM local_infile_large_async ORDER BY a")
            rows = await cursor.fetchall()
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0], ('a', 'b'))
            self.assertEqual(rows[1], ('c', 'd'))
            
            await cursor.close()
            await conn.close()
        finally:
            os.unlink(temp_path)

    async def test_load_xml_local_infile_async(self):
        """Test LOAD XML LOCAL INFILE (async)"""
        if not self.local_infile_enabled:
            self.skipTest("local_infile not enabled on server")
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.xml') as f:
            f.write('<row id="1" name="xml1" />\n')
            f.write('<row id="2" name="xml2" />\n')
            temp_path = f.name
        
        try:
            url = create_async_connection_url()
            conn = await mariadb.asyncConnect(url, autocommit=True)
            cursor = conn.cursor()
            
            await cursor.execute("TRUNCATE local_infile_test_async")
            
            sql = f"LOAD XML LOCAL INFILE '{temp_path.replace(chr(92), '/')}' INTO TABLE local_infile_test_async"
            await cursor.execute(sql)
            
            await cursor.execute("SELECT * FROM local_infile_test_async ORDER BY id")
            rows = await cursor.fetchall()
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0], (1, 'xml1'))
            self.assertEqual(rows[1], (2, 'xml2'))
            
            await cursor.close()
            await conn.close()
        finally:
            os.unlink(temp_path)

    async def test_load_data_disabled_default_async(self):
        """Test that LOAD DATA LOCAL INFILE works when local_infile is not set (default None allows it) (async)"""
        if not self.local_infile_enabled:
            self.skipTest("local_infile not enabled on server")
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("1\ttest\n")
            temp_path = f.name
        
        try:
            # Connect without local_infile parameter (defaults to None, which allows LOAD LOCAL INFILE)
            url = create_async_connection_url()
            conn = await mariadb.asyncConnect(url, autocommit=True)
            cursor = conn.cursor()
            
            await cursor.execute("TRUNCATE local_infile_test_async")
            
            sql = f"LOAD DATA LOCAL INFILE '{temp_path.replace(chr(92), '/')}' INTO TABLE local_infile_test_async (id, name)"
            
            # Should work with default (None)
            await cursor.execute(sql)
            
            # Verify data was loaded
            await cursor.execute("SELECT COUNT(*) FROM local_infile_test_async")
            count = (await cursor.fetchone())[0]
            self.assertEqual(count, 1)
            
            # Connection should still be valid
            await cursor.execute("SELECT 1")
            result = await cursor.fetchone()
            self.assertEqual(result[0], 1)
            
            await cursor.close()
            await conn.close()
        finally:
            os.unlink(temp_path)

    async def test_load_data_disabled_explicit_false_async(self):
        """Test that LOAD DATA LOCAL INFILE fails when local_infile is explicitly set to False (async)"""
        if not self.local_infile_enabled:
            self.skipTest("local_infile not enabled on server")
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("1\ttest\n")
            temp_path = f.name
        
        try:
            # Connect with local_infile=False
            url = create_async_connection_url()
            conn = await mariadb.asyncConnect(url, autocommit=True, local_infile=False)
            cursor = conn.cursor()
            
            await cursor.execute("TRUNCATE local_infile_test_async")
            
            sql = f"LOAD DATA LOCAL INFILE '{temp_path.replace(chr(92), '/')}' INTO TABLE local_infile_test_async (id, name)"
            
            try:
                await cursor.execute(sql)
                self.fail("Should have raised an error when local_infile=False")
            except (mariadb.ProgrammingError, mariadb.DatabaseError) as e:
                # Should get error - either from client or server
                pass
            
            # Connection should still be valid after error
            await cursor.execute("SELECT 1")
            result = await cursor.fetchone()
            self.assertEqual(result[0], 1)
            
            await cursor.close()
            await conn.close()
        finally:
            os.unlink(temp_path)


if __name__ == '__main__':
    unittest.main()
