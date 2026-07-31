"""
Integration tests for URI-based connection pools
"""

import unittest
import mariadb
from tests.conftest import get_test_config

# Check if mariadb_pool is available and functional
try:
    from mariadb_pool import ConnectionPoolWrapper
    HAS_MARIADB_POOL = True
except (ImportError, AttributeError):
    HAS_MARIADB_POOL = False

@unittest.skipIf(not HAS_MARIADB_POOL,
                 "mariadb_pool package not installed")
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
    
    # Honour the suite's TLS setting (ssl=False by default) unless the caller
    # already set ssl. Without this the URI connects with the secure-by-default
    # ssl=True and fails on servers without TLS (MaxScale, MariaDB 10.x).
    params = [query_params] if query_params else []
    if 'ssl' in config and 'ssl=' not in (query_params or ''):
        params.append(f"ssl={'true' if config['ssl'] else 'false'}")
    if params:
        uri += "?" + "&".join(params)

    return uri


@unittest.skipIf(not HAS_MARIADB_POOL,
                 "mariadb_pool package not installed")
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
        with mariadb.connect(uri, pool_name="test_uri_pool_1", pool_size=3) as conn1:
            self.assertIsNotNone(conn1)
            
            # Verify connection works
            with conn1.cursor() as cursor1:
                cursor1.execute("SELECT 1")
                result = cursor1.fetchone()
                self.assertEqual(result[0], 1)
        
        # Get another connection from same pool (reuse): the connection
        # arguments have to match the configuration of the pool
        with mariadb.connect(uri, pool_name="test_uri_pool_1") as conn2:
            self.assertIsNotNone(conn2)
            
            # Verify second connection works
            with conn2.cursor() as cursor2:
                cursor2.execute("SELECT 2")
                result = cursor2.fetchone()
                self.assertEqual(result[0], 2)
            
            # Verify pool is registered
            self.assertIn("test_uri_pool_1", mariadb._CONNECTION_POOLS)
        mariadb._CONNECTION_POOLS["test_uri_pool_1"].close()
    
    def test_pool_direct_instantiation_with_uri(self):
        """Test creating pool via ConnectionPool() with URI parameter"""
        config = get_test_config()
        uri = build_uri(config)
        
        # Create pool directly with URI
        with mariadb.ConnectionPool(pool_name="test_uri_pool_2", uri=uri, pool_size=3) as pool:
            self.assertIsNotNone(pool)
            
            # Get connection from pool
            with pool.get_connection() as conn:
                self.assertIsNotNone(conn)
                
                # Verify connection works
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 3")
                    result = cursor.fetchone()
                    self.assertEqual(result[0], 3)
        # Pool auto-closed by context manager

    def test_pool_uri_with_query_params(self):
        """Test pool creation with URI containing query parameters"""
        config = get_test_config()
        uri = build_uri(config, query_params="autocommit=true&pool_size=3")
        
        # Create pool with query parameters
        with mariadb.connect(uri, pool_name="test_uri_pool_3") as conn:
            self.assertIsNotNone(conn)
            
            # Verify autocommit is enabled (from URI)
            self.assertTrue(conn.autocommit)
            
            # Verify connection works
            with conn.cursor() as cursor:
                cursor.execute("SELECT 4")
                result = cursor.fetchone()
                self.assertEqual(result[0], 4)
        mariadb._CONNECTION_POOLS["test_uri_pool_3"].close()
    
    def test_pool_uri_kwarg_override(self):
        """Test that keyword arguments override URI parameters in pools"""
        config = get_test_config()
        
        # Build URI with autocommit=false
        uri = build_uri(config, query_params="autocommit=false")
        
        # Create pool but override autocommit with kwarg
        with mariadb.connect(uri, pool_name="test_uri_pool_4", autocommit=True, pool_size=3) as conn:
            self.assertIsNotNone(conn)
            
            # Verify kwarg override worked (autocommit should be True)
            self.assertTrue(conn.autocommit)
            
            with conn.cursor() as cursor:
                cursor.execute("SELECT 5")
                result = cursor.fetchone()
                self.assertEqual(result[0], 5)
        mariadb._CONNECTION_POOLS["test_uri_pool_4"].close()
    
    def test_pool_mysql_scheme(self):
        """Test pool creation with mysql:// scheme"""
        config = get_test_config()
        uri = build_uri(config, scheme='mysql')
        
        # Create pool with mysql:// scheme
        with mariadb.connect(uri, pool_name="test_uri_pool_5", pool_size=3) as conn:
            self.assertIsNotNone(conn)
            
            # Verify connection works
            with conn.cursor() as cursor:
                cursor.execute("SELECT 6")
                result = cursor.fetchone()
                self.assertEqual(result[0], 6)
        mariadb._CONNECTION_POOLS["test_uri_pool_5"].close()
    
    def test_pool_multiple_connections(self):
        """Test getting multiple connections from URI-created pool"""
        config = get_test_config()
        uri = build_uri(config, query_params="pool_size=3")
        
        # Create pool and get connections
        with mariadb.connect(uri, pool_name="test_uri_pool_6") as conn1:
            with mariadb.connect(uri, pool_name="test_uri_pool_6") as conn2:
                with mariadb.connect(uri, pool_name="test_uri_pool_6") as conn3:
                    # Verify all connections work
                    for i, conn in enumerate([conn1, conn2, conn3], 1):
                        with conn.cursor() as cursor:
                            cursor.execute(f"SELECT {i}")
                            result = cursor.fetchone()
                            self.assertEqual(result[0], i)
        mariadb._CONNECTION_POOLS["test_uri_pool_6"].close()
    
    def test_pool_uri_no_database(self):
        """Test pool creation with URI without database"""
        config = get_test_config()
        uri = build_uri(config, database='')
        
        # Create pool without database in URI
        with mariadb.connect(uri, pool_name="test_uri_pool_7", pool_size=3) as conn:
            self.assertIsNotNone(conn)
            
            # Set database after connection
            conn.database = config['database']
            
            # Verify connection works
            with conn.cursor() as cursor:
                cursor.execute("SELECT DATABASE()")
                result = cursor.fetchone()
                self.assertEqual(result[0], config['database'])
        mariadb._CONNECTION_POOLS["test_uri_pool_7"].close()
    
    def test_pool_duplicate_name_error(self):
        """Test that creating pool with duplicate name raises error"""
        config = get_test_config()
        uri = build_uri(config)
        
        # First connection creates the pool
        with mariadb.connect(uri, pool_name="test_uri_pool_dup", pool_size=3) as conn1:
            # Try to create another pool with same name
            with self.assertRaises(mariadb.PoolError) as cm:
                mariadb.ConnectionPool(pool_name="test_uri_pool_dup", uri=uri)
            
            self.assertIn("already exists", str(cm.exception))
        mariadb._CONNECTION_POOLS["test_uri_pool_dup"].close()
    
    def test_pool_without_pool_name(self):
        """Test pool can be created without pool_name for direct usage"""
        config = get_test_config()
        uri = build_uri(config)
        
        # Create pool without pool_name - should work for direct usage
        with mariadb.ConnectionPool(uri, pool_size=3) as pool:
            self.assertIsNotNone(pool)
            
            # Pool should not be registered in _CONNECTION_POOLS
            # (only named pools are registered)
            
            # Get connection from pool
            with pool.get_connection() as conn:
                self.assertIsNotNone(conn)
                
                # Verify connection works
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 13")
                    result = cursor.fetchone()
                    self.assertEqual(result[0], 13)
    
    def test_pool_uri_with_pool_name_in_query(self):
        """Test URI as first positional arg with pool_name in query params"""
        config = get_test_config()
        uri = build_uri(config, query_params="pool_name=test_uri_pool_single&pool_size=3")
        
        # Create pool with URI containing pool_name
        with mariadb.ConnectionPool(uri) as pool:
            self.assertIsNotNone(pool)
            
            # Get connection from pool
            with pool.get_connection() as conn:
                self.assertIsNotNone(conn)
                
                # Verify connection works
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 10")
                    result = cursor.fetchone()
                    self.assertEqual(result[0], 10)

    def test_pool_uri_first_arg_with_kwarg_pool_name(self): 
        """Test URI as first arg with pool_name as kwarg (kwarg takes precedence)"""
        config = get_test_config()
        uri = build_uri(config, query_params="pool_name=wrong_name")
        
        # Create pool with URI but override pool_name with kwarg
        with mariadb.ConnectionPool(uri, pool_name="test_uri_pool_override", pool_size=3) as pool:
            self.assertIsNotNone(pool)
            
            # Verify correct pool_name was used
            self.assertEqual(pool.pool_name, "test_uri_pool_override")
            self.assertIn("test_uri_pool_override", mariadb._CONNECTION_POOLS)
            self.assertNotIn("wrong_name", mariadb._CONNECTION_POOLS)
            
            with pool.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 11")
                    result = cursor.fetchone()
                    self.assertEqual(result[0], 11)


    def test_pool_traditional_first_arg_pool_name(self):
        """Test traditional style with pool_name as first positional arg"""
        config = get_test_config()
        
        # Create pool with pool_name as first arg, connection params as kwargs
        with mariadb.ConnectionPool(
            "test_uri_pool_traditional",
            host=config.get('host', 'localhost'),
            user=config.get('user', 'root'),
            password=config.get('password', ''),
            database=config.get('database', 'test'),
            port=config.get('port', 3306),
            ssl=config.get('ssl', False),
            pool_size=3,
            acquire_timeout=1
        ) as pool:
            self.assertIsNotNone(pool)
            
            with pool.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 12")
                    result = cursor.fetchone()
                    self.assertEqual(result[0], 12)

if __name__ == '__main__':
    unittest.main()
