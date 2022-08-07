#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

import unittest
import mariadb

from test.base_test import create_connection


class TestCA(unittest.TestCase):

    def setUp(self):
        self.connection = create_connection()
        self.connection.autocommit = False

    def tearDown(self):
        del self.connection

    def test_xid(self):
        con = create_connection()
        xid = con.xid(1, "foo", "bar")
        self.assertEqual(xid, (1, "foo", "bar"))

        # default for format_id is 1
        xid = con.xid(0, "foo", "bar")
        self.assertEqual(xid, (1, "foo", "bar"))

        # parameter too long:
        try:
            xid = con.xid(0, "a" * 65, "bar")
        except mariadb.ProgrammingError:
            pass
        try:
            xid = con.xid(0, "foo", "b" * 65)
        except mariadb.ProgrammingError:
            pass

    def test_tpc_begin(self):
        con = create_connection()
        xid = con.xid(0, "1234567890", "2345")
        try:
            con.tpc_begin(xid)
        except mariadb.NotSupportedError:
            pass

    def test_tpc_commit(self):
        con = create_connection()
        xid = con.xid(0, "1234567891", "2345")
        try:
            con.tpc_begin(xid)
            cursor = con.cursor()
            cursor.execute("CREATE TEMPORARY TABLE t1 (a int)")
            cursor.execute("INSERT INTO t1 VALUES (1),(2)")
            cursor.close()
            con.tpc_commit()
        finally:
            con.close()

    def test_tpc_rollback_without_prepare(self):
        con = create_connection()
        try:
            xid = con.xid(0, "1234567892", "2345")
            con.tpc_begin(xid)
            cursor = con.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            con.tpc_rollback()
        finally:
            con.close()

    def test_tpc_commit_with_prepare(self):
        con = create_connection()
        try:
            xid = con.xid(0, "1234567893", "2345")
            con.tpc_begin(xid)
            cursor = con.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            con.tpc_prepare()
            con.tpc_commit()
        finally:
            con.close()

    def test_tpc_rollback_with_prepare(self):
        con = create_connection()
        try:
            xid = con.xid(0, "1234567894", "2345")
            con.tpc_begin(xid)
            cursor = con.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            con.tpc_prepare()
            con.tpc_rollback()
        finally:
            con.close()

    def test_tpc_begin_in_transaction_fails(self):
        con = create_connection()
        try:
            xid = con.xid(0, "1234567895", "2345")

            cursor = con.cursor()
            cursor.execute("BEGIN")
            cursor.execute("SELECT 1")
            cursor.close()
            self.assertRaises(mariadb.IntegrityError,
                              con.tpc_begin, xid)
        finally:
            con.close()

    def test_commit_in_tpc_fails(self):
        con = create_connection()
        try:
            xid = con.xid(0, "1234567897", "2345")
            con.tpc_begin(xid)

            self.assertRaises(mariadb.ProgrammingError, con.commit)
        finally:
            con.close()

    def test_rollback_in_tpc_fails(self):
        # calling rollback() within a TPC transaction fails with
        # ProgrammingError.
        con = create_connection()
        try:
            xid = con.xid(0, "1234567898", "2345")
            con.tpc_begin(xid)

            self.assertRaises(mariadb.ProgrammingError, con.rollback)
        finally:
            con.close()


if __name__ == '__main__':
    unittest.main()
