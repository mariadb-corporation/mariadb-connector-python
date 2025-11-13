#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

import unittest
import mariadb

from ..conftest import get_test_config as conf


# Check if AsyncConnection is available
HAS_ASYNC_CONNECTION = hasattr(mariadb, 'AsyncConnection') and mariadb.AsyncConnection is not None


@unittest.skipIf(not HAS_ASYNC_CONNECTION, "AsyncConnection not available")
class AsyncTestCA(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.connection = await mariadb.AsyncConnection.connect(**conf())
        await self.connection.set_autocommit(False)

    async def asyncTearDown(self):
        await self.connection.close()
        del self.connection

    async def test_xid(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
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

    async def test_tpc_begin(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            xid = con.xid(0, "2234567890", "2345")
            try:
                await con.tpc_begin(xid)
            except mariadb.NotSupportedError:
                pass

    async def test_tpc_commit(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            xid = con.xid(0, "2234567891", "2345")
            cursor = con.cursor()
            await cursor.execute("DROP TABLE IF EXISTS t1")
            await cursor.execute("CREATE TABLE t1 (a int)")
            await con.tpc_begin(xid)
            await cursor.execute("INSERT INTO t1 VALUES (1),(2)")
            await cursor.close()
            await con.tpc_commit()

    async def test_tpc_rollback_without_prepare(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            xid = con.xid(0, "2234567892", "2345")
            await con.tpc_begin(xid)
            cursor = con.cursor()
            await cursor.execute("SELECT 1")
            await cursor.close()
            await con.tpc_rollback()

    async def test_tpc_commit_with_prepare(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            xid = con.xid(0, "2234567893", "2345")
            await con.tpc_begin(xid)
            cursor = con.cursor()
            await cursor.execute("SELECT 1")
            await cursor.close()
            await con.tpc_prepare()
            await con.tpc_commit()

    async def test_tpc_rollback_with_prepare(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            xid = con.xid(0, "2234567894", "2345")
            await con.tpc_begin(xid)
            cursor = con.cursor()
            await cursor.execute("SELECT 1")
            await cursor.close()
            await con.tpc_prepare()
            await con.tpc_rollback()

    async def test_tpc_begin_in_transaction_fails(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            xid = con.xid(0, "2234567895", "2345")

            cursor = con.cursor()
            await cursor.execute("BEGIN")
            await cursor.execute("SELECT 1")
            await cursor.close()
            with self.assertRaises(mariadb.IntegrityError):
                await con.tpc_begin(xid)

    async def test_commit_in_tpc_fails(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            xid = con.xid(0, "2234567897", "2345")
            await con.tpc_begin(xid)

            with self.assertRaises(mariadb.ProgrammingError):
                await con.commit()

    async def test_rollback_in_tpc_fails(self):
        # calling rollback() within a TPC transaction fails with
        # ProgrammingError.
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            xid = con.xid(0, "2234567898", "2345")
            await con.tpc_begin(xid)

            with self.assertRaises(mariadb.ProgrammingError):
                await con.rollback()


if __name__ == '__main__':
    unittest.main()
