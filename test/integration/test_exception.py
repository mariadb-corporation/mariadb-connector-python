#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

import unittest
from datetime import datetime
import mariadb

from test.base_test import create_connection


class TestException(unittest.TestCase):

    def setUp(self):
        self.connection = create_connection()

    def tearDown(self):
        del self.connection

    def test_exception(self):
        cursor = self.connection.cursor()
        try:
            cursor.execute("WRONG QUERY")
        except mariadb.ProgrammingError as err:
            self.assertEqual(err.sqlstate, "42000")
            self.assertEqual(err.errno, 1064)
            self.assertTrue(err.errmsg.find("You have an error in your SQL syntax") > -1)
            pass

        del cursor

    def test_db_unknown_exception(self):
        try:
            create_connection({"database": "Unknown"})
        except mariadb.ProgrammingError as err:
            self.assertEqual(err.sqlstate, "42000")
            self.assertEqual(err.errno, 1049)
            self.assertTrue(err.errmsg.find("Unknown database 'Unknown'") > -1)
            pass

    def test_conn_timeout_exception(self):
        start = datetime.today()
        try:
            create_connection({"connect_timeout": 1, "host": "google.com", "port": 443})
        except mariadb.DatabaseError as err:
            self.assertEqual(err.sqlstate, "HY000")
            self.assertEqual(err.errno, 2013)
            self.assertTrue(err.errmsg.find("Lost connection to MySQL server at 'handshake: reading inital communication packet'") > -1)
            end = datetime.today()
            difference = end - start
            self.assertEqual(difference.days, 0)
            self.assertTrue(difference.seconds, 1)
            pass


if __name__ == '__main__':
    unittest.main()
