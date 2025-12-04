#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Caching SHA2 Password Authentication Tests for MariaDB Connector/Python (Async)

Async tests for caching_sha2_password authentication plugin including:
- Basic authentication with password
- Empty password authentication
- SSL mode authentication
- Public key retrieval
- Cache flush scenarios
"""

import unittest
import os
import sys
import platform
import asyncio

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import mariadb
from tests.base_test import create_connection, is_native, get_host_suffix
from tests.conftest import get_test_config


@unittest.skipIf(not is_native(), "AsyncConnection not available")
class TestCachingSha256AuthenticationAsync(unittest.IsolatedAsyncioTestCase):
    """Async test cases for caching_sha2_password authentication plugin"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test class - check if caching_sha2_password is available"""
        cls.connection = create_connection()
        cls.server_version = cls.connection.server_version
        
        # Check if server supports caching_sha2_password
        # MariaDB >= 12.1.1 or MySQL >= 8.0.0
        if cls.connection.server_mariadb:
            if cls.server_version < 120101:
                raise unittest.SkipTest("caching_sha2_password requires MariaDB >= 12.1.1")
            # Try to install the plugin
            try:
                cursor = cls.connection.cursor()
                cursor.execute("INSTALL SONAME 'auth_mysql_sha2'")
                cursor.close()
            except:
                pass
            with cls.connection.cursor() as cursor:
                cursor.execute("SHOW STATUS like 'Caching_sha2_password_rsa_public_key'")
                result = cursor.fetchone()
                print("Caching_sha2_password_rsa_public_key: ", result)
        else:
            if cls.server_version < 80000:
                raise unittest.SkipTest("caching_sha2_password requires MySQL >= 8.0.0")
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test class"""
        if hasattr(cls, 'connection') and cls.connection:
            cursor = cls.connection.cursor()
            # Drop all test users
            for user in ['cachingSha256UserAsync', 'cachingSha256UserAsync2', 'cachingSha256UserAsync3', 'cachingSha256UserAsync4']:
                try:
                    cursor.execute(f"DROP USER IF EXISTS '{user}'{get_host_suffix()}")
                except:
                    pass
            cursor.close()
            cls.connection.close()
    
    async def asyncSetUp(self):
        """Set up test case"""
        self.connection = create_connection()
        self.cursor = self.connection.cursor()
        
        # Create test users
        password = "!Passw0rd3Works"
        is_mariadb = self.connection.server_mariadb
        # User 1: Standard user with password
        try:
            self.cursor.execute(f"DROP USER IF EXISTS 'cachingSha256UserAsync'{get_host_suffix()}")
        except:
            pass
        keyword = "VIA" if is_mariadb else "WITH"
        password_clause = f"USING PASSWORD('{password}')" if is_mariadb else f"BY '{password}'"
        self.cursor.execute(
            f"CREATE USER 'cachingSha256UserAsync'{get_host_suffix()} "
            f"IDENTIFIED {keyword} caching_sha2_password {password_clause}"
        )
        self.cursor.execute(f"GRANT ALL PRIVILEGES ON *.* TO 'cachingSha256UserAsync'{get_host_suffix()}")
        
        # User 2: User with empty password
        try:
            self.cursor.execute(f"DROP USER IF EXISTS 'cachingSha256UserAsync2'{get_host_suffix()}")
        except:
            pass
        keyword = "VIA" if is_mariadb else "WITH"
        password_clause = "USING PASSWORD('')" if is_mariadb else "BY ''"
        self.cursor.execute(
            f"CREATE USER 'cachingSha256UserAsync2'{get_host_suffix()} "
            f"IDENTIFIED {keyword} caching_sha2_password {password_clause}"
        )
        self.cursor.execute(f"GRANT ALL PRIVILEGES ON *.* TO 'cachingSha256UserAsync2'{get_host_suffix()}")
        
        # User 3: Another standard user
        try:
            self.cursor.execute(f"DROP USER IF EXISTS 'cachingSha256UserAsync3'{get_host_suffix()}")
        except:
            pass
        keyword = "VIA" if is_mariadb else "WITH"
        password_clause = f"USING PASSWORD('{password}')" if is_mariadb else f"BY '{password}'"
        self.cursor.execute(
            f"CREATE USER 'cachingSha256UserAsync3'{get_host_suffix()} "
            f"IDENTIFIED {keyword} caching_sha2_password {password_clause}"
        )
        self.cursor.execute(f"GRANT ALL PRIVILEGES ON *.* TO 'cachingSha256UserAsync3'{get_host_suffix()}")
        
        # User 4: Another standard user
        try:
            self.cursor.execute(f"DROP USER IF EXISTS 'cachingSha256UserAsync4'{get_host_suffix()}")
        except:
            pass
        keyword = "VIA" if is_mariadb else "WITH"
        password_clause = f"USING PASSWORD('{password}')" if is_mariadb else f"BY '{password}'"
        self.cursor.execute(
            f"CREATE USER 'cachingSha256UserAsync4'{get_host_suffix()} "
            f"IDENTIFIED {keyword} caching_sha2_password {password_clause}"
        )
        self.cursor.execute(f"GRANT ALL PRIVILEGES ON *.* TO 'cachingSha256UserAsync4'{get_host_suffix()}")
        
        self.cursor.execute("FLUSH PRIVILEGES")
        self.connection.commit()
    
    async def asyncTearDown(self):
        """Clean up test case"""
        if hasattr(self, 'cursor') and self.cursor:
            self.cursor.close()
        if hasattr(self, 'connection') and self.connection:
            self.connection.close()
    
    async def test_caching_sha256_empty_password(self):
        """Test caching_sha2_password authentication with empty password"""
        # Skip on Windows
        if platform.system() == "Windows":
            self.skipTest("Skipping on Windows")
        
        self.cursor.execute("FLUSH PRIVILEGES")  # Reset cache
        
        conn_config = get_test_config().copy()
        conn_config['user'] = 'cachingSha256UserAsync2'
        conn_config['password'] = ''
        
        # Connect with empty password
        sha256_conn = await mariadb.AsyncConnection.connect(**conn_config)
        self.assertIsNotNone(sha256_conn)
        await sha256_conn.ping()
        await sha256_conn.close()
    
    async def test_caching_sha256_with_ssl(self):
        """Test caching_sha2_password authentication with SSL"""
        # Check if SSL is available
        test_config = get_test_config()
        if not test_config.get('ssl_ca'):
            self.skipTest("SSL not configured")
        
        self.cursor.execute("FLUSH PRIVILEGES")  # Reset cache
        
        conn_config = get_test_config().copy()
        conn_config['user'] = 'cachingSha256UserAsync'
        conn_config['password'] = '!Passw0rd3Works'
        conn_config['ssl'] = True
        conn_config['ssl_verify_cert'] = False  # Trust mode
        
        # Connect with SSL
        sha256_conn = await mariadb.AsyncConnection.connect(**conn_config)
        self.assertIsNotNone(sha256_conn)
        await sha256_conn.ping()
        await sha256_conn.close()
    
    async def test_caching_sha256_basic_authentication(self):
        """Test basic caching_sha2_password authentication"""
        self.cursor.execute("FLUSH PRIVILEGES")  # Reset cache
        
        conn_config = get_test_config().copy()
        conn_config['user'] = 'cachingSha256UserAsync3'
        conn_config['password'] = '!Passw0rd3Works'
        
        # First connection - not cached
        sha256_conn = await mariadb.AsyncConnection.connect(**conn_config)
        self.assertIsNotNone(sha256_conn)
        await sha256_conn.ping()
        await sha256_conn.close()
        
        # Second connection - should use cache
        sha256_conn = await mariadb.AsyncConnection.connect(**conn_config)
        self.assertIsNotNone(sha256_conn)
        await sha256_conn.ping()
        await sha256_conn.close()
    
    async def test_caching_sha256_wrong_password(self):
        """Test caching_sha2_password authentication with wrong password"""
        self.cursor.execute("FLUSH PRIVILEGES")  # Reset cache
        
        conn_config = get_test_config().copy()
        conn_config['user'] = 'cachingSha256UserAsync'
        conn_config['password'] = 'WrongPassword123'
        
        # Should fail with authentication error
        with self.assertRaises(mariadb.OperationalError) as cm:
            await mariadb.AsyncConnection.connect(**conn_config)
        
        error_msg = str(cm.exception)
        self.assertTrue(
            'Access denied' in error_msg or 
            'authentication' in error_msg.lower(),
            f"Expected authentication error, got: {error_msg}"
        )
    
    async def test_caching_sha256_multiple_connections(self):
        """Test multiple connections with caching_sha2_password"""
        self.cursor.execute("FLUSH PRIVILEGES")  # Reset cache
        
        conn_config = get_test_config().copy()
        conn_config['user'] = 'cachingSha256UserAsync4'
        conn_config['password'] = '!Passw0rd3Works'
        
        connections = []
        try:
            # Create multiple connections
            for i in range(3):
                conn = await mariadb.AsyncConnection.connect(**conn_config)
                self.assertIsNotNone(conn)
                cursor = conn.cursor()
                await cursor.execute("SELECT USER()")
                user_result = await cursor.fetchone()
                self.assertIn('cachingSha256UserAsync4', user_result[0])
                await cursor.close()
                connections.append(conn)
            
            # All connections should be valid
            for conn in connections:
                await conn.ping()
        
        finally:
            # Clean up connections
            for conn in connections:
                try:
                    await conn.close()
                except:
                    pass
    
    async def test_caching_sha256_after_cache_flush(self):
        """Test authentication after cache flush"""
        conn_config = get_test_config().copy()
        conn_config['user'] = 'cachingSha256UserAsync'
        conn_config['password'] = '!Passw0rd3Works'
        
        # First connection
        sha256_conn = await mariadb.AsyncConnection.connect(**conn_config)
        await sha256_conn.ping()
        await sha256_conn.close()
        
        # Flush privileges to clear cache
        self.cursor.execute("FLUSH PRIVILEGES")
        
        # Second connection after cache flush
        sha256_conn = await mariadb.AsyncConnection.connect(**conn_config)
        await sha256_conn.ping()
        await sha256_conn.close()
    
    async def test_caching_sha256_user_query(self):
        """Test that we can query user information"""
        self.cursor.execute("FLUSH PRIVILEGES")  # Reset cache
        
        conn_config = get_test_config().copy()
        conn_config['user'] = 'cachingSha256UserAsync'
        conn_config['password'] = '!Passw0rd3Works'
        
        sha256_conn = await mariadb.AsyncConnection.connect(**conn_config)
        cursor = sha256_conn.cursor()
        
        # Check current user
        await cursor.execute("SELECT USER()")
        user_result = await cursor.fetchone()
        self.assertIn('cachingSha256UserAsync', user_result[0])
        
        # Check current database operations work
        await cursor.execute("SELECT 1")
        result = await cursor.fetchone()
        self.assertEqual(result[0], 1)
        
        await cursor.close()
        await sha256_conn.close()


if __name__ == '__main__':
    unittest.main()
