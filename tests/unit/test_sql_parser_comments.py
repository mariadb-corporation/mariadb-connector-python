#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

import unittest
from mariadb_shared.text_protocol import substitute_params, normalize_to_qmark


def _subst(sql, params):
    return b"".join(substitute_params(sql, params)).decode("utf-8")


def _norm(sql):
    norm, _names = normalize_to_qmark(sql)
    return norm.decode("utf-8") if isinstance(norm, (bytes, bytearray)) else norm


class SqlParserCommentTest(unittest.TestCase):

    # --- '--' as an operator (not a comment) ---------------------------------

    def test_dash_dash_operator_keeps_following_placeholder(self):
        # 2--1 is 2 minus -1; the ? after it must still be substituted
        self.assertEqual(_subst("SELECT 2--1, ?", [5]), "SELECT 2--1, 5")

    def test_dash_dash_between_two_placeholders(self):
        self.assertEqual(_subst("SELECT ?--?", [10, 3]), "SELECT 10--3")

    def test_dash_dash_operator_not_normalized_away(self):
        # placeholder after a '--' operator must survive normalization
        self.assertEqual(_norm("SELECT 2--1, ?"), "SELECT 2--1, ?")
        self.assertEqual(_norm("SELECT 2--1, :p"), "SELECT 2--1, ?")

    # --- '--' as a genuine line comment --------------------------------------

    def test_dash_dash_space_is_comment(self):
        # '-- ' (dash dash space) IS a comment: the ? inside it is ignored,
        # only the ? on the next line is a real placeholder
        self.assertEqual(_subst("SELECT 1 -- ?\n, ?", [9]), "SELECT 1 -- ?\n, 9")

    def test_dash_dash_tab_is_comment(self):
        self.assertEqual(_subst("SELECT 1 --\t?\n, ?", [9]), "SELECT 1 --\t?\n, 9")

    def test_dash_dash_at_end_of_query_is_comment(self):
        # '--' at end of statement starts a comment (Connector/J behaviour);
        # the trailing ? is part of the comment, only the first ? is a param
        self.assertEqual(_subst("SELECT ? --", [7]), "SELECT 7 --")

    def test_hash_comment_still_works(self):
        self.assertEqual(_subst("SELECT 1 # ?\n, ?", [4]), "SELECT 1 # ?\n, 4")

    # --- '//' is NOT a comment in MySQL/MariaDB ------------------------------

    def test_double_slash_is_not_a_comment(self):
        # leading quote forces the slow-path parser; '//' must not start a comment
        self.assertEqual(_subst("SELECT '' , 1//1, ?", [5]), "SELECT '' , 1//1, 5")

    def test_double_slash_not_comment_in_normalize(self):
        self.assertEqual(_norm("SELECT 1//1, :p"), "SELECT 1//1, ?")

    # --- genuine block comments still work -----------------------------------

    def test_block_comment_suppresses_placeholder(self):
        self.assertEqual(_norm("SELECT /* :x */ :p"), "SELECT /* :x */ ?")

    def test_star_after_block_comment_is_not_new_comment(self):
        # after '*/' a following '*' is the multiply operator, not '/*';
        # the placeholder after it must still be found
        self.assertEqual(_subst("SELECT 2 /* x */*3, ?", [9]), "SELECT 2 /* x */*3, 9")
        self.assertEqual(_norm("SELECT 2 /* x */*3, :p"), "SELECT 2 /* x */*3, ?")

    def test_adjacent_block_comments(self):
        self.assertEqual(_norm("SELECT /*a*//*b*/ :p"), "SELECT /*a*//*b*/ ?")


if __name__ == "__main__":
    unittest.main()
