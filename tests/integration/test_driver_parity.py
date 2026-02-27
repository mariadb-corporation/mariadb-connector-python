#!/usr/bin/env python -O
# -*- coding: utf-8 -*-
"""
Driver parity tests: verify that mariadb (pure Python) and mariadb_c (C extension)
return identical results for the same queries across all protocol modes.
"""
from __future__ import annotations

import math
import unittest
from decimal import Decimal
from typing import Any

import mariadb
import mariadb_c

from ..conftest import get_test_config as conf


def _connect_both() -> tuple[Any, Any]:
    """Return (pure_conn, c_conn) connected to the same DB."""
    cfg = conf()
    pure_conn = mariadb.connect(**cfg)
    c_conn = mariadb_c.connect(**cfg)
    return pure_conn, c_conn


def _rows_equal(a: Any, b: Any) -> bool:
    """Compare two result values, handling float approximations."""
    if type(a) is float and type(b) is float:
        return math.isclose(a, b, rel_tol=1e-9)
    if isinstance(a, (bytes, bytearray)) and isinstance(b, (bytes, bytearray)):
        return bytes(a) == bytes(b)
    return a == b


def _assert_results_equal(
    test: unittest.TestCase,
    pure_rows: list[tuple[Any, ...]],
    c_rows: list[tuple[Any, ...]],
    label: str,
) -> None:
    test.assertEqual(
        len(pure_rows), len(c_rows),
        f"{label}: row count differs — pure={len(pure_rows)} c={len(c_rows)}",
    )
    for i, (pr, cr) in enumerate(zip(pure_rows, c_rows)):
        test.assertEqual(
            len(pr), len(cr),
            f"{label} row {i}: column count differs — pure={len(pr)} c={len(cr)}",
        )
        for j, (pv, cv) in enumerate(zip(pr, cr)):
            test.assertTrue(
                _rows_equal(pv, cv),
                f"{label} row {i} col {j}: pure={pv!r} != c={cv!r}",
            )


