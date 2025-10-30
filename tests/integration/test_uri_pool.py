"""
Integration tests for URI-based connection pools
"""

import unittest
import mariadb
from tests.conftest import get_test_config


def build_uri(config, scheme='mariadb', database=None, query_params=None):
    """Helper function to build URI from config with optional password"""
    user = config.get('user', 'root')
    password = config.get('password', '')
    host = config.get('host', 'localhost')
    port = config.get('port', 3306)
    db = database if database is not None else config.get('database', '')
    
    # Build user:password part
    if password:
        auth = f"{user}:{password}"
    else:
        auth = user
    
    # Build base URI
    if db:
        uri = f"{scheme}://{auth}@{host}:{port}/{db}"
    else:
        uri = f"{scheme}://{auth}@{host}:{port}"
    
    # Add query parameters if provided
    if query_params:
        uri += "?" + query_params
    
    return uri


class TestURIPool(unittest.TestCase):
    """Test URI-based connection pools"""
    
    def tearDown(self):
        """Clean up any pools created during tests"""
        # Clean up mariadb pools
        pools_to_remove = []
        for pool_name in mariadb._CONNECTION_POOLS:
            if pool_name.startswith('test_uri_pool_'):
                pools_to_remove.append(pool_name)
        
        for pool_name in pools_to_remove:
            try:
                mariadb._CONNECTION_POOLS[pool_name].close()
            except:
                pass
    
    def test_pool_via_connect_with_uri(self):
        """Test creating pool via connect() with URI"""
        config = get_test_config()
        uri = build_uri(config)
        
        # Create pool via connect with URI
        conn1 = mariadb.connect(uri, pool_name="test_uri_pool_1")
        self.assertIsNotNone(conn1)
        
        # Verify connection works
        cursor1 = conn1.cursor()
        cursor1.execute("SELECT 1")
        result = cursor1.fetchone()
        self.assertEqual(result[0], 1)
        cursor1.close()
        
        # Get another connection from same pool (reuse)
        conn2 = mariadb.connect(pool_name="test_uri_pool_1")
        self.assertIsNotNone(conn2)
        
        # Verify second connection works
        cursor2 = conn2.cursor()
        cursor2.execute("SELECT 2")
        result = cursor2.fetchone()
        self.assertEqual(result[0], 2)
        cursor2.close()
        
        # Verify pool is registered
        self.assertIn("test_uri_pool_1", mariadb._CONNECTION_POOLS)
        
        conn1.close()
        conn2.close()
    
    def test_pool_direct_instantiation_with_uri(self):
        """Test creating pool via ConnectionPool() with URI parameter"""
        config = get_test_config()
        uri = build_uri(config)
        
        # Create pool directly with URI
        pool = mariadb.ConnectionPool(pool_name="test_uri_pool_2", uri=uri)
        self.assertIsNotNone(pool)
        
        # Get connection from pool
        conn = pool.get_connection()
        self.assertIsNotNone(conn)
        
        # Verify connection works
        cursor = conn.cursor()
        cursor.execute("SELECT 3")
        result = cursor.fetchone()
        self.assertEqual(result[0], 3)
        
        cursor.close()
        conn.close()
        pool.close()
    
    def test_pool_uri_with_query_params(self):
        """Test pool creation with URI containing query parameters"""
        config = get_test_config()
        uri = build_uri(config, query_params="autocommit=true&pool_size=5")
        
        # Create pool with query parameters
        conn = mariadb.connect(uri, pool_name="test_uri_pool_3")
        self.assertIsNotNone(conn)
        
        # Verify autocommit is enabled (from URI)
        self.assertTrue(conn.autocommit)
        
        # Verify connection works
        cursor = conn.cursor()
        cursor.execute("SELECT 4")
        result = cursor.fetchone()
        self.assertEqual(result[0], 4)
        
        cursor.close()
        conn.close()
    
    def test_pool_uri_kwarg_override(self):
        """Test that keyword arguments override URI parameters in pools"""
        config = get_test_config()
        
        # Build URI with autocommit=false
        uri = build_uri(config, query_params="autocommit=false")
        
        # Create pool but override autocommit with kwarg
        conn = mariadb.connect(uri, pool_name="test_uri_pool_4", autocommit=True)
        self.assertIsNotNone(conn)
        
        # Verify kwarg override worked (autocommit should be True)
        self.assertTrue(conn.autocommit)
        
        cursor = conn.cursor()
        cursor.execute("SELECT 5")
        result = cursor.fetchone()
        self.assertEqual(result[0], 5)
        
        cursor.close()
        conn.close()
    
    def test_pool_mysql_scheme(self):
        """Test pool creation with mysql:// scheme"""
        config = get_test_config()
        uri = build_uri(config, scheme='mysql')
        
        # Create pool with mysql:// scheme
        conn = mariadb.connect(uri, pool_name="test_uri_pool_5")
        self.assertIsNotNone(conn)
        
        # Verify connection works
        cursor = conn.cursor()
        cursor.execute("SELECT 6")
        result = cursor.fetchone()
        self.assertEqual(result[0], 6)
        
        cursor.close()
        conn.close()
    
    def test_pool_multiple_connections(self):
        """Test getting multiple connections from URI-created pool"""
        config = get_test_config()
        uri = build_uri(config, query_params="pool_size=3")
        
        # Create pool
        conn1 = mariadb.connect(uri, pool_name="test_uri_pool_6")
        
        # Get additional connections from pool
        conn2 = mariadb.connect(pool_name="test_uri_pool_6")
        conn3 = mariadb.connect(pool_name="test_uri_pool_6")
        
        # Verify all connections work
        for i, conn in enumerate([conn1, conn2, conn3], 1):
            cursor = conn.cursor()
            cursor.execute(f"SELECT {i}")
            result = cursor.fetchone()
            self.assertEqual(result[0], i)
            cursor.close()
        
        # Close all connections
        conn1.close()
        conn2.close()
        conn3.close()
    
    def test_pool_uri_no_database(self):
        """Test pool creation with URI without database"""
        config = get_test_config()
        uri = build_uri(config, database='')
        
        # Create pool without database in URI
        conn = mariadb.connect(uri, pool_name="test_uri_pool_7")
        self.assertIsNotNone(conn)
        
        # Set database after connection
        conn.database = config['database']
        
        # Verify connection works
        cursor = conn.cursor()
        cursor.execute("SELECT DATABASE()")
        result = cursor.fetchone()
        self.assertEqual(result[0], config['database'])
        
        cursor.close()
        conn.close()
    
    def test_pool_duplicate_name_error(self):
        """Test that creating pool with duplicate name raises error"""
        config = get_test_config()
        uri = build_uri(config)
        
        # Create first pool
        conn1 = mariadb.connect(uri, pool_name="test_uri_pool_dup")
        
        # Try to create another pool with same name
        with self.assertRaises(mariadb.PoolError) as cm:
            mariadb.ConnectionPool(pool_name="test_uri_pool_dup", uri=uri)
        
        self.assertIn("already exists", str(cm.exception))
        
        conn1.close()
    
    def test_pool_missing_pool_name_error(self):
        """Test that ConnectionPool requires pool_name"""
        config = get_test_config()
        uri = build_uri(config)
        
        # Try to create pool without pool_name
        with self.assertRaises(mariadb.ProgrammingError) as cm:
            mariadb.ConnectionPool(uri=uri)
        
        self.assertIn("pool_name is required", str(cm.exception))


if __name__ == '__main__':
    unittest.main()
