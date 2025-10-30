"""
Unit tests for URI parser
"""

import unittest
from mariadb_shared.uri_parser import parse_connection_uri, is_connection_uri


class TestURIParser(unittest.TestCase):
    """Test URI parsing functionality"""
    
    def test_is_connection_uri(self):
        """Test URI detection"""
        self.assertTrue(is_connection_uri("mariadb://localhost"))
        self.assertTrue(is_connection_uri("mysql://localhost"))
        self.assertFalse(is_connection_uri("localhost"))
        self.assertFalse(is_connection_uri(""))
        self.assertFalse(is_connection_uri(None))
        self.assertFalse(is_connection_uri(123))
    
    def test_basic_uri(self):
        """Test basic URI parsing"""
        result = parse_connection_uri("mariadb://localhost")
        self.assertEqual(result['host'], 'localhost')
        self.assertNotIn('port', result)
        self.assertNotIn('user', result)
        self.assertNotIn('password', result)
        self.assertNotIn('database', result)
    
    def test_full_uri(self):
        """Test full URI with all components"""
        result = parse_connection_uri("mariadb://root:secret@localhost:3306/mydb")
        self.assertEqual(result['user'], 'root')
        self.assertEqual(result['password'], 'secret')
        self.assertEqual(result['host'], 'localhost')
        self.assertEqual(result['port'], 3306)
        self.assertEqual(result['database'], 'mydb')
    
    def test_uri_with_query_params(self):
        """Test URI with query parameters"""
        result = parse_connection_uri("mariadb://localhost/mydb?charset=utf8mb4&ssl=true")
        self.assertEqual(result['host'], 'localhost')
        self.assertEqual(result['database'], 'mydb')
        self.assertEqual(result['charset'], 'utf8mb4')
        self.assertTrue(result['ssl'])
    
    def test_uri_boolean_params(self):
        """Test boolean parameter conversion"""
        # Test true values
        result = parse_connection_uri("mariadb://localhost?ssl=true&compress=1&autocommit=yes")
        self.assertTrue(result['ssl'])
        self.assertTrue(result['compress'])
        self.assertTrue(result['autocommit'])
        
        # Test false values
        result = parse_connection_uri("mariadb://localhost?ssl=false&compress=0&autocommit=no")
        self.assertFalse(result['ssl'])
        self.assertFalse(result['compress'])
        self.assertFalse(result['autocommit'])
    
    def test_uri_numeric_params(self):
        """Test numeric parameter conversion"""
        result = parse_connection_uri("mariadb://localhost?port=3307&connect_timeout=30")
        self.assertEqual(result['port'], 3307)
        self.assertEqual(result['connect_timeout'], 30)
    
    def test_uri_url_encoding(self):
        """Test URL-encoded values"""
        result = parse_connection_uri("mariadb://user%40host:p%40ssw0rd@localhost/my%20db")
        self.assertEqual(result['user'], 'user@host')
        self.assertEqual(result['password'], 'p@ssw0rd')
        self.assertEqual(result['database'], 'my db')
    
    def test_uri_no_database(self):
        """Test URI without database"""
        result = parse_connection_uri("mariadb://root:secret@localhost:3306")
        self.assertEqual(result['user'], 'root')
        self.assertEqual(result['password'], 'secret')
        self.assertEqual(result['host'], 'localhost')
        self.assertEqual(result['port'], 3306)
        self.assertNotIn('database', result)
    
    def test_uri_no_password(self):
        """Test URI without password"""
        result = parse_connection_uri("mariadb://root@localhost/mydb")
        self.assertEqual(result['user'], 'root')
        self.assertNotIn('password', result)
        self.assertEqual(result['host'], 'localhost')
        self.assertEqual(result['database'], 'mydb')
    
    def test_uri_mysql_scheme(self):
        """Test mysql:// scheme (alias for mariadb://)"""
        result = parse_connection_uri("mysql://root:secret@localhost:3306/mydb")
        self.assertEqual(result['user'], 'root')
        self.assertEqual(result['password'], 'secret')
        self.assertEqual(result['host'], 'localhost')
        self.assertEqual(result['port'], 3306)
        self.assertEqual(result['database'], 'mydb')
    
    def test_uri_invalid_scheme(self):
        """Test invalid URI scheme"""
        with self.assertRaises(ValueError) as cm:
            parse_connection_uri("postgresql://localhost")
        self.assertIn("Invalid URI scheme", str(cm.exception))
    
    def test_uri_complex_query_params(self):
        """Test complex query parameters"""
        result = parse_connection_uri(
            "mariadb://localhost/mydb?charset=utf8mb4&ssl=true&"
            "ssl_ca=/path/to/ca.pem&connect_timeout=10"
        )
        self.assertEqual(result['charset'], 'utf8mb4')
        self.assertTrue(result['ssl'])
        self.assertEqual(result['ssl_ca'], '/path/to/ca.pem')
        self.assertEqual(result['connect_timeout'], 10)
    
    def test_uri_empty_password(self):
        """Test URI with empty password"""
        result = parse_connection_uri("mariadb://root:@localhost/mydb")
        self.assertEqual(result['user'], 'root')
        self.assertEqual(result['password'], '')
        self.assertEqual(result['host'], 'localhost')
        self.assertEqual(result['database'], 'mydb')


if __name__ == '__main__':
    unittest.main()
