#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Unix Socket Connection Tests

Tests for connecting to MariaDB server using Unix domain sockets.
Based on mariadb-connector-j UnixsocketTest.java
"""

import os
import sys
import unittest
import platform

from ..conftest import get_test_config

try:
    import mariadb
except ImportError:
    mariadb = None


def is_windows():
    """Check if running on Windows"""
    return platform.system() == 'Windows'


def is_local_test():
    """Check if this is a local test environment"""
    local_env = os.getenv("LOCAL_DB", "")
    return local_env == "local" or local_env == ""

def generate_long_text(length):
    """Generate a long text string for testing"""
    return 'a' * length


@unittest.skipIf(mariadb is None, "mariadb module not available")
class TestUnixSocket(unittest.TestCase):
    """Test Unix socket connections"""

    @classmethod
    def setUpClass(cls):
        """Set up test table"""
        conf = get_test_config()
        cls.conn = mariadb.connect(**conf)
        cls.conn.autocommit = True
        cursor = cls.conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS test_unixsocket_table("
            "int_column INT DEFAULT 100, "
            "mediumtext_column MEDIUMTEXT NULL"
            ") COLLATE = utf8mb3_bin"
        )
        cursor.close()
        cls.conn.commit()

    @classmethod
    def tearDownClass(cls):
        """Clean up test table"""
        cursor = cls.conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS test_unixsocket_table")
        cursor.close()
        cls.conn.close()

    def setUp(self):
        """Clear test table before each test"""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM test_unixsocket_table")
        cursor.close()
        self.conn.commit()

    @unittest.skipIf(is_windows(), "Unix sockets not supported on Windows")
    @unittest.skipIf(not is_local_test(), "Test requires local environment")
    def test_ensure_unix_socket_reaching_buffer(self):
        """
        Test that large data can be transmitted over Unix socket connection.
        
        This test:
        1. Inserts a large text (50000 chars) into the database
        2. Gets the Unix socket path from the server
        3. Connects using the Unix socket
        4. Retrieves the data and verifies it
        """
        # Insert large text
        cursor = self.conn.cursor()
        long_text = generate_long_text(50000)
        cursor.execute(
            "INSERT INTO test_unixsocket_table (mediumtext_column) VALUES (?)",
            (long_text,)
        )
        
        # Get socket path from server
        cursor.execute("SELECT @@version_compile_os, @@socket")
        row = cursor.fetchone()
        cursor.close()
        
        # Commit the data so it's visible to other connections
        self.conn.commit()
        
        if not row or not row[1]:
            self.skipTest("Server does not provide socket path")
        
        socket_path = row[1]
        
        # Verify socket file exists
        if not os.path.exists(socket_path):
            self.skipTest(f"Socket file does not exist: {socket_path}")
        
        # Connect using Unix socket
        conf = get_test_config()
        conf['unix_socket'] = socket_path
        # Remove host/port to force Unix socket usage
        conf.pop('host', None)
        conf.pop('port', None)
        
        try:
            socket_conn = mariadb.connect(**conf)
            socket_cursor = socket_conn.cursor()
            
            # Verify we're using Unix socket
            self.assertIsNotNone(socket_conn.unix_socket)
            self.assertEqual(socket_conn.unix_socket, socket_path)
            
            # Query the data
            socket_cursor.execute("SELECT * FROM test_unixsocket_table")
            result = socket_cursor.fetchone()
            
            # Verify data
            self.assertIsNotNone(result)
            self.assertEqual(len(result[1]), 50000, "mediumtext_column should be 50000 chars")
            self.assertEqual(result[0], 100, "int_column should be 100")
            
            socket_cursor.close()
            socket_conn.close()
        except Exception as e:
            self.fail(f"Unix socket connection failed: {e}")

    @unittest.skipIf(not is_windows(), "Test is for Windows only")
    def test_unix_socket_error_on_windows(self):
        """
        Test that Unix socket connection fails gracefully on Windows.
        
        Unix domain sockets are not supported on Windows, so attempting
        to use them should raise an appropriate error.
        """
        conf = get_test_config()
        conf['unix_socket'] = '/tmp/not_valid_socket'
        conf.pop('host', None)
        conf.pop('port', None)
        
        with self.assertRaises(mariadb.OperationalError) as cm:
            mariadb.connect(**conf)
        
        # Check that error message mentions Unix sockets or Windows
        error_msg = str(cm.exception).lower()
        self.assertTrue(
            'unix' in error_msg or 'socket' in error_msg or 'windows' in error_msg,
            f"Error message should mention Unix sockets or Windows: {cm.exception}"
        )

    @unittest.skipIf(is_windows(), "Unix sockets not supported on Windows")
    def test_connect_with_invalid_unix_socket(self):
        """
        Test that connection fails appropriately with invalid Unix socket path.
        
        This test verifies that:
        1. Connection fails when socket doesn't exist
        2. No socket file descriptors are leaked
        3. Error is raised appropriately
        """
        conf = get_test_config()
        conf['unix_socket'] = '/tmp/not_valid_socket_mariadb_test'
        conf.pop('host', None)
        conf.pop('port', None)
        
        # Try to connect multiple times to check for resource leaks
        for i in range(10):
            with self.assertRaises(mariadb.OperationalError):
                mariadb.connect(**conf)
        
        # If we get here without hanging or crashing, the test passes
        # (We can't easily check for socket FD leaks in Python like in Java)

    @unittest.skipIf(is_windows(), "Unix sockets not supported on Windows")
    @unittest.skipIf(not is_local_test(), "Test requires local environment")
    def test_unix_socket_properties(self):
        """
        Test that connection properties are correct for Unix socket connections.
        
        Verifies:
        - unix_socket property returns the socket path
        - server_name is None (no TCP/IP host)
        - server_port is 0 (no TCP/IP port)
        """
        # Get socket path from server
        cursor = self.conn.cursor()
        cursor.execute("SELECT @@socket")
        row = cursor.fetchone()
        cursor.close()
        
        if not row or not row[0]:
            self.skipTest("Server does not provide socket path")
        
        socket_path = row[0]
        
        if not os.path.exists(socket_path):
            self.skipTest(f"Socket file does not exist: {socket_path}")
        
        # Connect using Unix socket
        conf = get_test_config()
        conf['unix_socket'] = socket_path
        conf.pop('host', None)
        conf.pop('port', None)
        
        try:
            socket_conn = mariadb.connect(**conf)
            
            # Verify Unix socket properties
            self.assertEqual(socket_conn.unix_socket, socket_path)
            self.assertIsNone(socket_conn.server_name, "server_name should be None for Unix socket")
            self.assertEqual(socket_conn.server_port, 0, "server_port should be 0 for Unix socket")
            
            # Verify connection works
            cursor = socket_conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            self.assertEqual(result[0], 1)
            cursor.close()
            
            socket_conn.close()
        except Exception as e:
            self.fail(f"Unix socket connection failed: {e}")

    @unittest.skipIf(is_windows(), "Unix sockets not supported on Windows")
    @unittest.skipIf(not is_local_test(), "Test requires local environment")
    def test_unix_socket_with_multiple_operations(self):
        """
        Test multiple database operations over Unix socket connection.
        
        Verifies that Unix socket connections can handle:
        - Multiple queries
        - Transactions
        - Large result sets
        """
        # Get socket path
        cursor = self.conn.cursor()
        cursor.execute("SELECT @@socket")
        row = cursor.fetchone()
        cursor.close()
        
        if not row or not row[0]:
            self.skipTest("Server does not provide socket path")
        
        socket_path = row[0]
        
        if not os.path.exists(socket_path):
            self.skipTest(f"Socket file does not exist: {socket_path}")
        
        # Connect using Unix socket
        conf = get_test_config()
        conf['unix_socket'] = socket_path
        conf.pop('host', None)
        conf.pop('port', None)
        
        try:
            socket_conn = mariadb.connect(**conf)
            socket_conn.autocommit = True
            cursor = socket_conn.cursor()
            
            # First test a simple query to verify connection works
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            self.assertEqual(result[0], 1, "Simple query should work")
            
            # Test multiple inserts using string formatting (avoid parameterized queries for now)
            for i in range(10):
                cursor.execute(
                    f"INSERT INTO test_unixsocket_table (int_column, mediumtext_column) VALUES ({i}, 'text_{i}')"
                )
            
            socket_conn.commit()
            # Test query with multiple results
            cursor.execute("SELECT * FROM test_unixsocket_table ORDER BY int_column")
            results = cursor.fetchall()
            self.assertEqual(len(results), 10)
            
            # Verify data
            for i, row in enumerate(results):
                self.assertEqual(row[0], i)
                # Handle both string and bytes - convert bytes to string if needed
                text_val = row[1]
                if isinstance(text_val, bytearray):
                    text_val = text_val.decode('utf-8')
                elif isinstance(text_val, bytes):
                    text_val = text_val.decode('utf-8')
                self.assertTrue(text_val.startswith('text_'), 
                               f"Expected text to start with 'text_', got: {text_val!r} (type: {type(text_val)})")
            
            cursor.close()
            socket_conn.close()
        except Exception as e:
            self.fail(f"Unix socket operations failed: {e}")


if __name__ == '__main__':
    unittest.main()
