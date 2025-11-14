#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

import unittest
from datetime import datetime
import mariadb
import sys, traceback

from ..base_test import create_connection


class TestException(unittest.TestCase):

    def setUp(self):
        self.connection = create_connection()

    def tearDown(self):
        self.connection.close()

    def test_exception(self):
        cursor = self.connection.cursor()
        try:
            cursor.execute("WRONG QUERY")
        except mariadb.ProgrammingError as err:
            self.assertEqual(err.sqlstate, "42000")
            self.assertEqual(err.errno, 1064)
            self.assertTrue(err.errmsg.find("You have an error "
                                            "in your SQL syntax") > -1)
            if mariadb._have_asan:
                tb = sys.exc_info()[2]
                traceback.clear_frames(tb)
            pass

        del cursor

    def test_db_unknown_exception(self):

        try:
            create_connection({"database": "unknown"})
        except mariadb.OperationalError as err:
            ending_error = err.__cause__
        except mariadb.ProgrammingError as err:
            ending_error = err

        self.assertEqual(ending_error.sqlstate, "42000")
        self.assertEqual(ending_error.errno, 1049)
        self.assertTrue(ending_error.errmsg.find("Unknown database 'unknown'") > -1)
        if mariadb._have_asan:
            tb = sys.exc_info()[2]
            traceback.clear_frames(tb)

    def test_conn_timeout_exception(self):
        start = datetime.today()
        try:
            create_connection({"connect_timeout": 1, "host": "8.8.8.8"})
        except mariadb.OperationalError as err:
            if (err.__cause__):
                ending_error = err.__cause__
            else:
                ending_error = err
            self.assertEqual(ending_error.sqlstate, "HY000")
            self.assertEqual(ending_error.errno, 2002)
            self.assertTrue(ending_error.errmsg.find("server on '8.8.8.8'") > -1)
            end = datetime.today()
            difference = end - start
            self.assertEqual(difference.days, 0)
            self.assertGreaterEqual(difference.total_seconds(), 0.95,
                                    "Connection should have timed out after ~1 second")
            if mariadb._have_asan:
                tb = sys.exc_info()[2]
                traceback.clear_frames(tb)
            pass

if __name__ == '__main__':
    unittest.main()
