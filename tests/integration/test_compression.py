#
# Copyright (C) 2020-2021 Georg Richter and MariaDB Corporation AB

# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Library General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.

# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Library General Public License for more details.

# You should have received a copy of the GNU Library General Public
# License along with this library; if not see <http://www.gnu.org/licenses>
# or write to the Free Software Foundation, Inc.,
# 51 Franklin St., Fifth Floor, Boston, MA 02110, USA
#

"""
Test compression functionality
"""

import unittest
import mariadb
from tests.base_test import conf


class TestCompression(unittest.TestCase):
    """Test compression functionality"""
    
    def test_compression_enabled(self):
        """Test that compression can be enabled and works"""
        config = conf()
        config['use_compression'] = True
        
        try:
            with mariadb.connect(**config) as conn:
                # Check that compression was negotiated
                from mariadb.src.constants import CAPABILITY
                self.assertTrue(conn._client.context.has_capability(CAPABILITY.COMPRESS))
                
                # Check that reader and writer have compression enabled
                self.assertTrue(conn._client.reader.use_compression)
                self.assertTrue(conn._client.writer.use_compression)
                
                # Test a simple query to ensure compression works
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1 as test_value")
                    result = cursor.fetchone()
                    self.assertEqual(result[0], 1)
                    
                    # Test a larger query that would trigger compression
                    large_string = 'x' * 2000  # Larger than MIN_COMPRESSION_SIZE (1536)
                    cursor.execute("SELECT %s as large_value", (large_string,))
                    result = cursor.fetchone()
                    self.assertEqual(result[0], large_string)
                    
        except mariadb.Error as e:
            # If server doesn't support compression, skip test
            if "compression" in str(e).lower():
                self.skipTest(f"Server doesn't support compression: {e}")
            else:
                raise
    
    def test_compression_disabled(self):
        """Test that compression is disabled by default"""
        config = conf()
        config['use_compression'] = False
        
        with mariadb.connect(**config) as conn:
            # Check that compression is not enabled
            self.assertFalse(conn._client.reader.use_compression)
            self.assertFalse(conn._client.writer.use_compression)
            
            # Test a simple query works without compression
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1 as test_value")
                result = cursor.fetchone()
                self.assertEqual(result[0], 1)
    
    def test_compression_with_init_command(self):
        """Test compression works with init commands"""
        config = conf()
        config['use_compression'] = True
        config['init_command'] = 'SET @test_var = 123'
        
        try:
            with mariadb.connect(**config) as conn:
                # Verify init command worked
                with conn.cursor() as cursor:
                    cursor.execute("SELECT @test_var")
                    result = cursor.fetchone()
                    self.assertEqual(result[0], 123)
                    
        except mariadb.Error as e:
            if "compression" in str(e).lower():
                self.skipTest(f"Server doesn't support compression: {e}")
            else:
                raise
    
    def test_compress_alias(self):
        """Test that 'compress' works as an alias for 'use_compression'"""
        config = conf()
        config['compress'] = True  # Using the alias
        
        try:
            with mariadb.connect(**config) as conn:
                # Check that compression was enabled via the alias
                self.assertTrue(conn._client.configuration.use_compression)
                self.assertTrue(conn._client.configuration.compress)
                
                # Test a simple query works
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 'compress_alias_test' as test_value")
                    result = cursor.fetchone()
                    self.assertEqual(result[0], 'compress_alias_test')
                    
        except mariadb.Error as e:
            if "compression" in str(e).lower():
                self.skipTest(f"Server doesn't support compression: {e}")
            else:
                raise


if __name__ == '__main__':
    unittest.main()
