"""
Integration tests for URI connection strings
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
    
    # Honour the suite's TLS setting (ssl=False by default) unless the caller
    # already set ssl. Without this the URI connects with the secure-by-default
    # ssl=True and fails on servers without TLS (MaxScale, MariaDB 10.x).
    params = [query_params] if query_params else []
    if 'ssl' in config and 'ssl=' not in (query_params or ''):
        params.append(f"ssl={'true' if config['ssl'] else 'false'}")
    if params:
        uri += "?" + "&".join(params)

    return uri


class TestURIConnection(unittest.TestCase):
    """Test URI-based connections"""
    
    def test_uri_basic_connection(self):
        """Test basic connection with URI"""
        config = get_test_config()
        
        # Build URI from config
        uri = build_uri(config)
        
        # Connect using URI
        conn = mariadb.connect(uri)
        self.assertIsNotNone(conn)
        
        # Verify connection works
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        self.assertEqual(result[0], 1)
        
        cursor.close()
        conn.close()
    
    def test_uri_with_query_params(self):
        """Test URI with query parameters"""
        config = get_test_config()
        
        # Build URI with query parameters
        uri = build_uri(config, query_params="autocommit=true")
        
        # Connect using URI
        conn = mariadb.connect(uri)
        self.assertIsNotNone(conn)
        self.assertTrue(conn.autocommit)
        
        conn.close()
    
    def test_uri_kwarg_override(self):
        """Test that keyword arguments override URI parameters"""
        config = get_test_config()
        
        # Skip this test if no password is configured (can't test override)
        if 'password' not in config:
            self.skipTest("Password not configured, cannot test kwarg override")
        
        # Build URI with wrong password (ssl honours the suite default so the
        # connection reaches auth on servers without TLS)
        _ssl = f"?ssl={'true' if config['ssl'] else 'false'}" if 'ssl' in config else ""
        uri = f"mariadb://{config.get('user', 'root')}:wrongpassword@{config.get('host', 'localhost')}:{config.get('port', 3306)}/{config.get('database', 'test')}{_ssl}"
        
        # Connect using URI but override password with kwarg
        conn = mariadb.connect(uri, password=config['password'])
        self.assertIsNotNone(conn)
        
        # Verify connection works
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        self.assertEqual(result[0], 1)
        
        cursor.close()
        conn.close()
    
    def test_uri_no_database(self):
        """Test URI without database specified"""
        config = get_test_config()
        
        # Build URI without database
        uri = build_uri(config, database='')
        
        # Connect using URI
        conn = mariadb.connect(uri)
        self.assertIsNotNone(conn)
        
        # Change to test database
        conn.database = config['database']
        
        # Verify connection works
        cursor = conn.cursor()
        cursor.execute("SELECT DATABASE()")
        result = cursor.fetchone()
        self.assertEqual(result[0], config['database'])
        
        cursor.close()
        conn.close()
    
    def test_uri_with_options(self):
        """Test URI with multiple options"""
        config = get_test_config()
        
        # Build URI with multiple options
        # Note: charset is not a valid parameter (always utf8mb4)
        uri = build_uri(config, query_params="autocommit=false")
        
        # Connect using URI
        conn = mariadb.connect(uri)
        self.assertIsNotNone(conn)
        self.assertFalse(conn.autocommit)
        # Verify connection works and character set is utf8mb4 by default
        cursor = conn.cursor()
        cursor.execute("SELECT @@character_set_client")
        result = cursor.fetchone()
        self.assertEqual(result[0], 'utf8mb4')
        
        cursor.close()
        conn.close()
    
    def test_uri_mysql_scheme(self):
        """Test mysql:// scheme (alias for mariadb://)"""
        config = get_test_config()
        
        # Build URI with mysql:// scheme
        uri = build_uri(config, scheme='mysql')
        
        # Connect using URI
        conn = mariadb.connect(uri)
        self.assertIsNotNone(conn)
        
        # Verify connection works
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        self.assertEqual(result[0], 1)
        
        cursor.close()
        conn.close()
    
    def test_uri_special_characters(self):
        """Test URI with URL-encoded special characters"""
        config = get_test_config()
        
        # Create a user with special characters in password (for testing)
        # Note: This test assumes we can create users, skip if not
        try:
            admin_conn = mariadb.connect(**config)
            cursor = admin_conn.cursor()
            
            # Create test user with special password
            test_user = 'uri_test_user'
            test_pass = 'p@ss:w/rd'
            
            try:
                cursor.execute(f"DROP USER IF EXISTS '{test_user}'@'%'")
                cursor.execute(f"CREATE USER '{test_user}'@'%' IDENTIFIED BY '{test_pass}'")
                cursor.execute(f"GRANT ALL PRIVILEGES ON {config['database']}.* TO '{test_user}'@'%'")
                cursor.execute("FLUSH PRIVILEGES")
                
                # Build URI with URL-encoded password
                import urllib.parse
                encoded_pass = urllib.parse.quote(test_pass, safe='')
                _ssl = f"?ssl={'true' if config['ssl'] else 'false'}" if 'ssl' in config else ""
                uri = f"mariadb://{test_user}:{encoded_pass}@{config['host']}:{config['port']}/{config['database']}{_ssl}"
                
                # Connect using URI
                test_conn = mariadb.connect(uri)
                self.assertIsNotNone(test_conn)
                
                # Verify connection works
                test_cursor = test_conn.cursor()
                test_cursor.execute("SELECT USER()")
                result = test_cursor.fetchone()
                self.assertIn(test_user, result[0])
                
                test_cursor.close()
                test_conn.close()
                
            finally:
                # Cleanup
                cursor.execute(f"DROP USER IF EXISTS '{test_user}'@'%'")
                cursor.close()
                admin_conn.close()
                
        except mariadb.Error:
            # Skip test if we can't create users
            self.skipTest("Cannot create test users")


if __name__ == '__main__':
    unittest.main()
