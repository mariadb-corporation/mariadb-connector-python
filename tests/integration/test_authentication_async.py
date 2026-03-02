#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Async Authentication Plugin Tests for MariaDB Connector/Python

Tests for various authentication plugins including:
- PARSEC password authentication
- Native password authentication
- Caching SHA2 password authentication
"""

import unittest
import os
import sys
import pytest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import mariadb
from tests.base_test import is_native, get_host_suffix
from tests.conftest import get_test_config

class AsyncTestParsecAuthentication(unittest.IsolatedAsyncioTestCase):
    """Async test cases for PARSEC password authentication plugin"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test class - check if PARSEC authentication is available"""
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            cls.has_cryptography = True
        except ImportError:
            cls.has_cryptography = False
    
    async def asyncSetUp(self):
        """Set up test case"""
        if not self.has_cryptography and is_native():
            self.skipTest("cryptography library not available for PARSEC authentication")
        
        config = get_test_config()
        self.connection = await mariadb.AsyncConnection.connect(**config)
        self.cursor = self.connection.cursor()
        
        # Check if strict password validation is enabled
        try:
            await self.cursor.execute("SELECT @@global.strict_password_validation")
            result = await self.cursor.fetchone()
            self.strict_password_validation = bool(result[0]) if result else False
        except mariadb.Error:
            self.strict_password_validation = False
        
        try:
            await self.cursor.execute("INSTALL SONAME 'auth_parsec'")
        except:
            pass
        # Check if server supports PARSEC plugin
        await self.cursor.execute("SELECT PLUGIN_NAME FROM information_schema.PLUGINS WHERE PLUGIN_NAME='parsec'")
        if not await self.cursor.fetchone():
            self.skipTest("Server does not support PARSEC authentication plugin")
    
    async def asyncTearDown(self):
        """Clean up test case"""
        if hasattr(self, 'cursor') and self.cursor:
            # Clean up test users
            try:
                await self.cursor.execute(f"DROP USER IF EXISTS 'parsec_test_user'{get_host_suffix()}")
                await self.cursor.execute(f"DROP USER IF EXISTS 'parsec_empty_pwd'{get_host_suffix()}")
                await self.cursor.execute(f"DROP USER IF EXISTS 'parsec_special_chars'{get_host_suffix()}")
            except:
                pass
            await self.cursor.close()
        
        if hasattr(self, 'connection') and self.connection:
            await self.connection.close()
    
    async def test_parsec_basic_authentication(self):
        """Test basic PARSEC authentication with standard password"""
        # Create test user with PARSEC authentication
        test_password = "parsec_test_password_123"
        
        await self.cursor.execute(f"DROP USER IF EXISTS 'parsec_test_user'{get_host_suffix()}")
        await self.cursor.execute(
            f"CREATE USER 'parsec_test_user'{get_host_suffix()} "
            f"IDENTIFIED VIA parsec USING PASSWORD('{test_password}')"
        )
        await self.cursor.execute(f"GRANT ALL PRIVILEGES ON *.* TO 'parsec_test_user'{get_host_suffix()}")
        await self.connection.commit()
        
        # Test connection with PARSEC user
        conn_config = get_test_config().copy()
        conn_config['user'] = 'parsec_test_user'
        conn_config['password'] = test_password
        
        parsec_conn = await mariadb.AsyncConnection.connect(**conn_config)
        self.assertIsNotNone(parsec_conn)
        
        # Verify connection works
        parsec_cursor = parsec_conn.cursor()
        await parsec_cursor.execute("SELECT USER()")
        user_result = await parsec_cursor.fetchone()
        self.assertIn('parsec_test_user', user_result[0])
        
        await parsec_cursor.close()
        await parsec_conn.close()
    
    async def test_parsec_empty_password(self):
        """Test PARSEC authentication with empty password"""
        # Skip if strict password validation is enabled
        if self.strict_password_validation:
            self.skipTest("Strict password validation is enabled - empty passwords not allowed")
        
        await self.cursor.execute(f"DROP USER IF EXISTS 'parsec_empty_pwd'{get_host_suffix()}")
        await self.cursor.execute(
            f"CREATE USER 'parsec_empty_pwd'{get_host_suffix()} "
            f"IDENTIFIED VIA parsec USING PASSWORD('')"
        )
        await self.cursor.execute(f"GRANT ALL PRIVILEGES ON *.* TO 'parsec_empty_pwd'{get_host_suffix()}")
        await self.connection.commit()
        
        # Test connection with empty password
        conn_config = get_test_config().copy()
        conn_config['user'] = 'parsec_empty_pwd'
        conn_config['password'] = ''
        
        parsec_conn = await mariadb.AsyncConnection.connect(**conn_config)
        self.assertIsNotNone(parsec_conn)
        
        parsec_cursor = parsec_conn.cursor()
        await parsec_cursor.execute("SELECT 1")
        result = await parsec_cursor.fetchone()
        self.assertEqual(result[0], 1)
        
        await parsec_cursor.close()
        await parsec_conn.close()
    
    async def test_parsec_wrong_password(self):
        """Test PARSEC authentication with incorrect password"""
        test_password = "correct_password_123"
        
        await self.cursor.execute(f"DROP USER IF EXISTS 'parsec_test_user'{get_host_suffix()}")
        await self.cursor.execute(
            f"CREATE USER 'parsec_test_user'{get_host_suffix()} "
            f"IDENTIFIED VIA parsec USING PASSWORD('{test_password}')"
        )
        await self.cursor.execute(f"GRANT ALL PRIVILEGES ON *.* TO 'parsec_test_user'{get_host_suffix()}")
        await self.connection.commit()
        
        # Try to connect with wrong password
        conn_config = get_test_config().copy()
        conn_config['user'] = 'parsec_test_user'
        conn_config['password'] = 'wrong_password'

        with self.assertRaises(mariadb.DatabaseError) as context:
            await mariadb.AsyncConnection.connect(**conn_config)
        
        # Verify it's an authentication error
        self.assertIn('Access denied', str(context.exception))
    
    async def test_parsec_special_characters_password(self):
        """Test PARSEC authentication with special characters in password"""
        # Password with special characters
        test_password = "P@ssw0rd!#$%^&*()_+-=[]{}|;:',.<>?/~`"
        
        await self.cursor.execute(f"DROP USER IF EXISTS 'parsec_special_chars'{get_host_suffix()}")
        # Need to escape single quotes in SQL
        escaped_password = test_password.replace("'", "''")
        await self.cursor.execute(
            f"CREATE USER 'parsec_special_chars'{get_host_suffix()} "
            f"IDENTIFIED VIA parsec USING PASSWORD('{escaped_password}')"
        )
        await self.cursor.execute(f"GRANT ALL PRIVILEGES ON *.* TO 'parsec_special_chars'{get_host_suffix()}")
        await self.connection.commit()
        
        # Test connection with special characters password
        conn_config = get_test_config().copy()
        conn_config['user'] = 'parsec_special_chars'
        conn_config['password'] = test_password
        
        parsec_conn = await mariadb.AsyncConnection.connect(**conn_config)
        self.assertIsNotNone(parsec_conn)
        
        parsec_cursor = parsec_conn.cursor()
        await parsec_cursor.execute("SELECT DATABASE()")
        db_result = await parsec_cursor.fetchone()
        self.assertEqual(db_result[0], get_test_config()["database"])
        
        await parsec_cursor.close()
        await parsec_conn.close()
    
    async def test_parsec_unicode_password(self):
        """Test PARSEC authentication with Unicode characters in password"""
        # Password with Unicode characters
        test_password = "пароль密码🔐"
        
        await self.cursor.execute(f"DROP USER IF EXISTS 'parsec_test_user'{get_host_suffix()}")
        # Need to escape single quotes in SQL
        escaped_password = test_password.replace("'", "''")
        await self.cursor.execute(
            f"CREATE USER 'parsec_test_user'{get_host_suffix()} "
            f"IDENTIFIED VIA parsec USING PASSWORD('{escaped_password}')"
        )
        await self.cursor.execute(f"GRANT ALL PRIVILEGES ON *.* TO 'parsec_test_user'{get_host_suffix()}")
        await self.connection.commit()
        
        # Test connection with Unicode password
        conn_config = get_test_config().copy()
        conn_config['user'] = 'parsec_test_user'
        conn_config['password'] = test_password
        
        parsec_conn = await mariadb.AsyncConnection.connect(**conn_config)
        self.assertIsNotNone(parsec_conn)
        
        parsec_cursor = parsec_conn.cursor()
        await parsec_cursor.execute("SELECT 'Unicode test'")
        result = await parsec_cursor.fetchone()
        self.assertEqual(result[0], 'Unicode test')
        
        await parsec_cursor.close()
        await parsec_conn.close()
    
    async def test_parsec_long_password(self):
        """Test PARSEC authentication with very long password"""
        # Skip if strict password validation is enabled
        if self.strict_password_validation:
            self.skipTest("Strict password validation is enabled - simple passwords not allowed")
        
        # 256 character password
        test_password = "a" * 256
        
        await self.cursor.execute(f"DROP USER IF EXISTS 'parsec_test_user'{get_host_suffix()}")
        await self.cursor.execute(
            f"CREATE USER 'parsec_test_user'{get_host_suffix()} "
            f"IDENTIFIED VIA parsec USING PASSWORD('{test_password}')"
        )
        await self.cursor.execute(f"GRANT ALL PRIVILEGES ON *.* TO 'parsec_test_user'{get_host_suffix()}")
        await self.connection.commit()
        
        # Test connection with long password
        conn_config = get_test_config().copy()
        conn_config['user'] = 'parsec_test_user'
        conn_config['password'] = test_password
        
        parsec_conn = await mariadb.AsyncConnection.connect(**conn_config)
        self.assertIsNotNone(parsec_conn)
        
        parsec_cursor = parsec_conn.cursor()
        await parsec_cursor.execute("SELECT VERSION()")
        version = await parsec_cursor.fetchone()
        self.assertIsNotNone(version[0])
        
        await parsec_cursor.close()
        await parsec_conn.close()
    
    async def test_parsec_multiple_connections(self):
        """Test multiple simultaneous PARSEC authenticated connections"""
        test_password = "multi_conn_test_123"
        
        await self.cursor.execute(f"DROP USER IF EXISTS 'parsec_test_user'{get_host_suffix()}")
        await self.cursor.execute(
            f"CREATE USER 'parsec_test_user'{get_host_suffix()} "
            f"IDENTIFIED VIA parsec USING PASSWORD('{test_password}')"
        )
        await self.cursor.execute(f"GRANT ALL PRIVILEGES ON *.* TO 'parsec_test_user'{get_host_suffix()}")
        await self.connection.commit()
        
        conn_config = get_test_config().copy()
        conn_config['user'] = 'parsec_test_user'
        conn_config['password'] = test_password
        
        # Create multiple connections
        connections = []
        try:
            for i in range(5):
                conn = await mariadb.AsyncConnection.connect(**conn_config)
                self.assertIsNotNone(conn)
                
                cursor = conn.cursor()
                await cursor.execute("SELECT CONNECTION_ID()")
                conn_id = (await cursor.fetchone())[0]
                self.assertIsNotNone(conn_id)
                
                connections.append((conn, cursor))
            
            # Verify all connections are independent
            conn_ids = set()
            for conn, cursor in connections:
                await cursor.execute("SELECT CONNECTION_ID()")
                conn_ids.add((await cursor.fetchone())[0])
            
            self.assertEqual(len(conn_ids), 5, "All connections should have unique IDs")
            
        finally:
            # Clean up connections
            for conn, cursor in connections:
                await cursor.close()
                await conn.close()
    
    async def test_parsec_reconnection(self):
        """Test reconnecting with PARSEC authentication after disconnect"""
        test_password = "reconnect_test_456"
        
        await self.cursor.execute(f"DROP USER IF EXISTS 'parsec_test_user'{get_host_suffix()}")
        await self.cursor.execute(
            f"CREATE USER 'parsec_test_user'{get_host_suffix()} "
            f"IDENTIFIED VIA parsec USING PASSWORD('{test_password}')"
        )
        await self.cursor.execute(f"GRANT ALL PRIVILEGES ON *.* TO 'parsec_test_user'{get_host_suffix()}")
        await self.connection.commit()
        
        conn_config = get_test_config().copy()
        conn_config['user'] = 'parsec_test_user'
        conn_config['password'] = test_password
        
        # First connection
        conn1 = await mariadb.AsyncConnection.connect(**conn_config)
        cursor1 = conn1.cursor()
        await cursor1.execute("SELECT 1")
        self.assertEqual((await cursor1.fetchone())[0], 1)
        await cursor1.close()
        await conn1.close()
        
        # Reconnect
        conn2 = await mariadb.AsyncConnection.connect(**conn_config)
        cursor2 = conn2.cursor()
        await cursor2.execute("SELECT 2")
        self.assertEqual((await cursor2.fetchone())[0], 2)
        await cursor2.close()
        await conn2.close()
        
        # Third connection to ensure it's repeatable
        conn3 = await mariadb.AsyncConnection.connect(**conn_config)
        cursor3 = conn3.cursor()
        await cursor3.execute("SELECT 3")
        self.assertEqual((await cursor3.fetchone())[0], 3)
        await cursor3.close()
        await conn3.close()
    
    async def test_parsec_ssl_connection(self):
        """Test PARSEC authentication over SSL connection"""
        # First check if SSL is enabled on the server
        await self.cursor.execute("SHOW VARIABLES LIKE 'have_ssl'")
        row = await self.cursor.fetchone()
        if not row or row[1].upper() != 'YES':
            self.skipTest("SSL is not enabled on the server (have_ssl != YES)")
        
        test_password = "ssl_parsec_test_789"
        
        await self.cursor.execute(f"DROP USER IF EXISTS 'parsec_test_user'{get_host_suffix()}")
        await self.cursor.execute(
            f"CREATE USER 'parsec_test_user'{get_host_suffix()} "
            f"IDENTIFIED VIA parsec USING PASSWORD('{test_password}')"
        )
        await self.cursor.execute(f"GRANT ALL PRIVILEGES ON *.* TO 'parsec_test_user'{get_host_suffix()}")
        await self.connection.commit()
        
        # Test connection with SSL enabled
        conn_config = get_test_config().copy()
        conn_config['user'] = 'parsec_test_user'
        conn_config['password'] = test_password
        conn_config['ssl'] = True
        
        parsec_ssl_conn = await mariadb.AsyncConnection.connect(**conn_config)
        self.assertIsNotNone(parsec_ssl_conn)
        
        # Verify SSL is actually being used
        parsec_cursor = parsec_ssl_conn.cursor()
        await parsec_cursor.execute("SHOW STATUS LIKE 'Ssl_cipher'")
        ssl_row = await parsec_cursor.fetchone()
        self.assertIsNotNone(ssl_row, "Ssl_cipher status should be available")
        self.assertNotEqual(ssl_row[1], '', "Ssl_cipher should not be empty when SSL is enabled")
        
        # Verify PARSEC authentication worked
        await parsec_cursor.execute("SELECT USER()")
        user_result = await parsec_cursor.fetchone()
        self.assertIn('parsec_test_user', user_result[0])
        
        # Execute a query to ensure connection is fully functional
        await parsec_cursor.execute("SELECT 'SSL + PARSEC test'")
        result = await parsec_cursor.fetchone()
        self.assertEqual(result[0], 'SSL + PARSEC test')
        
        await parsec_cursor.close()
        await parsec_ssl_conn.close()


