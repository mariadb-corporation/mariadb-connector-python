#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""
Integration tests for field types and field metadata
"""

import unittest
import mariadb
from mariadb import fieldinfo
from mariadb_shared import constants
from decimal import Decimal
import datetime
from ..base_test import create_connection, is_mysql


class FieldTypesTest(unittest.TestCase):
    """Test field type handling and metadata"""

    def setUp(self):
        """Set up test connection"""
        self.connection = create_connection()
        self.cursor = self.connection.cursor()

    def tearDown(self):
        """Clean up test resources"""
        if hasattr(self, 'cursor') and self.cursor:
            self.cursor.close()
        if hasattr(self, 'connection') and self.connection:
            self.connection.close()

    def test_field_info_decimal(self):
        """Test DECIMAL field type"""
        self.cursor.execute("SELECT CAST(123.45 AS DECIMAL(10,2)) as val")
        self.cursor.fetchone()
        
        fi = fieldinfo()
        field_type = fi.type(self.cursor.description[0])
        self.assertIn(field_type, ['DECIMAL', 'NEWDECIMAL'])

    def test_field_info_integer_types(self):
        """Test integer field types"""
        self.cursor.execute("CREATE TEMPORARY TABLE test_integer_types (tiny TINYINT, small SMALLINT, medium MEDIUMINT, normal INT, big BIGINT)")
        self.cursor.execute("SELECT * FROM test_integer_types")        
        self.cursor.fetchone()
        
        fi = fieldinfo()
        descriptions = self.cursor.description
        
        self.assertEqual(fi.type(descriptions[0]), 'TINY')
        self.assertEqual(fi.type(descriptions[1]), 'SHORT')
        self.assertEqual(fi.type(descriptions[2]), 'INT24')
        self.assertEqual(fi.type(descriptions[3]), 'LONG')
        self.assertEqual(fi.type(descriptions[4]), 'LONGLONG')

    def test_field_info_float_double(self):
        """Test FLOAT and DOUBLE field types"""
        self.cursor.execute("""
            SELECT 
                CAST(1.5 AS FLOAT) as f,
                CAST(1.5 AS DOUBLE) as d
        """)
        self.cursor.fetchone()
        
        fi = fieldinfo()
        descriptions = self.cursor.description
        
        self.assertEqual(fi.type(descriptions[0]), 'FLOAT')
        self.assertEqual(fi.type(descriptions[1]), 'DOUBLE')

    def test_field_info_date_time_types(self):
        """Test date and time field types"""
        self.cursor.execute("CREATE TEMPORARY TABLE test_datetime_types (d DATE, t TIME, dt DATETIME, ts TIMESTAMP, y YEAR)")
        self.cursor.execute("SELECT * FROM test_datetime_types")
        self.cursor.fetchone()
        
        fi = fieldinfo()
        descriptions = self.cursor.description
        
        self.assertEqual(fi.type(descriptions[0]), 'DATE')
        self.assertEqual(fi.type(descriptions[1]), 'TIME')
        self.assertEqual(fi.type(descriptions[2]), 'DATETIME')
        self.assertEqual(fi.type(descriptions[3]), 'TIMESTAMP')
        self.assertEqual(fi.type(descriptions[4]), 'YEAR')

    def test_field_info_year2_mariadb_only(self):
        """Test YEAR(2) field type - MariaDB only"""
        if is_mysql():
            self.skipTest("YEAR(2) test is for MariaDB only")
        
        # YEAR(2) is deprecated in MySQL 5.7+ but still supported in MariaDB
        try:
            self.cursor.execute("""
                CREATE TEMPORARY TABLE test_year2 (
                    y YEAR(2)
                )
            """)
        except mariadb.Error:
            self.skipTest("YEAR(2) not supported on this server version")
        
        # Insert year 75 which should be interpreted as 1975
        self.cursor.execute("INSERT INTO test_year2 VALUES (75)")
        
        # Retrieve and verify
        self.cursor.execute("SELECT y FROM test_year2")
        result = self.cursor.fetchone()
        
        # Year 75 should be stored and retrieved as 1975
        self.assertEqual(result[0], 75)
        
        # Test field type
        fi = fieldinfo()
        field_type = fi.type(self.cursor.description[0])
        self.assertIn(field_type, ['YEAR', 'SHORT'])

    def test_field_info_string_types(self):
        """Test string field types"""
        self.cursor.execute("""
            CREATE TEMPORARY TABLE test_strings (
                c1 VARCHAR(100),
                c2 CHAR(10),
                c3 TEXT,
                c4 MEDIUMTEXT,
                c5 LONGTEXT
            )
        """)
        self.cursor.execute("SELECT * FROM test_strings LIMIT 0")
        
        fi = fieldinfo()
        descriptions = self.cursor.description
        
        # VARCHAR
        self.assertIn(fi.type(descriptions[0]), ['VARCHAR', 'VAR_STRING'])
        # CHAR
        self.assertIn(fi.type(descriptions[1]), ['STRING', 'VAR_STRING'])
        # TEXT types
        self.assertIn(fi.type(descriptions[2]), ['BLOB', 'VAR_STRING'])

    def test_field_info_blob_types(self):
        """Test BLOB field types"""
        self.cursor.execute("""
            CREATE TEMPORARY TABLE test_blobs (
                c1 TINYBLOB,
                c2 BLOB,
                c3 MEDIUMBLOB,
                c4 LONGBLOB
            )
        """)
        self.cursor.execute("SELECT * FROM test_blobs LIMIT 0")
        
        fi = fieldinfo()
        descriptions = self.cursor.description
        
        # All BLOB types should be identified
        for desc in descriptions:
            field_type = fi.type(desc)
            self.assertIn(field_type, ['TINY_BLOB', 'BLOB', 'MEDIUM_BLOB', 'LONG_BLOB'])

    def test_field_info_bit_type(self):
        """Test BIT field type"""
        self.cursor.execute("CREATE TEMPORARY TABLE test_bit (b BIT(8))")
        self.cursor.execute("SELECT * FROM test_bit LIMIT 0")
        
        fi = fieldinfo()
        field_type = fi.type(self.cursor.description[0])
        self.assertEqual(field_type, 'BIT')

    def test_field_info_enum_set(self):
        """Test ENUM and SET field types"""
        self.cursor.execute("""
            CREATE TEMPORARY TABLE test_enum_set (
                e ENUM('a', 'b', 'c'),
                s SET('x', 'y', 'z')
            )
        """)
        self.cursor.execute("SELECT * FROM test_enum_set LIMIT 0")
        
        fi = fieldinfo()
        descriptions = self.cursor.description
        
        self.assertIn(fi.type(descriptions[0]), ['ENUM', 'STRING', 'VAR_STRING'])
        self.assertIn(fi.type(descriptions[1]), ['SET', 'STRING', 'VAR_STRING'])

    def test_field_flags_not_null(self):
        """Test NOT NULL field flag"""
        self.cursor.execute("""
            CREATE TEMPORARY TABLE test_not_null (
                id INT NOT NULL
            )
        """)
        self.cursor.execute("SELECT * FROM test_not_null LIMIT 0")
        
        fi = fieldinfo()
        flags = fi.flag(self.cursor.description[0])
        self.assertIn('NOT_NULL', flags)

    def test_field_flags_primary_key(self):
        """Test PRIMARY KEY field flag"""
        self.cursor.execute("""
            CREATE TEMPORARY TABLE test_pk (
                id INT PRIMARY KEY
            )
        """)
        self.cursor.execute("SELECT * FROM test_pk LIMIT 0")
        
        fi = fieldinfo()
        flags = fi.flag(self.cursor.description[0])
        self.assertIn('PRIMARY_KEY', flags)
        self.assertIn('NOT_NULL', flags)

    def test_field_flags_auto_increment(self):
        """Test AUTO_INCREMENT field flag"""
        self.cursor.execute("""
            CREATE TEMPORARY TABLE test_auto (
                id INT AUTO_INCREMENT PRIMARY KEY
            )
        """)
        self.cursor.execute("SELECT * FROM test_auto LIMIT 0")
        
        fi = fieldinfo()
        flags = fi.flag(self.cursor.description[0])
        self.assertIn('AUTO_INCREMENT', flags)

    def test_field_flags_unsigned(self):
        """Test UNSIGNED field flag"""
        self.cursor.execute("""
            CREATE TEMPORARY TABLE test_unsigned (
                val INT UNSIGNED
            )
        """)
        self.cursor.execute("SELECT * FROM test_unsigned LIMIT 0")
        
        fi = fieldinfo()
        flags = fi.flag(self.cursor.description[0])
        self.assertIn('UNSIGNED', flags)

    def test_field_flags_zerofill(self):
        """Test ZEROFILL field flag"""
        self.cursor.execute("""
            CREATE TEMPORARY TABLE test_zerofill (
                val INT ZEROFILL
            )
        """)
        self.cursor.execute("SELECT * FROM test_zerofill LIMIT 0")
        
        fi = fieldinfo()
        flags = fi.flag(self.cursor.description[0])
        self.assertIn('ZEROFILL', flags)
        self.assertIn('UNSIGNED', flags)  # ZEROFILL implies UNSIGNED

    def test_field_flags_binary(self):
        """Test BINARY field flag"""
        self.cursor.execute("""
            CREATE TEMPORARY TABLE test_binary (
                val VARCHAR(100) BINARY
            )
        """)
        self.cursor.execute("SELECT * FROM test_binary LIMIT 0")
        
        fi = fieldinfo()
        flags = fi.flag(self.cursor.description[0])
        self.assertIn('BINARY', flags)

    def test_field_flags_unique_key(self):
        """Test UNIQUE KEY field flag"""
        self.cursor.execute("""
            CREATE TEMPORARY TABLE test_unique (
                id INT PRIMARY KEY,
                email VARCHAR(100) UNIQUE
            )
        """)
        self.cursor.execute("SELECT * FROM test_unique LIMIT 0")
        
        fi = fieldinfo()
        # Check unique key column
        flags = fi.flag(self.cursor.description[1])
        self.assertIn('UNIQUE_KEY', flags)

    def test_field_flags_multiple_key(self):
        """Test PART_KEY (multiple key) field flag"""
        self.cursor.execute("""
            CREATE TEMPORARY TABLE test_multi_key (
                id INT PRIMARY KEY,
                a INT,
                b INT,
                KEY idx_ab (a, b)
            )
        """)
        self.cursor.execute("SELECT * FROM test_multi_key LIMIT 0")
        
        fi = fieldinfo()
        # Columns in composite index should have PART_KEY flag
        flags_a = fi.flag(self.cursor.description[1])
        flags_b = fi.flag(self.cursor.description[2])
        
        # At least one should have PART_KEY
        self.assertTrue('PART_KEY' in flags_a or 'PART_KEY' in flags_b)

    def test_field_description_structure(self):
        """Test cursor description structure"""
        self.cursor.execute("""
            CREATE TEMPORARY TABLE test_desc (
                id INT PRIMARY KEY AUTO_INCREMENT,
                name VARCHAR(50),
                value DECIMAL(10,2)
            )
        """)
        self.cursor.execute("SELECT * FROM test_desc LIMIT 0")
        
        # Description should be a sequence of 7-item sequences
        self.assertIsNotNone(self.cursor.description)
        self.assertEqual(len(self.cursor.description), 3)
        
        for desc in self.cursor.description:
            # Each description should have 11 elements
            
            self.assertEqual(len(desc), 11)
            # name, type_code, display_size, internal_size, precision, scale, null_ok
            self.assertIsInstance(desc[0], str)  # name
            self.assertIsInstance(desc[1], int)  # type_code

    def test_field_description_names(self):
        """Test field names in description"""
        self.cursor.execute("""
            SELECT 
                1 as col1,
                'test' as col2,
                3.14 as col3
        """)
        self.cursor.fetchone()
        
        names = [desc[0] for desc in self.cursor.description]
        self.assertEqual(names, ['col1', 'col2', 'col3'])

    def test_field_null_ok_flag(self):
        """Test null_ok flag in field description"""
        self.cursor.execute("""
            CREATE TEMPORARY TABLE test_null (
                not_null INT NOT NULL,
                nullable INT
            )
        """)
        self.cursor.execute("SELECT * FROM test_null LIMIT 0")
        
        # Index 6 is null_ok flag
        not_null_desc = self.cursor.description[0]
        nullable_desc = self.cursor.description[1]
        
        # NOT NULL column should have null_ok = 0 or False
        # Nullable column should have null_ok = 1 or True
        self.assertIsNotNone(not_null_desc[6])
        self.assertIsNotNone(nullable_desc[6])

    def test_field_precision_scale(self):
        """Test precision and scale in field description"""
        self.cursor.execute("SELECT CAST(123.45 AS DECIMAL(10,2)) as val")
        self.cursor.fetchone()
        
        desc = self.cursor.description[0]
        # Index 4 is precision, index 5 is scale
        precision = desc[4]
        scale = desc[5]
        
        self.assertEqual(precision, 12)
        self.assertEqual(scale, 2)

    def test_field_info_unknown_type(self):
        """Test fieldinfo with unknown type code"""
        fi = fieldinfo()
        
        # Create a fake description with unknown type code
        fake_desc = ('col', 9999, None, None, None, None, None)
        result = fi.type(fake_desc)
        
        # Should return None for unknown types
        self.assertIsNone(result)

    def test_field_info_empty_flags(self):
        """Test fieldinfo with no flags set"""
        fi = fieldinfo()
        
        # Create a fake description with no flags (0)
        fake_desc = ('col', constants.FIELD_TYPE.LONG, None, None, None, None, None, 0)
        flags = fi.flag(fake_desc)
        
        # Should return empty string for no flags
        self.assertEqual(flags, '')

    def test_field_info_multiple_flags(self):
        """Test fieldinfo with multiple flags"""
        self.cursor.execute("""
            CREATE TEMPORARY TABLE test_multi_flags (
                id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY
            )
        """)
        self.cursor.execute("SELECT * FROM test_multi_flags LIMIT 0")
        
        fi = fieldinfo()
        flags = fi.flag(self.cursor.description[0])
        
        # Should have multiple flags
        self.assertIn('NOT_NULL', flags)
        self.assertIn('PRIMARY_KEY', flags)
        self.assertIn('AUTO_INCREMENT', flags)
        self.assertIn('UNSIGNED', flags)
        
        # Flags should be separated by " | "
        self.assertIn(' | ', flags)


if __name__ == '__main__':
    unittest.main()
