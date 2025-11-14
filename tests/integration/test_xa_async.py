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

    async def test_tpc_begin_no_xid(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            try:
                await con.tpc_begin(123)
            except mariadb.ProgrammingError:
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
            with self.assertRaises(mariadb.ProgrammingError) as cm:
                await con.tpc_commit()
            self.assertIn("not prepared", str(cm.exception).lower())

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
            with self.assertRaises(mariadb.ProgrammingError):
                await con.tpc_prepare()

            xid = con.xid(0, "2234567894", "2345")
            await con.tpc_begin(xid)
            cursor = con.cursor()
            await cursor.execute("SELECT 1")
            await cursor.close()
            await con.tpc_prepare()
            with self.assertRaises(mariadb.ProgrammingError):
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

    async def test_tpc_commit_without_transaction(self):
        """Test tpc_commit fails when transaction not started (TPC_STATE.NONE)"""
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            # Calling tpc_commit without starting a transaction should fail
            with self.assertRaises(mariadb.ProgrammingError) as cm:
                await con.tpc_commit()
            self.assertIn("not started", str(cm.exception).lower())

    async def test_tpc_commit_without_prepare(self):
        """Test tpc_commit fails when transaction not prepared and xid is None"""
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            xid = con.xid(0, "2234567899", "2345")
            await con.tpc_begin(xid)
            
            # Calling tpc_commit() without xid and without prepare should fail
            with self.assertRaises(mariadb.ProgrammingError) as cm:
                await con.tpc_commit()
            self.assertIn("not prepared", str(cm.exception).lower())

    async def test_tpc_commit_with_invalid_xid(self):
        """Test tpc_commit fails when xid is not an Xid object"""
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            xid = con.xid(0, "2234567900", "2345")
            await con.tpc_begin(xid)
            
            # Calling tpc_commit with invalid xid type should fail
            with self.assertRaises(mariadb.ProgrammingError) as cm:
                await con.tpc_commit(123)
            self.assertIn("must be xid", str(cm.exception).lower())

    async def test_tpc_rollback_without_transaction(self):
        """Test tpc_rollback fails when transaction not started (TPC_STATE.NONE)"""
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            # Calling tpc_rollback without starting a transaction should fail
            with self.assertRaises(mariadb.ProgrammingError) as cm:
                await con.tpc_rollback()
            self.assertIn("not started", str(cm.exception).lower())

    async def test_tpc_rollback_with_invalid_xid(self):
        """Test tpc_rollback fails when xid is not an Xid object"""
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            xid = con.xid(0, "2234567901", "2345")
            await con.tpc_begin(xid)
            
            # Calling tpc_rollback with invalid xid type should fail
            with self.assertRaises(mariadb.ProgrammingError) as cm:
                await con.tpc_rollback(123)
            self.assertIn("must be xid", str(cm.exception).lower())


if __name__ == '__main__':
    unittest.main()
