#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""
CONPY-382, async client: a parameter that cannot be serialized must leave the
connection usable.

The async client pipelines the prepare and then writes one execute packet per
row. When building an execute payload fails -- a str with no UTF-8 encoding --
the prepare is already on the wire, and its response has to be read anyway or
the next statement on that connection reads it as its own. That showed up as an
executemany() raising correctly, followed by an unrelated
"No result set to fetch from" on the very next query.

The sync side of this lives in test_invalid_param_binding.py; only the
async-specific path is exercised here.
"""

import array
import unittest

import mariadb
from ..base_test import is_mysql
from ..conftest import get_test_config as conf

BAD = '\ud800'
_RAISES = (UnicodeEncodeError, mariadb.Error)


class AsyncInvalidParamBindingTest(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.connection = await mariadb.asyncConnect(**conf())
        self.cursor = self.connection.cursor()
        await self.cursor.execute("DROP TABLE IF EXISTS conpy382a")
        await self.cursor.execute("CREATE TABLE conpy382a (a TEXT)")

    async def asyncTearDown(self):
        try:
            await self.cursor.execute("DROP TABLE IF EXISTS conpy382a")
        except mariadb.Error:
            pass
        await self.connection.close()
        del self.connection

    async def assert_connection_usable(self):
        """No leftover response in the socket: the next query must be answered."""
        await self.cursor.execute("SELECT 1")
        self.assertEqual((1,), await self.cursor.fetchone())

    async def test_executemany_unencodable_string_keeps_connection_usable(self):
        for label, rows in (("only row", [(BAD,)]),
                            ("after a valid row", [('valid',), (BAD,)]),
                            ("between valid rows", [('a',), (BAD,), ('b',)])):
            with self.subTest(label):
                # start from an empty table so each case stands alone
                await self.cursor.execute("DELETE FROM conpy382a")
                with self.assertRaises(_RAISES):
                    await self.cursor.executemany(
                        "INSERT INTO conpy382a VALUES (?)", rows)
                await self.assert_connection_usable()
                # the unencodable row is never written; rows before it survive
                # only on servers without the bulk protocol (row-by-row loop)
                await self.cursor.execute("SELECT COUNT(*) FROM conpy382a")
                self.assertLessEqual((await self.cursor.fetchone())[0],
                                     len(rows) - 1)

    async def test_execute_unencodable_string_keeps_connection_usable(self):
        with self.assertRaises(_RAISES):
            await self.cursor.execute("INSERT INTO conpy382a VALUES (?)", (BAD,))
        await self.assert_connection_usable()

    async def test_valid_executemany_still_works(self):
        await self.cursor.executemany("INSERT INTO conpy382a VALUES (?)",
                                      [('a',), ('accentué',), ('😎',)])
        await self.cursor.execute("SELECT COUNT(*) FROM conpy382a")
        self.assertEqual((3,), await self.cursor.fetchone())

    async def test_empty_vector_keeps_connection_usable(self):
        if is_mysql():
            self.skipTest("VECTOR columns are MariaDB-specific here")
        if self.connection.server_version < 110702:
            self.skipTest("Requires server version >= 11.7.2 for VECTOR")
        await self.cursor.execute("DROP TABLE IF EXISTS conpy382av")
        await self.cursor.execute("CREATE TABLE conpy382av (id INT, v VECTOR(2))")
        try:
            # An empty vector is refused by the C extension and stored as NULL by
            # the pure-Python client; either is fine, a broken connection is not.
            try:
                await self.cursor.executemany(
                    "INSERT INTO conpy382av VALUES (?,?)",
                    [(1, array.array('f', [1.0, 2.0])), (2, array.array('f', []))])
            except mariadb.Error:
                pass
            await self.assert_connection_usable()
        finally:
            await self.cursor.execute("DROP TABLE IF EXISTS conpy382av")


if __name__ == '__main__':
    unittest.main()
