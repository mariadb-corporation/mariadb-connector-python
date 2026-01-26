#!/usr/bin/env python -O

# -*- coding: utf-8 -*-

import os
import unittest
import mariadb

from ..base_test import create_connection, is_skysql, is_maxscale, is_mysql, is_native, is_async_native, get_host_suffix
from ..conftest import get_test_config as conf

class AsyncCursorTest(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.connection = await mariadb.AsyncConnection.connect(**conf())

    async def asyncTearDown(self):
        await self.connection.close()

    async def test_ping(self):
        if is_maxscale():
            self.skipTest("MAXSCALE return wrong thread id")

        new_conn = await mariadb.AsyncConnection.connect(**conf())
        id = new_conn.connection_id
        await self.connection.kill(id)
        try:
            await new_conn.ping()
        except (mariadb.InterfaceError, mariadb.DatabaseError):
            pass
        await new_conn.close()
        # Pure Python (native) doesn't implement auto_reconnect
        if not is_native() and not is_async_native():
            new_conn = await mariadb.AsyncConnection.connect(**conf())
            new_conn.auto_reconnect = True
            id = new_conn.connection_id
            await self.connection.kill(id)
            await new_conn.ping()
            new_id = new_conn.connection_id
            self.assertTrue(id != new_id)
            await new_conn.close()

    async def test_change_user(self):
        if is_skysql():
            self.skipTest("SkySQL failure")
        if is_maxscale():
            self.skipTest("MAXSCALE doesn't get new user immediately")
        if self.connection.server_name == "localhost":
            curs = await self.connection.cursor(buffered=True)
            await curs.execute("select * from information_schema.plugins "
                         "where plugin_name='unix_socket' "
                         "and plugin_status='ACTIVE'")
            if curs.rowcount > 0:
                await curs.close()
                self.skipTest("unix_socket is active")
            await curs.close()

        default_conf = conf()
        cursor = self.connection.cursor()
        #        os.environ["LOCAL_DB"] = "local"
        await cursor.execute("drop user if exists foo")
        if is_mysql() and self.connection.server_version < 80000:
            await cursor.execute("create user foo"+get_host_suffix())
            await cursor.execute("GRANT ALL on `"
                           + default_conf["database"] +
                           "`.* TO foo"+get_host_suffix()+" IDENTIFIED BY "
                           "'heyPassw-!µ20§rd'")
        else:
            await cursor.execute("create user foo"+get_host_suffix()+" IDENTIFIED "
                           "BY 'heyPassw-!µ20§rd'")
            await cursor.execute("GRANT ALL on `" + default_conf["database"] +
                           "`.* TO foo"+get_host_suffix())
        new_conn = await mariadb.AsyncConnection.connect(**conf())
        await new_conn.change_user("foo", "heyPassw-!µ20§rd", "")
        self.assertEqual("foo", new_conn.user)
        await cursor.execute("drop user foo"+get_host_suffix())
        await new_conn.close()
        await cursor.close()


    async def test_change_user_wrong(self):
        if is_skysql():
            self.skipTest("SkySQL failure")
        if is_maxscale():
            self.skipTest("MAXSCALE doesn't get new user immediately")

        default_conf = conf()
       
        new_conn = await mariadb.AsyncConnection.connect(**conf())
        with self.assertRaises(Exception):
            await new_conn.change_user("unknownUser", "mypassword", default_conf["database"])
        self.assertEqual(default_conf["user"], new_conn.user)
        await new_conn.close()

    async def test_reconnect(self):
        if is_maxscale():
            self.skipTest("MAXSCALE wrong thread id")
        if is_async_native():
            self.skipTest("Pure Python (native) doesn't support reconnect")
        new_conn = await mariadb.AsyncConnection.connect(**conf())
        conn1_id = new_conn.connection_id
        await self.connection.kill(conn1_id)
        await new_conn.reconnect()
        conn2_id = new_conn.connection_id
        self.assertFalse(conn1_id == conn2_id)
        await new_conn.close()


    async def test_reconnect_not_closed(self):
        if is_maxscale():
            self.skipTest("MAXSCALE wrong thread id")
        if is_async_native():
            self.skipTest("Pure Python (native) doesn't support reconnect")
        new_conn = await mariadb.AsyncConnection.connect(**conf())
        conn1_id = new_conn.connection_id
        await new_conn.reconnect()
        conn2_id = new_conn.connection_id
        self.assertFalse(conn1_id == conn2_id)
        await new_conn.close()

    async def test_reset(self):
        if self.connection.server_version < 100204:
            self.skipTest("RESET not supported")

        cursor = self.connection.cursor()
        await cursor.execute("SELECT 1 UNION SELECT 2")
        try:
            await self.connection.ping()
        except mariadb.InterfaceError:
            pass

        await self.connection.reset()
        await self.connection.ping()
        await cursor.close()

    async def test_warnings(self):
        conn = self.connection
        cursor = conn.cursor()

        await cursor.execute("SET session sql_mode=''")
        await cursor.execute("CREATE TEMPORARY TABLE test_warnings (a tinyint)")
        await cursor.execute("INSERT INTO test_warnings VALUES (300)")

        self.assertEqual(conn.warnings, 1)
        self.assertEqual(conn.warnings, cursor.warnings)
        await cursor.close()

    async def test_server_infos(self):
        self.assertTrue(self.connection.server_info)
        self.assertTrue(self.connection.server_version > 0)

    async def test_escape(self):
        cursor = self.connection.cursor()
        await cursor.execute("CREATE TEMPORARY TABLE test_escape (a varchar(100))")
        str = 'This is a \ and a \"'  # noqa: W605
        cmd = "INSERT INTO test_escape VALUES('%s')" % str

        try:
            await cursor.execute(cmd)
        except mariadb.DatabaseError:
            pass

        str = self.connection.escape_string(str)
        cmd = "INSERT INTO test_escape VALUES('%s')" % str
        await cursor.execute(cmd)
        await cursor.close()

    async def test_conpy279(self):
        conn = self.connection
        default_conf = conf()
        if "password" not in default_conf:
            default_conf["password"] = None
        try:
            await conn.change_user(None, None, None)
        except TypeError:
            pass
        await conn.change_user(default_conf["user"], default_conf["password"], None)
        await conn.close()


if __name__ == '__main__':
    unittest.main()
