#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

import datetime
import unittest

from mariadb.constants import FIELD_TYPE
from test.base_test import create_connection


class foo(int):
    def bar(self): pass


def timedelta_to_time(s):
    return (datetime.datetime.min + s).time()


def long_minus(s):
    return s - 1


conversions = {
    **{FIELD_TYPE.TIME: timedelta_to_time},
    **{FIELD_TYPE.LONG: long_minus},
    **{FIELD_TYPE.LONGLONG: long_minus},
}


class TestConversion(unittest.TestCase):

    def setUp(self):
        self.connection = create_connection({"converter": conversions})
        self.connection.autocommit = False

    def tearDown(self):
        del self.connection

    def test_convert_time(self):
        cursor = self.connection.cursor()
        a = datetime.time(12, 29, 21)
        cursor.execute("SELECT cast(? as time)", (a,))
        row = cursor.fetchone()
        self.assertEqual(row[0], a)
        del cursor

    def test_convert_long(self):
        cursor = self.connection.cursor()
        a = 12345
        cursor.execute("SELECT CAST(? AS SIGNED)", (12345,))
        row = cursor.fetchone()
        self.assertEqual(row[0], a - 1)
        del cursor


if __name__ == '__main__':
    unittest.main()
