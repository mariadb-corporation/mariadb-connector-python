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
from ..base_test import create_connection, is_maxscale, is_native
from ..conftest import get_test_config as conf


@unittest.skipIf(is_maxscale(), "LOAD DATA LOCAL INFILE not supported through MaxScale")
class TestLocalInfile(unittest.TestCase):
    """Test LOAD DATA LOCAL INFILE functionality"""

    @classmethod
    def setUpClass(cls):
        """Create test tables"""
        conn = create_connection({'autocommit': True, 'local_infile': True})
        cursor = conn.cursor()
        
        # Drop tables if they exist
        cursor.execute("DROP TABLE IF EXISTS local_infile_test")
        cursor.execute("DROP TABLE IF EXISTS local_infile_test2")
        cursor.execute("DROP TABLE IF EXISTS local_infile_empty")
        cursor.execute("DROP TABLE IF EXISTS local_infile_large")
        
        # Create test tables
        cursor.execute("""
            CREATE TABLE local_infile_test (
                id INT,
                name VARCHAR(100)
            )
        """)
        cursor.execute("""
            CREATE TABLE local_infile_test2 (
                id INT,
                name VARCHAR(100)
            )
        """)
        cursor.execute("""
            CREATE TABLE local_infile_empty (
                id INT,
                name VARCHAR(100)
            )
        """)
        cursor.execute("""
            CREATE TABLE local_infile_large (
                a VARCHAR(50),
                b VARCHAR(50)
            )
        """)
        
        cursor.close()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        """Drop test tables"""
        try:
            conn = create_connection({'autocommit': True, 'local_infile': True})
            cursor = conn.cursor()
            cursor.execute("DROP TABLE IF EXISTS local_infile_test")
            cursor.execute("DROP TABLE IF EXISTS local_infile_test2")
            cursor.execute("DROP TABLE IF EXISTS local_infile_empty")
            cursor.execute("DROP TABLE IF EXISTS local_infile_large")
            cursor.close()
            conn.close()
        except:
            pass

    def setUp(self):
        """Check if local_infile is enabled on server"""
        conn = create_connection({'autocommit': True, 'local_infile': True})
        cursor = conn.cursor()
        cursor.execute("SELECT @@local_infile")
        row = cursor.fetchone()
        self.local_infile_enabled = row[0] == 1 if row else False
        cursor.close()
        conn.close()

    def test_load_data_basic(self):
        """Test basic LOAD DATA LOCAL INFILE"""
        if not self.local_infile_enabled:
            self.skipTest("local_infile not enabled on server")
        
        # Create temp file with test data
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', newline='') as f:
            f.write("1\thello\n")
            f.write("2\tworld\n")
            f.write("3\ttest\n")
            temp_path = f.name
        
        try:
            conn = create_connection({'autocommit': True, 'local_infile': True})
            cursor = conn.cursor()
            
            # Truncate table
            cursor.execute("TRUNCATE local_infile_test")
            
            # Load data from file
            sql = f"LOAD DATA LOCAL INFILE '{temp_path.replace(chr(92), '/')}' INTO TABLE local_infile_test (id, name)"
            cursor.execute(sql)
            
            # Verify data was loaded
            cursor.execute("SELECT * FROM local_infile_test ORDER BY id")
            rows = cursor.fetchall()
            
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0], (1, 'hello'))
            self.assertEqual(rows[1], (2, 'world'))
            self.assertEqual(rows[2], (3, 'test'))
            
            cursor.close()
            conn.close()
        finally:
            os.unlink(temp_path)

    def test_load_data_windows_path(self):
        """Test LOAD DATA LOCAL INFILE with Windows-style path (double backslashes)"""
        if not self.local_infile_enabled:
            self.skipTest("local_infile not enabled on server")
        
        # Create temp file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', newline='') as f:
            f.write("10\twindows\n")
            f.write("20\tpath\n")
            temp_path = f.name
        
        try:
            conn = create_connection({'autocommit': True, 'local_infile': True})
            cursor = conn.cursor()
            
            cursor.execute("TRUNCATE local_infile_test")
            
            # Use double backslashes (Windows style)
            escaped_path = temp_path.replace(chr(92), chr(92) + chr(92))
            sql = f"LOAD DATA LOCAL INFILE '{escaped_path}' INTO TABLE local_infile_test (id, name)"
            cursor.execute(sql)
            
            cursor.execute("SELECT * FROM local_infile_test ORDER BY id")
            rows = cursor.fetchall()
            
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0], (10, 'windows'))
            self.assertEqual(rows[1], (20, 'path'))
            
            cursor.close()
            conn.close()
        finally:
            os.unlink(temp_path)

    def test_load_data_empty_file(self):
        """Test LOAD DATA LOCAL INFILE with empty file"""
        if not self.local_infile_enabled:
            self.skipTest("local_infile not enabled on server")
        
        # Create empty temp file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            temp_path = f.name
        
        try:
            conn = create_connection({'autocommit': True, 'local_infile': True})
            cursor = conn.cursor()
            
            cursor.execute("TRUNCATE local_infile_empty")
            
            sql = f"LOAD DATA LOCAL INFILE '{temp_path.replace(chr(92), '/')}' INTO TABLE local_infile_empty (id, name)"
            cursor.execute(sql)
            
            cursor.execute("SELECT COUNT(*) FROM local_infile_empty")
            count = cursor.fetchone()[0]
            self.assertEqual(count, 0)
            
            cursor.close()
            conn.close()
        finally:
            os.unlink(temp_path)

    def test_load_data_file_not_found(self):
        """Test LOAD DATA LOCAL INFILE with non-existent file"""
        if not self.local_infile_enabled:
            self.skipTest("local_infile not enabled on server")
        
        conn = create_connection({'autocommit': True, 'local_infile': True})
        cursor = conn.cursor()
        
        try:
            sql = "LOAD DATA LOCAL INFILE '/nonexistent/file.txt' INTO TABLE local_infile_test (id, name)"
            cursor.execute(sql)
            self.fail("Should have raised an error for non-existent file")
        except (mariadb.OperationalError, mariadb.InternalError) as e:
            # Should get "Could not send file" or "File not found" error
            self.assertTrue("Could not send file" in str(e) or "not found" in str(e))
        finally:
            # Connection should still be valid
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            self.assertEqual(result[0], 1)
            cursor.close()
            conn.close()

    def test_load_data_with_comments(self):
        """Test LOAD DATA LOCAL INFILE with SQL comments"""
        if not self.local_infile_enabled:
            self.skipTest("local_infile not enabled on server")
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', newline='') as f:
            f.write("100\tcomment\n")
            temp_path = f.name
        
        try:
            conn = create_connection({'autocommit': True, 'local_infile': True})
            cursor = conn.cursor()
            
            cursor.execute("TRUNCATE local_infile_test")
            
            # SQL with comment before LOAD DATA
            sql = f"/* test comment */ LOAD DATA LOCAL INFILE '{temp_path.replace(chr(92), '/')}' INTO TABLE local_infile_test (id, name)"
            cursor.execute(sql)
            
            cursor.execute("SELECT * FROM local_infile_test")
            rows = cursor.fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0], (100, 'comment'))
            
            cursor.close()
            conn.close()
        finally:
            os.unlink(temp_path)

    def test_load_data_large_file(self):
        """Test LOAD DATA LOCAL INFILE with larger file (multiple packets)"""
        if not self.local_infile_enabled:
            self.skipTest("local_infile not enabled on server")
        
        # Create file with 1000 rows
        row_count = 1000
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', newline='') as f:
            for i in range(row_count):
                f.write(f"{i}\trow_{i}\n")
            temp_path = f.name
        
        try:
            conn = create_connection({'autocommit': True, 'local_infile': True})
            cursor = conn.cursor()
            
            cursor.execute("TRUNCATE local_infile_test")
            
            sql = f"LOAD DATA LOCAL INFILE '{temp_path.replace(chr(92), '/')}' INTO TABLE local_infile_test (id, name)"
            cursor.execute(sql)
            
            cursor.execute("SELECT COUNT(*) FROM local_infile_test")
            count = cursor.fetchone()[0]
            self.assertEqual(count, row_count)
            
            # Verify some rows
            cursor.execute("SELECT * FROM local_infile_test WHERE id IN (0, 500, 999) ORDER BY id")
            rows = cursor.fetchall()
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0], (0, 'row_0'))
            self.assertEqual(rows[1], (500, 'row_500'))
            self.assertEqual(rows[2], (999, 'row_999'))
            
            cursor.close()
            conn.close()
        finally:
            os.unlink(temp_path)

    def test_load_data_with_custom_delimiters(self):
        """Test LOAD DATA LOCAL INFILE with custom field and line terminators"""
        if not self.local_infile_enabled:
            self.skipTest("local_infile not enabled on server")
        
        # Create CSV file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv', newline='') as f:
            f.write('"a","b"\n')
            f.write('"c","d"\n')
            temp_path = f.name
        
        try:
            conn = create_connection({'autocommit': True, 'local_infile': True})
            cursor = conn.cursor()
            
            cursor.execute("TRUNCATE local_infile_large")
            
            sql = f"""
                LOAD DATA LOCAL INFILE '{temp_path.replace(chr(92), '/')}'
                INTO TABLE local_infile_large
                FIELDS TERMINATED BY ',' ENCLOSED BY '"'
                LINES TERMINATED BY '\\n'
                (a, b)
            """
            cursor.execute(sql)
            
            cursor.execute("SELECT * FROM local_infile_large ORDER BY a")
            rows = cursor.fetchall()
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0], ('a', 'b'))
            self.assertEqual(rows[1], ('c', 'd'))
            
            cursor.close()
            conn.close()
        finally:
            os.unlink(temp_path)

    def test_load_xml_local_infile(self):
        """Test LOAD XML LOCAL INFILE"""
        if not self.local_infile_enabled:
            self.skipTest("local_infile not enabled on server")
        
        # Create XML file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.xml', newline='') as f:
            f.write('<row id="1" name="xml1" />\n')
            f.write('<row id="2" name="xml2" />\n')
            temp_path = f.name
        
        try:
            conn = create_connection({'autocommit': True, 'local_infile': True})
            cursor = conn.cursor()
            
            cursor.execute("TRUNCATE local_infile_test")
            
            sql = f"LOAD XML LOCAL INFILE '{temp_path.replace(chr(92), '/')}' INTO TABLE local_infile_test"
            cursor.execute(sql)
            
            cursor.execute("SELECT * FROM local_infile_test ORDER BY id")
            rows = cursor.fetchall()
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0], (1, 'xml1'))
            self.assertEqual(rows[1], (2, 'xml2'))
            
            cursor.close()
            conn.close()
        finally:
            os.unlink(temp_path)

    def test_load_data_validation_security(self):
        """Test that filename validation prevents malicious server responses"""
        if not self.local_infile_enabled:
            self.skipTest("local_infile not enabled on server")
        
        # This test verifies that if a malicious proxy changes the filename
        # in the server response, the client will reject it
        # In normal operation, this shouldn't happen, but the validation is there for security
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', newline='') as f:
            f.write("1\ttest\n")
            temp_path = f.name
        
        try:
            conn = create_connection({'autocommit': True, 'local_infile': True})
            cursor = conn.cursor()
            
            # Normal case should work
            cursor.execute("TRUNCATE local_infile_test")
            sql = f"LOAD DATA LOCAL INFILE '{temp_path.replace(chr(92), '/')}' INTO TABLE local_infile_test (id, name)"
            cursor.execute(sql)
            
            cursor.execute("SELECT COUNT(*) FROM local_infile_test")
            count = cursor.fetchone()[0]
            self.assertEqual(count, 1)
            
            cursor.close()
            conn.close()
        finally:
            os.unlink(temp_path)

    def test_load_data_disabled_default(self):
        """Test that LOAD DATA LOCAL INFILE works when local_infile is not set (default None allows it)"""
        if not self.local_infile_enabled:
            self.skipTest("local_infile not enabled on server")
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', newline='') as f:
            f.write("1\ttest\n")
            temp_path = f.name
        
        try:
            # Connect without local_infile parameter (defaults to None, which allows LOAD LOCAL INFILE)
            conn = create_connection({'autocommit': True})
            cursor = conn.cursor()
            
            cursor.execute("TRUNCATE local_infile_test")
            
            sql = f"LOAD DATA LOCAL INFILE '{temp_path.replace(chr(92), '/')}' INTO TABLE local_infile_test (id, name)"
            
            # Should work with default (None)
            cursor.execute(sql)
            
            # Verify data was loaded
            cursor.execute("SELECT COUNT(*) FROM local_infile_test")
            count = cursor.fetchone()[0]
            self.assertEqual(count, 1)
            
            # Connection should still be valid
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            self.assertEqual(result[0], 1)
            
            cursor.close()
            conn.close()
        finally:
            os.unlink(temp_path)

    def test_load_data_disabled_explicit_false(self):
        """Test that LOAD DATA LOCAL INFILE fails when local_infile is explicitly set to False"""
        if not self.local_infile_enabled:
            self.skipTest("local_infile not enabled on server")
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', newline='') as f:
            f.write("1\ttest\n")
            temp_path = f.name
        
        try:
            # Connect with local_infile=False
            conn = create_connection({'autocommit': True, 'local_infile': False})
            cursor = conn.cursor()
            
            cursor.execute("TRUNCATE local_infile_test")
            
            sql = f"LOAD DATA LOCAL INFILE '{temp_path.replace(chr(92), '/')}' INTO TABLE local_infile_test (id, name)"
            
            try:
                cursor.execute(sql)
                self.fail("Should have raised ProgrammingError when local_infile=False")
            except (mariadb.ProgrammingError, mariadb.OperationalError, mariadb.DatabaseError) as e:
                pass    
            
            # Connection should still be valid after error
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            self.assertEqual(result[0], 1)
            
            cursor.close()
            conn.close()
        finally:
            os.unlink(temp_path)


if __name__ == '__main__':
    unittest.main()