class TestDriverParity(unittest.TestCase):

    def setUp(self) -> None:
        self.pure_conn, self.c_conn = _connect_both()

    def tearDown(self) -> None:
        self.pure_conn.close()
        self.c_conn.close()

    def _run(
        self,
        sql: str,
        params: tuple[Any, ...] = (),
        *,
        binary: bool = False,
    ) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]]:
        """Execute on both drivers, return (pure_rows, c_rows)."""
        pure_cur = self.pure_conn.cursor(binary=binary)
        c_cur = self.c_conn.cursor(binary=binary)
        pure_cur.execute(sql, params)
        c_cur.execute(sql, params)
        pure_rows = pure_cur.fetchall()
        c_rows = c_cur.fetchall()
        pure_cur.close()
        c_cur.close()
        return pure_rows, c_rows

    # ------------------------------------------------------------------
    # Basic scalar queries
    # ------------------------------------------------------------------

    def test_select_integer_text(self) -> None:
        pure, c = self._run("SELECT 1, 2, 3")
        _assert_results_equal(self, pure, c, "select_integer_text")
        self.assertEqual(pure, [(1, 2, 3)])

    def test_select_integer_binary(self) -> None:
        pure, c = self._run("SELECT 1, 2, 3", binary=True)
        _assert_results_equal(self, pure, c, "select_integer_binary")

    def test_select_param_integer_text(self) -> None:
        pure, c = self._run("SELECT ?, ?, ?", (10, 200, 3000), binary=False)
        _assert_results_equal(self, pure, c, "select_param_integer_text")

    def test_select_param_integer_binary(self) -> None:
        pure, c = self._run("SELECT ?, ?, ?", (10, 200, 3000), binary=True)
        _assert_results_equal(self, pure, c, "select_param_integer_binary")

    def test_select_string_text(self) -> None:
        pure, c = self._run("SELECT 'hello', 'world'")
        _assert_results_equal(self, pure, c, "select_string_text")

    def test_select_string_binary(self) -> None:
        pure, c = self._run("SELECT ?, ?", ("hello", "world"), binary=True)
        _assert_results_equal(self, pure, c, "select_string_binary")

    def test_select_null(self) -> None:
        for binary in (False, True):
            with self.subTest(binary=binary):
                pure, c = self._run("SELECT NULL, NULL", binary=binary)
                _assert_results_equal(self, pure, c, f"select_null binary={binary}")
                self.assertEqual(pure, [(None, None)])

    def test_select_float(self) -> None:
        for binary in (False, True):
            with self.subTest(binary=binary):
                pure, c = self._run("SELECT 3.14159265358979", binary=binary)
                _assert_results_equal(self, pure, c, f"select_float binary={binary}")

    def test_select_decimal(self) -> None:
        for binary in (False, True):
            with self.subTest(binary=binary):
                pure, c = self._run("SELECT CAST(1234.5678 AS DECIMAL(10,4))", binary=binary)
                _assert_results_equal(self, pure, c, f"select_decimal binary={binary}")

    def test_select_date(self) -> None:
        for binary in (False, True):
            with self.subTest(binary=binary):
                pure, c = self._run("SELECT DATE('2024-06-15')", binary=binary)
                _assert_results_equal(self, pure, c, f"select_date binary={binary}")

    def test_select_datetime(self) -> None:
        for binary in (False, True):
            with self.subTest(binary=binary):
                pure, c = self._run("SELECT TIMESTAMP('2024-06-15 12:34:56')", binary=binary)
                _assert_results_equal(self, pure, c, f"select_datetime binary={binary}")

    def test_select_time(self) -> None:
        for binary in (False, True):
            with self.subTest(binary=binary):
                pure, c = self._run("SELECT TIME('12:34:56')", binary=binary)
                _assert_results_equal(self, pure, c, f"select_time binary={binary}")

    def test_select_blob(self) -> None:
        for binary in (False, True):
            with self.subTest(binary=binary):
                pure, c = self._run("SELECT ?, ?", (b"\x00\xff\xde\xad", b"hello"), binary=binary)
                _assert_results_equal(self, pure, c, f"select_blob binary={binary}")

    # ------------------------------------------------------------------
    # Multi-row queries
    # ------------------------------------------------------------------

    def test_seq_1_to_100_text(self) -> None:
        pure, c = self._run("SELECT seq FROM seq_1_to_100")
        _assert_results_equal(self, pure, c, "seq_1_to_100_text")
        self.assertEqual(len(pure), 100)

    def test_seq_1_to_100_binary(self) -> None:
        pure, c = self._run("SELECT seq FROM seq_1_to_100", binary=True)
        _assert_results_equal(self, pure, c, "seq_1_to_100_binary")
        self.assertEqual(len(pure), 100)

    def test_seq_with_param_text(self) -> None:
        pure, c = self._run("SELECT seq FROM seq_1_to_100 WHERE seq > ?", (50,), binary=False)
        _assert_results_equal(self, pure, c, "seq_with_param_text")
        self.assertEqual(len(pure), 50)

    def test_seq_with_param_binary(self) -> None:
        pure, c = self._run("SELECT seq FROM seq_1_to_100 WHERE seq > ?", (50,), binary=True)
        _assert_results_equal(self, pure, c, "seq_with_param_binary")
        self.assertEqual(len(pure), 50)

    # ------------------------------------------------------------------
    # Cursor description (column metadata) parity
    # ------------------------------------------------------------------

    def test_description_parity_text(self) -> None:
        sql = "SELECT 1 AS a, 'x' AS b, NULL AS c"
        pure_cur = self.pure_conn.cursor()
        c_cur = self.c_conn.cursor()
        pure_cur.execute(sql)
        c_cur.execute(sql)
        pure_cur.fetchall()
        c_cur.fetchall()
        self.assertIsNotNone(pure_cur.description)
        self.assertIsNotNone(c_cur.description)
        self.assertEqual(len(pure_cur.description), len(c_cur.description))
        for i, (pd, cd) in enumerate(zip(pure_cur.description, c_cur.description)):
            self.assertEqual(pd[0], cd[0], f"description col {i}: name mismatch")
        pure_cur.close()
        c_cur.close()

    def test_description_parity_binary(self) -> None:
        sql = "SELECT ? AS a, ? AS b"
        pure_cur = self.pure_conn.cursor(binary=True)
        c_cur = self.c_conn.cursor(binary=True)
        pure_cur.execute(sql, (42, "hello"))
        c_cur.execute(sql, (42, "hello"))
        pure_cur.fetchall()
        c_cur.fetchall()
        self.assertIsNotNone(pure_cur.description)
        self.assertIsNotNone(c_cur.description)
        self.assertEqual(len(pure_cur.description), len(c_cur.description))
        pure_cur.close()
        c_cur.close()

    # ------------------------------------------------------------------
    # Repeated execute (stmt cache reuse)
    # ------------------------------------------------------------------

    def test_repeated_execute_same_sql(self) -> None:
        sql = "SELECT seq FROM seq_1_to_100 WHERE seq = ?"
        for val in (1, 50, 100):
            with self.subTest(val=val):
                pure, c = self._run(sql, (val,), binary=True)
                _assert_results_equal(self, pure, c, f"repeated_execute val={val}")
                self.assertEqual(pure, [(val,)])

    def test_switch_sql_between_executes(self) -> None:
        """Cursor switching between two SQL strings must return correct data."""
        sql_a = "SELECT ?, ?"
        sql_b = "SELECT ?, ?, ?"
        for binary in (False, True):
            with self.subTest(binary=binary):
                pure_cur = self.pure_conn.cursor(binary=binary)
                c_cur = self.c_conn.cursor(binary=binary)
                for _ in range(3):
                    pure_cur.execute(sql_a, (1, 2))
                    c_cur.execute(sql_a, (1, 2))
                    pr = pure_cur.fetchall()
                    cr = c_cur.fetchall()
                    _assert_results_equal(self, pr, cr, f"switch_sql A binary={binary}")

                    pure_cur.execute(sql_b, (10, 20, 30))
                    c_cur.execute(sql_b, (10, 20, 30))
                    pr = pure_cur.fetchall()
                    cr = c_cur.fetchall()
                    _assert_results_equal(self, pr, cr, f"switch_sql B binary={binary}")
                pure_cur.close()
                c_cur.close()
