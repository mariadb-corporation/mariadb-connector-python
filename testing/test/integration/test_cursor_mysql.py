#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

import datetime
import unittest
import os

from test.base_test import create_connection


class CursorMySQLTest(unittest.TestCase):

    def setUp(self):
        self.connection = create_connection()

    def tearDown(self):
        del self.connection

    def test_parameter(self):
        if os.environ.get("MAXSCALE_VERSION"):
            self.skipTest("MAXSCALE doesn't support BULK yet")

        cursor = self.connection.cursor()
        cursor.execute("CREATE TEMPORARY TABLE test_parameter(a int auto_increment primary key not "
                       "null, b int, c int, d varchar(20),e date)")
        cursor.execute("SET @@autocommit=0")
        c = (1, 2, 3, "bar", datetime.date(2018, 11, 11))
        list_in = []
        for i in range(1, 30000):
            row = (i, i, i, "bar", datetime.date(2019, 1, 1))
            list_in.append(row)
        cursor.executemany("INSERT INTO test_parameter VALUES (%s,%s,%s,%s,%s)", list_in)
        self.connection.commit()
        cursor.execute("SELECT * FROM test_parameter order by a")
        list_out = cursor.fetchall()
        self.assertEqual(list_in, list_out)

        cursor.close()


if __name__ == '__main__':
    unittest.main()
