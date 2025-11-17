#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Unit tests for SQL parser
"""

import unittest
from mariadb.impl.sql_parser import split_sql_parts


class TestSQLParser(unittest.TestCase):
    """Test SQL parser functionality"""

    def test_split_query_simple(self):
        """Test simple positional placeholder"""
        sql = "SELECT * FROM users WHERE id = ?"
        sql_bytes, positions = split_sql_parts(sql)
        self.assertEqual(sql_bytes, b"SELECT * FROM users WHERE id = ?")
        self.assertEqual(positions, [31, 32])

    def test_split_query_multiple(self):
        """Test multiple positional placeholders"""
        sql = "INSERT INTO users VALUES (?, ?, ?)"
        sql_bytes, positions = split_sql_parts(sql)
        self.assertEqual(sql_bytes, b"INSERT INTO users VALUES (?, ?, ?)")
        self.assertEqual(positions, [26, 27, 29, 30, 32, 33])

    def test_split_query_in_string(self):
        """Test placeholder inside string is ignored"""
        sql = "SELECT * FROM users WHERE name = 'test?' AND id = ?"
        sql_bytes, positions = split_sql_parts(sql)
        # Only the last ? should be found
        self.assertEqual(positions, [50, 51])

    def test_split_query_in_comment(self):
        """Test placeholder inside comment is ignored"""
        sql = "SELECT * FROM users /* WHERE id = ? */ WHERE name = ?"
        sql_bytes, positions = split_sql_parts(sql)
        # Only the last ? should be found
        self.assertEqual(positions, [52, 53])

    def test_split_query_in_line_comment(self):
        """Test placeholder inside line comment is ignored"""
        sql = "SELECT * FROM users -- WHERE id = ?\nWHERE name = ?"
        sql_bytes, positions = split_sql_parts(sql)
        # Only the last ? should be found
        self.assertEqual(positions, [49, 50])

    def test_split_query_in_hash_comment(self):
        """Test placeholder inside hash comment is ignored"""
        sql = "SELECT * FROM users # WHERE id = ?\nWHERE name = ?"
        sql_bytes, positions = split_sql_parts(sql)
        # Only the last ? should be found
        self.assertEqual(positions, [48, 49])

    def test_split_query_in_backticks(self):
        """Test placeholder inside backticks is ignored"""
        sql = "SELECT * FROM `table?` WHERE id = ?"
        sql_bytes, positions = split_sql_parts(sql)
        # Only the last ? should be found
        self.assertEqual(positions, [34, 35])

    def test_split_query_double_quotes(self):
        """Test placeholder inside double quotes is ignored"""
        sql = 'SELECT * FROM users WHERE name = "test?" AND id = ?'
        sql_bytes, positions = split_sql_parts(sql)
        # Only the last ? should be found
        self.assertEqual(positions, [50, 51])

    def test_split_query_escaped_quote(self):
        """Test escaped quote in string"""
        sql = "SELECT * FROM users WHERE name = 'test\\'?' AND id = ?"
        sql_bytes, positions = split_sql_parts(sql)
        # Only the last ? should be found
        self.assertEqual(positions, [52, 53])

    def test_split_sql_parts_simple(self):
        """Test splitting SQL into parts"""
        sql = "SELECT * FROM users WHERE id = ?"
        sql_bytes, positions = split_sql_parts(sql)
        self.assertEqual(sql_bytes, b"SELECT * FROM users WHERE id = ?")
        self.assertEqual(positions, [31, 32])

    def test_split_sql_parts_multiple(self):
        """Test splitting SQL with multiple placeholders"""
        sql = "INSERT INTO users VALUES (?, ?, ?)"
        sql_bytes, positions = split_sql_parts(sql)
        self.assertEqual(sql_bytes, b"INSERT INTO users VALUES (?, ?, ?)")
        self.assertEqual(positions, [26, 27, 29, 30, 32, 33])

    def test_split_sql_parts_no_placeholders(self):
        """Test SQL with no placeholders"""
        sql = "SELECT * FROM users"
        sql_bytes, positions = split_sql_parts(sql)
        self.assertEqual(sql_bytes, b"SELECT * FROM users")
        self.assertEqual(positions, [])

    def test_complex_sql_with_strings_and_comments(self):
        """Test complex SQL with strings, comments, and placeholders"""
        sql = """
        SELECT * FROM users 
        WHERE name = 'John?' /* comment with ? */
        AND email = "test@example.com" -- another comment with ?
        AND id = ?
        AND status = ?
        """
        sql_bytes, positions = split_sql_parts(sql)
        # Should find 2 placeholders (the ones not in strings/comments)
        self.assertEqual(len(positions), 4)  # 2 placeholders * 2 positions each

    def test_slash_star_comment(self):
        """Test /* */ style comments"""
        sql = "SELECT * /* ? */ FROM users WHERE id = ?"
        sql_bytes, positions = split_sql_parts(sql)
        self.assertEqual(len(positions), 2)  # Only 1 placeholder

    def test_double_slash_comment(self):
        """Test // style comments"""
        sql = "SELECT * FROM users // WHERE id = ?\nWHERE name = ?"
        sql_bytes, positions = split_sql_parts(sql)
        self.assertEqual(len(positions), 2)  # Only 1 placeholder

    def test_executable_comment_mysql(self):
        """Test executable comment /*! */ - placeholders should be found"""
        sql = "SELECT /*! SQL_NO_CACHE */ * FROM users WHERE id = ?"
        sql_bytes, positions = split_sql_parts(sql)
        self.assertEqual(positions, [51, 52])  # Should find the placeholder

    def test_executable_comment_mariadb(self):
        """Test MariaDB executable comment /*M! */ - placeholders should be found"""
        sql = "SELECT /*M! 100100 SQL_NO_CACHE */ * FROM users WHERE id = ?"
        sql_bytes, positions = split_sql_parts(sql)
        self.assertEqual(positions, [59, 60])  # Should find the placeholder

    def test_executable_comment_with_placeholder_inside(self):
        """Test executable comment with placeholder inside it"""
        sql = "INSERT /*! IGNORE */ INTO users VALUES (?)"
        sql_bytes, positions = split_sql_parts(sql)
        self.assertEqual(positions, [40, 41])  # Should find the placeholder

    def test_regular_comment_vs_executable(self):
        """Test that regular comments still ignore placeholders but executable don't"""
        sql = "SELECT /* ignore ? */ * FROM users /*! keep ? */ WHERE id = ?"
        sql_bytes, positions = split_sql_parts(sql)
        # Should find 2 placeholders: one in /*! */ and one after WHERE
        # Should NOT find the one in /* */
        self.assertEqual(len(positions), 4)  # 2 placeholders * 2 positions each


if __name__ == '__main__':
    unittest.main()