class TestAuthenticationPluginFactory(unittest.TestCase):
    """Test cases for authentication plugin factory and plugin loading"""
    
    def test_parsec_plugin_available(self):
        """Test that PARSEC plugin is available in the plugin registry"""
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            has_cryptography = True
        except ImportError:
            has_cryptography = False
        
        if not has_cryptography and is_native():
            self.skipTest("cryptography library not available")
        
        try:
            from mariadb.impl.plugin.authentication.parsec_password_plugin_factory import ParsecPasswordPluginFactory
        except ImportError:
            self.skipTest("mariadb pure-Python package not installed")
        
        factory = ParsecPasswordPluginFactory()
        self.assertEqual(factory.type(), "parsec")
        self.assertFalse(factory.require_ssl())
    
    def test_parsec_plugin_creation(self):
        """Test creating PARSEC plugin instance"""
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            has_cryptography = True
        except ImportError:
            has_cryptography = False
        
        if not has_cryptography and is_native():
            self.skipTest("cryptography library not available")
        
        try:
            from mariadb.impl.plugin.authentication.parsec_password_plugin_factory import ParsecPasswordPluginFactory
        except ImportError:
            self.skipTest("mariadb pure-Python package not installed")
        
        factory = ParsecPasswordPluginFactory()
        authentication_data = "test_password"
        seed = b'\x00' * 20  # Dummy seed
        
        plugin = factory.initialize(authentication_data, seed, None, None)
        self.assertIsNotNone(plugin)
        self.assertTrue(plugin.is_mitm_proof())


if __name__ == '__main__':
    unittest.main()
