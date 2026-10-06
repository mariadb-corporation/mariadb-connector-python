#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

import unittest

import mariadb
from mariadb_shared.text_protocol import substitute_params, normalize_to_qmark
from typing import Any, Mapping, Sequence


def _subst(sql: str, params: Mapping[str, Any] | Sequence[Any]) -> str:
    return b"".join(substitute_params(sql, params)).decode("utf-8")


def _norm(sql: str) -> str:
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

    def test_slash_star_slash_opens_comment(self):
        # '/*/' is an opening '/*' followed by a '/' of comment content, as on
        # the server: the comment runs to the next '*/'
        self.assertEqual(_norm("SELECT /*/ :x */ :p"), "SELECT /*/ :x */ ?")
        self.assertEqual(_subst("SELECT /*/ ? */ ?", [9]), "SELECT /*/ ? */ 9")

    def test_empty_block_comment(self):
        self.assertEqual(_norm("SELECT /**/ :p"), "SELECT /**/ ?")
        self.assertEqual(_subst("SELECT /**/ ?", [9]), "SELECT /**/ 9")

    def test_unterminated_block_comment_runs_to_end(self):
        self.assertEqual(_norm("SELECT 1 /* :p"), "SELECT 1 /* :p")
        self.assertEqual(_subst("SELECT 1 /* ?", []), "SELECT 1 /* ?")


MARIADB_12_3 = 120302
MYSQL_8_0 = 80000


def _subst_on(sql: str, params: Sequence[Any], server_version: int, is_mariadb: bool = True) -> str:
    return b"".join(substitute_params(sql, params, False, server_version, is_mariadb)).decode("utf-8")


class SqlParserExecutableCommentTest(unittest.TestCase):
    """A placeholder inside an executable comment is a parameter only when the
    server runs that comment (CONPY-133): the parser applies the server's
    rules from the server version and type the cursor passes along."""

    # --- comments the server runs -------------------------------------------

    def test_no_version_is_run(self):
        self.assertEqual(_subst_on("SELECT /*! ? */", [1], MARIADB_12_3), "SELECT /*! 1 */")
        self.assertEqual(_subst_on("SELECT /*M! ? */", [1], MARIADB_12_3), "SELECT /*M! 1 */")
        self.assertEqual(_subst_on("SELECT /*! ? */, /*M! ? */", [1, 2], MARIADB_12_3),
                         "SELECT /*! 1 */, /*M! 2 */")

    def test_version_up_to_the_server_is_run(self):
        self.assertEqual(_subst_on("SELECT /*!50600 ? */", [1], MARIADB_12_3), "SELECT /*!50600 1 */")
        self.assertEqual(_subst_on("SELECT /*!100201 ? */", [1], MARIADB_12_3), "SELECT /*!100201 1 */")
        self.assertEqual(_subst_on("SELECT /*!120302 ? */", [1], MARIADB_12_3), "SELECT /*!120302 1 */")
        self.assertEqual(_subst_on("SELECT /*M!120302 ? + ? */", [1, 2], MARIADB_12_3),
                         "SELECT /*M!120302 1 + 2 */")

    def test_unknown_server_version_runs_everything(self):
        self.assertEqual(_subst_on("SELECT /*!999999 ? */", [1], 0), "SELECT /*!999999 1 */")

    # --- comments the server does not run -----------------------------------

    def test_future_version_is_a_comment(self):
        # the second '?' is inside a comment the server skips: one parameter
        self.assertEqual(_subst_on("SELECT ? /*!999999 , ? */", [1], MARIADB_12_3),
                         "SELECT 1 /*!999999 , ? */")
        self.assertEqual(_subst_on("SELECT ? /*M!120303 , ? */", [1], MARIADB_12_3),
                         "SELECT 1 /*M!120303 , ? */")
        self.assertEqual(_subst_on("SELECT 1 /*!999999 , ? */", [], MARIADB_12_3),
                         "SELECT 1 /*!999999 , ? */")

    def test_mysql_only_range_is_a_comment_on_mariadb(self):
        # MariaDB never runs /*!50700 .. /*!99999 (MySQL 5.7 and later)
        self.assertEqual(_subst_on("SELECT 1 /*!50701 , ? */", [], MARIADB_12_3),
                         "SELECT 1 /*!50701 , ? */")
        self.assertEqual(_subst_on("SELECT 1 /*!80000 , ? */", [], MARIADB_12_3),
                         "SELECT 1 /*!80000 , ? */")
        # MySQL runs it
        self.assertEqual(_subst_on("SELECT 1 /*!50701 , ? */", [2], MYSQL_8_0, is_mariadb=False),
                         "SELECT 1 /*!50701 , 2 */")

    def test_mariadb_comment_is_a_comment_on_mysql(self):
        self.assertEqual(_subst_on("SELECT 1 /*M! , ? */", [], MYSQL_8_0, is_mariadb=False),
                         "SELECT 1 /*M! , ? */")
        self.assertEqual(_subst_on("SELECT 1 /*M!100201 , ? */", [], MYSQL_8_0, is_mariadb=False),
                         "SELECT 1 /*M!100201 , ? */")

    def test_m_without_bang_is_a_plain_comment(self):
        self.assertEqual(_subst_on("SELECT 1 /*Mfoo , ? */", [], MARIADB_12_3),
                         "SELECT 1 /*Mfoo , ? */")

    def test_unterminated_skipped_comment(self):
        self.assertEqual(_subst_on("SELECT ? /*!999999 , ?", [1], MARIADB_12_3),
                         "SELECT 1 /*!999999 , ?")

    def test_opener_inside_a_literal(self):
        self.assertEqual(_subst_on("SELECT '/*!999999 ?', ?", [1], MARIADB_12_3),
                         "SELECT '/*!999999 ?', 1")

    def test_surplus_value_is_an_error(self):
        # the value meant for the skipped placeholder must not be dropped silently
        with self.assertRaises(mariadb.ProgrammingError):
            _subst_on("SELECT ? + /*M!140201 ? + */ ?", [1, 2, 3], MARIADB_12_3)
        with self.assertRaises(mariadb.ProgrammingError):
            _subst_on("SELECT ?, 'x'", [1, 2], MARIADB_12_3)

    def test_normalize_skips_a_comment_the_server_does_not_run(self):
        self.assertEqual(normalize_to_qmark("SELECT :a /*!999999 , :b */", MARIADB_12_3),
                         ("SELECT ? /*!999999 , :b */", ["a"]))
        self.assertEqual(normalize_to_qmark("SELECT :a /*M! , :b */", MARIADB_12_3),
                         ("SELECT ? /*M! , ? */", ["a", "b"]))


if __name__ == "__main__":
    unittest.main()
