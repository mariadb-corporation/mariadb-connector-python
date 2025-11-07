#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

import os
import unittest
import platform
import traceback
import sys
from pathlib import Path

# Add the mariadb source module to the path BEFORE importing
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import mariadb
# Import constants as module attribute, not submodule
STATUS = mariadb.constants.STATUS
from packaging.version import parse as parse_version
from packaging import version

from ..base_test import is_skysql, is_maxscale, is_native, get_host_suffix
from ..conftest import get_test_config as conf

# Check if AsyncConnection is available
HAS_ASYNC_CONNECTION = hasattr(mariadb, 'AsyncConnection') and mariadb.AsyncConnection is not None

@unittest.skipIf(not HAS_ASYNC_CONNECTION, "AsyncConnection not available")
class AsyncTestConnection(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        config = conf()
        self.connection = await mariadb.AsyncConnection.connect(**config)

    async def asyncTearDown(self):
        await self.connection.close()

    async def test_conpy36(self):
        if platform.system() == "Windows":
            self.skipTest("unix_socket not supported on Windows")
        default_conf = conf()
        try:
            await mariadb.AsyncConnection.connect(
                user=default_conf["user"],
                unix_socket="/does_not_exist/x.sock",
                port=default_conf["port"],
                host=default_conf["host"]
            )
        except (mariadb.OperationalError,):
            # make asan happy
            tb = sys.exc_info()[2]
            traceback.clear_frames(tb)
            pass

    async def test_connection_default_file(self):
        if is_native():
            self.skipTest("default file not supported on native yet")
        if os.path.exists("client.cnf"):
            os.remove("client.cnf")
        default_conf = conf()
        f = open("client.cnf", "w+")
        f.write("[client]\n")
        f.write("host =%s\n" % default_conf["host"])
        f.write("port =%i\n" % default_conf["port"])
        f.write("user =%s\n" % default_conf["user"])
        if "password" in default_conf:
            f.write("password =%s\n" % default_conf["password"])
        f.write("database =%s\n" % default_conf["database"])
        f.close()

        new_conn = await mariadb.AsyncConnection.connect(
            user=default_conf["user"], ssl=True,
            default_file="./client.cnf"
        )
        self.assertEqual(new_conn.database, default_conf["database"])
        await new_conn.close()
        os.remove("client.cnf")

    async def test_autocommit(self):
        conn = self.connection
        await conn.set_autocommit(False)
        self.assertEqual(conn.autocommit, False)
        # revert
        await conn.set_autocommit(True)
        self.assertEqual(conn.autocommit, True)

    async def test_local_infile(self):
        default_conf = conf()
        new_conn = await mariadb.AsyncConnection.connect(**default_conf, local_infile=False)
        cursor = new_conn.cursor()
        await cursor.execute("CREATE TEMPORARY TABLE t1 (a int)")
        try:
            await cursor.execute("LOAD DATA LOCAL INFILE 'x.x' INTO TABLE t1")
        except (mariadb.OperationalError, mariadb.DatabaseError):
            # make asan happy
            if mariadb._have_asan:
                tb = sys.exc_info()[2]
                traceback.clear_frames(tb)
            pass
        await cursor.close()
        await new_conn.close()

    async def test_tls_version(self):
        if is_maxscale():
            self.skipTest("MAXSCALE test has no SSL on port by default")
        default_conf = conf()
        conn = await mariadb.AsyncConnection.connect(**default_conf, tls_version="TLSv1.2")
        cursor = conn.cursor()
        await cursor.execute("SHOW STATUS LIKE 'ssl_version'")
        row = await cursor.fetchone()
        self.assertEqual(row[1], "TLSv1.2")
        await cursor.close()
        await conn.close()

    async def test_init_command(self):
        default_conf = conf()
        new_conn = await mariadb.AsyncConnection.connect(**default_conf, init_command="SET @a:=1")
        cursor = new_conn.cursor()
        await cursor.execute("SELECT @a")
        row = await cursor.fetchone()
        self.assertEqual(row[0], 1)
        await cursor.close()
        await new_conn.close()

    async def test_compress(self):
        default_conf = conf()
        new_conn = await mariadb.AsyncConnection.connect(**default_conf, compress=True)
        cursor = new_conn.cursor()
        await cursor.execute("SHOW SESSION STATUS LIKE 'compression'")
        row = await cursor.fetchone()
        if is_maxscale() or is_native():
            self.assertEqual(row[1], "OFF")
        else:
            self.assertEqual(row[1], "ON")
        await cursor.close()
        await new_conn.close()

    async def test_schema(self):
        if self.connection.server_version < 100202:
            self.skipTest("session tracking not supported")
        if is_maxscale():
            self.skipTest("MAXSCALE doesn't tell schema change for now")

        default_conf = conf()
        conn = await mariadb.AsyncConnection.connect(**default_conf)
        self.assertEqual(conn.database, default_conf["database"])
        cursor = conn.cursor()
        await cursor.execute("DROP SCHEMA IF EXISTS test1")
        await cursor.execute("CREATE SCHEMA test1")
        await cursor.execute("USE test1")
        self.assertEqual(conn.database, "test1")
        await conn.select_db(default_conf["database"])
        self.assertEqual(conn.database, default_conf["database"])
        await cursor.close()
        await conn.close()

    async def test_ping(self):
        if is_maxscale():
            self.skipTest("MAXSCALE wrong thread id")
        config = conf()
        async with await mariadb.AsyncConnection.connect(**config) as conn:
            cursor = conn.cursor()
            oldid = conn.connection_id

            try:
                await cursor.execute("KILL {id}".format(id=oldid))
            except (mariadb.Error, mariadb.OperationalError):
                pass
            await cursor.close()
            
            try:
                await conn.ping()
            except (mariadb.InterfaceError, mariadb.DatabaseError):
                pass

    async def test_ed25519(self):
        if is_native():
            self.skipTest("Ed25519 not supported on native")
        if is_skysql():
            self.skipTest("Test fail on SkySQL")
        default_conf = conf()
        if is_maxscale():
            self.skipTest("MAXSCALE doesn't support ed25519 for now")
        if self.connection.server_version < 100122:
            self.skipTest("ed25519 not supported")

        conn = await mariadb.AsyncConnection.connect(**default_conf)
        curs = conn.cursor()

        if self.connection.server_name == "localhost":
            await curs.execute("select * from information_schema.plugins where "
                         "plugin_name ='unix_socket' and "
                         "plugin_status ='ACTIVE'")
            rows = await curs.fetchall()
            if len(rows) > 0:
                await curs.close()
                await conn.close()
                self.skipTest("unix_socket is active")

        cursor = conn.cursor()
        try:
            await cursor.execute("INSTALL SONAME 'auth_ed25519'")
        except (mariadb.DatabaseError, mariadb.OperationalError):
            await cursor.close()
            await conn.close()
            self.skipTest("Server couldn't load auth_ed25519")
        await cursor.execute("DROP USER IF EXISTS eduser")
        if self.connection.server_version < 100400:
            await cursor.execute("CREATE USER eduser"+get_host_suffix()+" IDENTIFIED VIA ed25519 "
                           "USING "
                           "'6aW9C7ENlasUfymtfMvMZZtnkCVlcb1ssxOLJ0kj/AA'")
        else:
            await cursor.execute("CREATE USER eduser"+get_host_suffix()+" IDENTIFIED VIA ed25519 "
                           "USING PASSWORD('MySup8%rPassw@ord')")
        await cursor.execute("GRANT ALL on " + default_conf["database"] +
                       ".* to eduser"+get_host_suffix())
        
        ed_conf = default_conf.copy()
        ed_conf["user"] = "eduser"
        ed_conf["password"] = "MySup8%rPassw@ord"
        conn2 = await mariadb.AsyncConnection.connect(**ed_conf)
        
        await cursor.execute("DROP USER IF EXISTS eduser"+get_host_suffix())
        await cursor.close()
        await curs.close()
        await conn2.close()
        await conn.close()

    async def test_conpy46(self):
        config = conf()
        async with await mariadb.AsyncConnection.connect(**config) as con:
            cursor = con.cursor()
            await cursor.execute("SELECT 'foo'")
            row = await cursor.fetchone()
            self.assertEqual(row[0], "foo")
            await cursor.close()
            
            try:
                await cursor.execute("SELECT 'bar'")
            except mariadb.ProgrammingError:
                pass
        try:
            cursor = con.cursor()
        except mariadb.ProgrammingError:
            pass

    async def test_conpy101(self):
        default_conf = conf()
        c1 = await mariadb.AsyncConnection.connect(**default_conf)
        self.assertEqual(c1.autocommit, False)
        await c1.close()
        c1 = await mariadb.AsyncConnection.connect(**default_conf, autocommit=True)
        self.assertEqual(c1.autocommit, True)
        await c1.close()

    async def test_db_attribute(self):
        config = conf()
        async with await mariadb.AsyncConnection.connect(**config) as con:
            cursor = con.cursor()
            await cursor.execute("drop schema if exists test123")
            db = con.database
            try:
                await cursor.execute("create schema test123")
            except mariadb.Error:
                pass
            await con.select_db("test123")
            await cursor.execute("select database()")
            row = await cursor.fetchone()
            self.assertEqual(row[0], "test123")
            await con.select_db(db)
            await cursor.execute("select database()")
            row = await cursor.fetchone()
            self.assertEqual(row[0], db)
            self.assertEqual(row[0], con.database)
            await cursor.execute("drop schema test123")
            await cursor.close()

    async def test_server_status(self):
        config = conf()
        con = await mariadb.AsyncConnection.connect(**config)
        self.assertTrue(not con.server_status & STATUS.AUTOCOMMIT)
        await con.set_autocommit(True)
        self.assertTrue(con.server_status & STATUS.AUTOCOMMIT)
        await con.set_autocommit(False)
        self.assertTrue(not con.server_status & STATUS.AUTOCOMMIT)
        await con.close()

    async def test_conpy175(self):
        default_conf = conf()
        conn = await mariadb.AsyncConnection.connect(**default_conf)
        str = "Bob's"
        cursor = conn.cursor()
        await cursor.execute("SET session sql_mode='NO_BACKSLASH_ESCAPES'")
        newstr = conn.escape_string(str)
        self.assertEqual(newstr, "Bob''s")
        await cursor.execute("SET session sql_mode=''")
        newstr = conn.escape_string(str)
        self.assertEqual(newstr, "Bob\\'s")
        await cursor.close()
        await conn.close()

    async def test_closed(self):
        default_conf = conf()
        conn = await mariadb.AsyncConnection.connect(**default_conf)
        await conn.close()
        try:
            conn.cursor()
        except (mariadb.ProgrammingError):
            pass

    async def test_multi_host(self):
        default_conf = conf()
        default_conf["host"] = "non_existant," + default_conf["host"]
        default_conf["connect_timeout"] = 1
        try:
            await mariadb.AsyncConnection.connect(**default_conf)
        except mariadb.ProgrammingError:
            self.assertLess(parse_version(mariadb.mariadbapi_version),
                            parse_version('3.3.0'))
            pass

    async def test_tls_verification(self):
        if is_maxscale():
            self.skipTest("MAXSCALE test has no SSL on port by default")
        if mariadb.mariadbapi_version is not None and version.Version(mariadb.mariadbapi_version) <\
               version.Version('3.4.2'):
            self.skipTest("Requires C/C 3.4.2 or newer")
        default_conf = conf()
        default_conf["ssl"] = False
        conn = await mariadb.AsyncConnection.connect(**default_conf)
        self.assertEqual(conn._tls_verify_status, None)
        await conn.close()
        default_conf = conf()
        default_conf["ssl"] = True
        conn = await mariadb.AsyncConnection.connect(**default_conf)
        self.assertNotEqual(conn._tls_verify_status, None)
        await conn.close()

    async def test_tls_fp(self):
        if is_maxscale():
            self.skipTest("MAXSCALE test has no SSL on port by default")
        if mariadb.mariadbapi_version is not None and version.Version(mariadb.mariadbapi_version) <\
               version.Version('3.4.2'):
            self.skipTest("Requires C/C 3.4.2 or newer")
        default_conf = conf()
        default_conf["ssl"] = True
        conn = await mariadb.AsyncConnection.connect(**default_conf)
        self.assertEqual(conn._tls, True)
        x509_info = conn.tls_peer_cert_info
        if not x509_info:
            await conn.close()
            self.skipTest("Peer certificate information not supported")
        fp = x509_info["fingerprint"]
        self.assertEqual(len(fp), 64)
        await conn.close()
        default_conf = conf()
        default_conf["tls_fp"] = fp
        conn = await mariadb.AsyncConnection.connect(**default_conf)
        self.assertEqual(conn._tls, True)
        x509_info = conn.tls_peer_cert_info
        self.assertEqual(fp, x509_info["fingerprint"])
        await conn.close()

    async def test_conpy278(self):
        if is_maxscale():
            self.skipTest("MAXSCALE bug MXS-4961")
        if is_native():
            self.skipTest("reconnect doesn't work with native connector")
        
        config = conf()
        config["reconnect"] = True
        
        async with await mariadb.AsyncConnection.connect(**config) as conn:
            old_id = conn.connection_id
            try:
                await conn.kill(conn.connection_id)
            except mariadb.OperationalError:
                await conn.ping()
            self.assertNotEqual(old_id, conn.connection_id)
        
        async with await mariadb.AsyncConnection.connect(**config) as conn:
            old_id = conn.connection_id
            try:
                await conn.kill(conn.connection_id)
            except mariadb.OperationalError:
                await conn.ping()
            self.assertNotEqual(old_id, conn.connection_id)
        
        async with await mariadb.AsyncConnection.connect(**config) as conn:
            old_id = conn.connection_id
            try:
                await conn.kill(conn.connection_id)
            except mariadb.OperationalError:
                pass
            cursor = conn.cursor()
            try:
                await cursor.execute("set @a:=1")
            except mariadb.InterfaceError:
                pass
            await cursor.execute("set @a:=1")
            self.assertNotEqual(old_id, conn.connection_id)

            old_id = conn.connection_id
            await conn.reconnect()
            self.assertNotEqual(old_id, conn.connection_id)
            await cursor.close()


if __name__ == '__main__':
    unittest.main()
