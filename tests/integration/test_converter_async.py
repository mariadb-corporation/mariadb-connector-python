#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

import datetime
import unittest

import mariadb
from mariadb.constants import FIELD_TYPE
from ..conftest import get_test_config as conf


class foo(int):
    def bar(self): pass


def timedelta_to_time(s):
    return (datetime.datetime.min + s).time()


def long_minus(s):
    return s - 1


def none_to_string(s):
    if s is None:
        return "None"
    return s


conversions = {
    **{FIELD_TYPE.TIME: timedelta_to_time},
    **{FIELD_TYPE.LONG: long_minus},
    **{FIELD_TYPE.NULL: none_to_string},
    **{FIELD_TYPE.LONGLONG: long_minus},
}


class AsyncTestConversion(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        config = conf()
        config["converter"] = conversions
        self.connection = await mariadb.AsyncConnection.connect(**config)
        await self.connection.set_autocommit(False)

    async def asyncTearDown(self):
        await self.connection.close()

    async def test_convert_time(self):
        cursor = self.connection.cursor()
        a = datetime.time(12, 29, 21)
        await cursor.execute("SELECT cast(? as time)", (a,))
        row = await cursor.fetchone()
        self.assertEqual(row[0], a)
        await cursor.close()

    async def test_convert_long(self):
        cursor = self.connection.cursor()
        a = 12345
        await cursor.execute("SELECT CAST(? AS SIGNED)", (12345,))
        row = await cursor.fetchone()
        self.assertEqual(row[0], a - 1)
        await cursor.close()

    async def test_convert_none(self):
        cursor = self.connection.cursor()
        await cursor.execute("SELECT NULL")
        row = await cursor.fetchone()
        self.assertEqual(row[0], "None")
        await cursor.execute("SELECT ?", (None,))
        row = await cursor.fetchone()
        self.assertEqual(row[0], "None")
        await cursor.close()


if __name__ == '__main__':
    unittest.main()
