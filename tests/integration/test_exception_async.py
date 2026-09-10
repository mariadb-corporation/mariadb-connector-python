#!/usr/bin/env python -O
# -*- coding: utf-8 -*-


from __future__ import annotations

from typing import cast

from mariadb_shared.async_connection_common import AsyncConnectionCommon
from mariadb_shared.connection_params import ConnectionOptions
from mariadb_shared.rows import TupleRow

import unittest
from datetime import datetime
import mariadb
import sys
import traceback


from ..conftest import get_test_config as conf


async def create_async_connection(additional_conf: ConnectionOptions | None = None) -> AsyncConnectionCommon[TupleRow]:
    """Helper to create async connection with optional additional config"""
    if additional_conf is None:
        return await mariadb.AsyncConnection.connect(**conf())
    merged = cast(ConnectionOptions, {**conf(), **additional_conf})
    return await mariadb.AsyncConnection.connect(**merged)

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

    async def test_db_unknown_exception(self):

        ending_error: BaseException | None = None
        try:
            await create_async_connection({"database": "unknown"})
        except mariadb.OperationalError as err:
            ending_error = err.__cause__
            assert isinstance(ending_error, mariadb.Error)
        except mariadb.ProgrammingError as err:
            ending_error = err

        assert isinstance(ending_error, mariadb.Error)
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
                assert isinstance(ending_error, mariadb.Error)
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
