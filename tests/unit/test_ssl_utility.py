"""
Unit tests for SSLUtility class
"""

import unittest
import ssl
import warnings
import sys
from pathlib import Path

# Add the mariadb source module to the path BEFORE importing
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from mariadb.impl.client.ssl.ssl_utility import SSLUtility
from mariadb.impl.configuration import Configuration


class TestSSLUtility(unittest.TestCase):
    """Test SSLUtility functionality"""
    
    def test_configure_tls_versions_single_tlsv1_3(self):
        """Test configuring single TLS version 1.3"""
        context = ssl.create_default_context()
        config = Configuration()
        config.tls_version = "TLSv1.3"
        
        SSLUtility._configure_tls_versions(context, config)
        
        self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1_3)
        self.assertEqual(context.maximum_version, ssl.TLSVersion.TLSv1_3)
    
    def test_configure_tls_versions_single_tlsv1_2(self):
        """Test configuring single TLS version 1.2"""
        context = ssl.create_default_context()
        config = Configuration()
        config.tls_version = "TLSv1.2"
        
        SSLUtility._configure_tls_versions(context, config)
        
        self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
        self.assertEqual(context.maximum_version, ssl.TLSVersion.TLSv1_2)
    
    def test_configure_tls_versions_multiple(self):
        """Test configuring multiple TLS versions"""
        context = ssl.create_default_context()
        config = Configuration()
        config.tls_version = "TLSv1.2,TLSv1.3"
        
        SSLUtility._configure_tls_versions(context, config)
        
        self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
        self.assertEqual(context.maximum_version, ssl.TLSVersion.TLSv1_3)
    
    def test_configure_tls_versions_multiple_reverse_order(self):
        """Test configuring multiple TLS versions in reverse order"""
        context = ssl.create_default_context()
        config = Configuration()
        config.tls_version = "TLSv1.3,TLSv1.2"
        
        SSLUtility._configure_tls_versions(context, config)
        
        # Should still set min to 1.2 and max to 1.3
        self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
        self.assertEqual(context.maximum_version, ssl.TLSVersion.TLSv1_3)
    
    def test_configure_tls_versions_case_insensitive(self):
        """Test TLS version parsing is case insensitive"""
        context = ssl.create_default_context()
        config = Configuration()
        config.tls_version = "tlsv1.2"
        
        SSLUtility._configure_tls_versions(context, config)
        
        self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
        self.assertEqual(context.maximum_version, ssl.TLSVersion.TLSv1_2)
    
    def test_configure_tls_versions_underscore_format(self):
        """Test TLS version with underscore format"""
        context = ssl.create_default_context()
        config = Configuration()
        config.tls_version = "TLSv1_3"
        
        SSLUtility._configure_tls_versions(context, config)
        
        self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1_3)
        self.assertEqual(context.maximum_version, ssl.TLSVersion.TLSv1_3)
    
    def test_configure_tls_versions_uppercase(self):
        """Test TLS version with uppercase format"""
        context = ssl.create_default_context()
        config = Configuration()
        config.tls_version = "TLSV1_2"
        
        SSLUtility._configure_tls_versions(context, config)
        
        self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
        self.assertEqual(context.maximum_version, ssl.TLSVersion.TLSv1_2)
    
    def test_configure_tls_versions_short_format(self):
        """Test TLS version with short format (TLS1_3)"""
        context = ssl.create_default_context()
        config = Configuration()
        config.tls_version = "TLS1_3"
        
        SSLUtility._configure_tls_versions(context, config)
        
        self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1_3)
        self.assertEqual(context.maximum_version, ssl.TLSVersion.TLSv1_3)
    
    def test_configure_tls_versions_with_spaces(self):
        """Test TLS version list with spaces"""
        context = ssl.create_default_context()
        config = Configuration()
        config.tls_version = " TLSv1.2 , TLSv1.3 "
        
        SSLUtility._configure_tls_versions(context, config)
        
        self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
        self.assertEqual(context.maximum_version, ssl.TLSVersion.TLSv1_3)
    
    def test_configure_tls_versions_invalid_single(self):
        """Test invalid single TLS version triggers warning"""
        context = ssl.create_default_context()
        config = Configuration()
        config.tls_version = "TLSv9.9"
        
        # Store original min/max
        original_min = context.minimum_version
        original_max = context.maximum_version
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            SSLUtility._configure_tls_versions(context, config)
            
            # Should have warning
            self.assertEqual(len(w), 1)
            self.assertIn("Unsupported TLS version", str(w[0].message))
        
        # Should keep original values
        self.assertEqual(context.minimum_version, original_min)
        self.assertEqual(context.maximum_version, original_max)
    
    def test_configure_tls_versions_invalid_in_list(self):
        """Test invalid TLS version in list triggers warning but processes valid ones"""
        context = ssl.create_default_context()
        config = Configuration()
        config.tls_version = "TLSv1.2,TLSv9.9,TLSv1.3"
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            SSLUtility._configure_tls_versions(context, config)
            
            # Should have warning for invalid version
            self.assertEqual(len(w), 1)
            self.assertIn("Unsupported TLS version", str(w[0].message))
        
        # Should still configure valid versions
        self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
        self.assertEqual(context.maximum_version, ssl.TLSVersion.TLSv1_3)
    
    def test_configure_tls_versions_all_invalid_in_list(self):
        """Test all invalid TLS versions in list triggers warning"""
        context = ssl.create_default_context()
        config = Configuration()
        config.tls_version = "TLSv9.9,TLSv8.8"
        
        # Store original min/max
        original_min = context.minimum_version
        original_max = context.maximum_version
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            SSLUtility._configure_tls_versions(context, config)
            
            # Should have warnings for each invalid version plus one for no valid versions
            self.assertGreaterEqual(len(w), 2)
        
        # Should keep original values
        self.assertEqual(context.minimum_version, original_min)
        self.assertEqual(context.maximum_version, original_max)
    
    def test_configure_tls_versions_three_versions(self):
        """Test configuring three TLS versions"""
        context = ssl.create_default_context()
        config = Configuration()
        config.tls_version = "TLSv1.1,TLSv1.2,TLSv1.3"
        
        SSLUtility._configure_tls_versions(context, config)
        
        # Should set min to lowest (1.1) and max to highest (1.3)
        self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1_1)
        self.assertEqual(context.maximum_version, ssl.TLSVersion.TLSv1_3)
    
    def test_configure_tls_versions_tlsv1(self):
        """Test configuring TLS version 1.0"""
        context = ssl.create_default_context()
        config = Configuration()
        config.tls_version = "TLSv1"
        
        SSLUtility._configure_tls_versions(context, config)
        
        self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1)
        self.assertEqual(context.maximum_version, ssl.TLSVersion.TLSv1)
    
    def test_configure_tls_versions_mixed_formats(self):
        """Test configuring with mixed format versions"""
        context = ssl.create_default_context()
        config = Configuration()
        config.tls_version = "TLSv1_2,TLSV1.3,tls1_1"
        
        SSLUtility._configure_tls_versions(context, config)
        
        self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1_1)
        self.assertEqual(context.maximum_version, ssl.TLSVersion.TLSv1_3)


if __name__ == '__main__':
    unittest.main()
