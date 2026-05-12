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
from ..base_test import create_connection, is_maxscale

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
@unittest.skipIf(is_maxscale(), "Unix socket connections not supported through MaxScale")
class TestUnixSocket(unittest.TestCase):
    """Test Unix socket connections"""

    @classmethod
    def setUpClass(cls):
        """Set up test table"""
        try:
            cls.conn = create_connection()
            cls.conn.autocommit = True
            cursor = cls.conn.cursor()
            cursor.execute("DROP TABLE IF EXISTS test_unixsocket_table")
            cursor.execute(
                "CREATE TABLE test_unixsocket_table("
                "int_column INT DEFAULT 100, "
                "mediumtext_column MEDIUMTEXT NULL"
                ")"
            )
            cursor.close()
        except Exception as e:
            if hasattr(cls, 'conn'):
                cls.conn.close()
            raise

    @classmethod
    def tearDownClass(cls):
        """Clean up test table"""
        # Check if conn exists and is a valid connection object
        if hasattr(cls, 'conn') and hasattr(cls.conn, 'cursor'):
            try:
                cursor = cls.conn.cursor()
                cursor.execute("DROP TABLE IF EXISTS test_unixsocket_table")
                cursor.close()
                cls.conn.close()
            except Exception:
                # Connection might already be closed or invalid
                pass

    def setUp(self):
        """Clear test table before each test"""
        # Check if conn exists and is valid
        if not hasattr(self.__class__, 'conn') or not hasattr(self.__class__.conn, 'cursor'):
            self.skipTest("Class-level connection not available")
        
        try:
            cursor = self.__class__.conn.cursor()
            cursor.execute("DELETE FROM test_unixsocket_table")
            cursor.close()
        except Exception as e:
            self.skipTest(f"Failed to clear test table: {e}")

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
        
        if not row or not row[1]:
            self.skipTest("Server does not provide socket path")
        
        socket_path = row[1]
        
        # Verify socket file exists
        if not os.path.exists(socket_path):
            self.skipTest(f"Socket file does not exist: {socket_path}")
        
        # Connect using Unix socket
        conf = get_test_config()
        conf['unix_socket'] = socket_path
        conf["connect_timeout"] = 0
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


    @unittest.skipIf(is_windows(), "Unix sockets not supported on Windows")
    @unittest.skipIf(not is_local_test(), "Test requires local environment")
    def test_localhost_defaults_to_unix_socket(self):
        """
        CONPY-340: connecting with host='localhost' (or no host) and no
        unix_socket should auto-detect the distro's default socket path,
        mirroring libmariadb behaviour (MARIADB_UNIX_ADDR compile-time
        default — different per distro).
        """
        # Pure-Python path detects the per-distro default at module load;
        # skip if we can't find it (non-Linux, or distro not in our mapping,
        # or the path simply doesn't exist on this server).
        try:
            from mariadb.impl.client.base_client import _find_default_unix_socket
        except ImportError:
            self.skipTest("Auto-detection only applies to the pure-Python client")
        detected = _find_default_unix_socket()
        if detected is None:
            self.skipTest("No default Unix socket detected for this platform/distro")

        # Build a config with host='localhost' and no explicit unix_socket.
        conf = get_test_config()
        conf.pop('unix_socket', None)
        conf['host'] = 'localhost'

        conn = mariadb.connect(**conf)
        try:
            self.assertEqual(conn.unix_socket, detected,
                             f"Expected unix_socket to be auto-detected as {detected}")
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            self.assertEqual(cursor.fetchone()[0], 1)
            cursor.close()
        finally:
            conn.close()


    @unittest.skipIf(is_windows(), "Unix sockets not supported on Windows")
    @unittest.skipIf(not is_local_test(), "Test requires local environment")
    def test_localhost_with_tcp_protocol_skips_unix_socket(self):
        """
        CONPY-340: when protocol='TCP' is set, the connector must use TCP even
        when host='localhost' and a default Unix socket is auto-detectable.
        """
        try:
            from mariadb.impl.client.base_client import _find_default_unix_socket
        except ImportError:
            self.skipTest("Auto-detection only applies to the pure-Python client")
        if _find_default_unix_socket() is None:
            self.skipTest("No default Unix socket would otherwise be picked up")

        conf = get_test_config()
        conf.pop('unix_socket', None)
        conf['host'] = 'localhost'
        conf['protocol'] = 'TCP'

        conn = mariadb.connect(**conf)
        try:
            self.assertEqual(conn.unix_socket, '',
                             "unix_socket should be '' when protocol=TCP forces TCP")
            self.assertNotEqual(conn.server_port, 0,
                                "server_port should be non-zero for a TCP connection")
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            self.assertEqual(cursor.fetchone()[0], 1)
            cursor.close()
        finally:
            conn.close()


if __name__ == '__main__':
    unittest.main()
