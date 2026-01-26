#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

import unittest
from datetime import datetime
import mariadb
import sys
import traceback

from tests.base_test import is_native

from ..conftest import get_test_config as conf


async def create_async_connection(additional_conf=None):
    """Helper to create async connection with optional additional config"""
    default_conf = conf()
    if additional_conf is None:
        c = {key: value for (key, value) in (default_conf.items())}
    else:
        c = {key: value for (key, value) in (list(default_conf.items()) + list(
            additional_conf.items()))}
    return await mariadb.AsyncConnection.connect(**c)

class AsyncTestException(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.connection = await create_async_connection()

    async def asyncTearDown(self):
        await self.connection.close()
        del self.connection

    async def test_exception(self):
        cursor = self.connection.cursor()
        try:
            await cursor.execute("WRONG QUERY")
        except mariadb.ProgrammingError as err:
            self.assertEqual(err.sqlstate, "42000")
            self.assertEqual(err.errno, 1064)
            self.assertTrue(err.errmsg.find("You have an error "
                                            "in your SQL syntax") > -1)
            if mariadb._have_asan:
                tb = sys.exc_info()[2]
                traceback.clear_frames(tb)
            pass

        await cursor.close()
        del cursor

    async def test_db_unknown_exception(self):

        try:
            await create_async_connection({"database": "unknown"})
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

    async def test_conn_timeout_exception(self):
        start = datetime.today()
        try:
            await create_async_connection({"connect_timeout": 1, "host": "8.8.8.8"})
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
