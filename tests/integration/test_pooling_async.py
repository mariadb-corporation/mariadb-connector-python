#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

import unittest

import mariadb

from ..base_test import conf, is_native, is_skysql, is_maxscale

# Helper to create async connection
async def create_async_connection(additional_conf=None):
    """Helper to create async connection with optional additional config"""
    default_conf = conf()
    if additional_conf is None:
        c = {key: value for (key, value) in (default_conf.items())}
    else:
        c = {key: value for (key, value) in (list(default_conf.items()) + list(
            additional_conf.items()))}
    return await mariadb.AsyncConnection.connect(**c)

# Check if mariadb_pool is available and functional
try:
    from mariadb_pool import AsyncConnectionPool
    HAS_MARIADB_POOL = True
except (ImportError, AttributeError):
    HAS_MARIADB_POOL = False


@unittest.skipIf(not HAS_MARIADB_POOL or not is_native(),
                 "AsyncConnection or mariadb_pool package not installed")
class AsyncTestPooling(unittest.IsolatedAsyncioTestCase):

    async def create_pool(self, **kwargs):
        """Create an opened async pool over the test configuration"""
        default_conf = conf()
        default_conf.update(kwargs.pop("connection_conf", {}))
        return await mariadb.create_async_pool(**default_conf, **kwargs)

    async def test_async_connection_pool_removed(self):
        # CONPY-377: mariadb.ConnectionPool mirrors the 1.1 pool API, which
        # never had an async counterpart -- create_async_pool() is the only
        # way to build an async pool
        with self.assertRaises(AttributeError):
            mariadb.AsyncConnectionPool

    async def test_release_undrained_streaming_cursor(self):
        # A connection returned to the pool with an unconsumed streaming cursor
        # must be drained on release (reset_connection off) so the next user of
        # that same pooled connection gets a clean, usable connection.
        pool = await self.create_pool(pool_size=1,
                                      pool_reset_connection=False,
                                      acquire_timeout=2)
        try:
            conn = await pool.acquire()
            cur = conn.cursor(buffered=False)
            await cur.execute("SELECT 1 UNION SELECT 2 UNION SELECT 3")
            self.assertEqual((await cur.fetchone())[0], 1)
            await conn.close()

            conn = await pool.acquire()
            cur = conn.cursor()
            await cur.execute("SELECT 42")
            self.assertEqual((await cur.fetchone())[0], 42)
            await cur.close()
            await conn.close()
        finally:
            await pool.close()

    async def test_conpy246(self):
        # test if a pooled connection will be roll backed
        pool = await self.create_pool(pool_size=1,
                                      pool_reset_connection=False,
                                      acquire_timeout=1)
        conn = await pool.acquire()
        cursor = conn.cursor()
        await cursor.execute("DROP TABLE IF EXISTS conpy246")
        await cursor.execute("CREATE TABLE conpy246(a int)")
        await cursor.execute("INSERT INTO conpy246 VALUES (1)")
        await cursor.close()
        await conn.close()
        conn = await pool.acquire()
        cursor = conn.cursor()
        await cursor.execute("SELECT * FROM conpy246")
        self.assertEqual(cursor.rowcount, 0)
        await cursor.execute("DROP TABLE conpy246")
        await cursor.close()
        await conn.close()
        await pool.close()

    async def test_conpy250(self):
        pool = await self.create_pool(pool_size=8,
                                      pool_reset_connection=False,
                                      pool_validation_interval=0,
                                      acquire_timeout=1)
        self.assertEqual(len(pool._all_connections), 8)
        await pool.close()
        self.assertEqual(len(pool._all_connections), 0)

    async def test_conpy247_1(self):
        pool = await self.create_pool(pool_size=1,
                                      pool_reset_connection=False,
                                      acquire_timeout=1,
                                      ping_threshold=0)

        # service connection
        conn = await create_async_connection()
        cursor = conn.cursor()

        pconn = await pool.acquire()
        old_id = pconn.connection_id
        await cursor.execute("KILL %s" % (old_id,))
        await cursor.close()
        await pconn.close()

        pconn = await pool.acquire()
        self.assertNotEqual(old_id, pconn.connection_id)

        await conn.close()
        await pool.close()

    async def test_conpy247_2(self):
        pool = await self.create_pool(pool_size=1,
                                      pool_reset_connection=True,
                                      pool_validation_interval=0,
                                      acquire_timeout=1)

        # service connection
        conn = await create_async_connection()
        cursor = conn.cursor()

        pconn = await pool.acquire()
        old_id = pconn.connection_id
        await cursor.execute("KILL %s" % (old_id,))
        await cursor.close()
        await pconn.close()

        pconn = await pool.acquire()
        self.assertNotEqual(old_id, pconn.connection_id)

        await conn.close()
        await pool.close()

    async def test_conpy247_3(self):
        pool = await self.create_pool(pool_size=10,
                                      pool_reset_connection=True,
                                      pool_validation_interval=0,
                                      acquire_timeout=10)

        # service connection
        conn = await create_async_connection()
        cursor = conn.cursor()
        ids = []
        await cursor.execute("DROP PROCEDURE IF EXISTS p1")
        sql = """CREATE PROCEDURE p1()
                 BEGIN
                   SELECT 1;
                   SELECT 2;
                 END"""

        await cursor.execute(sql)
        try:
            for i in range(0, 10):
                pconn = await pool.acquire()
                ids.append(pconn.connection_id)
                await cursor.execute("KILL %s" % (pconn.connection_id,))
                await pconn.close()

            new_ids = []

            conns = []
            for i in range(0, 10):
                pconn = await pool.acquire()
                conns.append(pconn)
                new_ids.append(pconn.connection_id)
                self.assertEqual(pconn.connection_id in ids, False)
            for conn1 in conns:
                pcursor = conn1.cursor()
                await pcursor.callproc("p1")
                await pcursor.close()
                await conn1.close()

            for i in range(0, 10):
                pconn = await pool.acquire()
                self.assertEqual(pconn.connection_id in new_ids, True)
                await pconn.close()

            await conn.close()
        finally:
            await pool.close()

    async def test_conpy245(self):
        # we can't test performance here, but we can check if LRU works.
        # All connections must have been used the same number of times.
        pool_size = 64
        iterations = 100

        pool = await self.create_pool(pool_size=pool_size, acquire_timeout=1)
        for i in range(0, iterations):
            for j in range(0, pool_size):
                conn = await pool.acquire()
                await conn.close()

        for i in range(0, pool_size):
            conn = await pool.acquire()
            self.assertEqual(conn._pooled_connection.use_count, iterations + 1)
            await conn.close()

        await pool.close()

    async def test_connection_pool_maxconn(self):
        pool = await self.create_pool(pool_size=6, acquire_timeout=1)
        connections = []
        for i in range(0, 6):
            connections.append(await pool.acquire())

        with self.assertRaises(mariadb.PoolError):
            await pool.acquire()

        for c in connections:
            await c.close()
        await pool.close()

    async def test_conpy69(self):
        if is_skysql():
            self.skipTest("skipping on SkySQL")
        if is_maxscale():
            self.skipTest("skipping on maxscale, bug")

        conn = await create_async_connection()
        await conn.set_autocommit(True)
        cursor1 = conn.cursor()
        await cursor1.execute("CREATE SCHEMA IF NOT EXISTS 中文考试")
        await cursor1.execute("COMMIT")

        pool = await self.create_pool(connection_conf={"database": "中文考试"},
                                      min_size=0, max_size=20,
                                      acquire_timeout=1)
        try:
            pconn = await pool.acquire()
            await pconn.set_autocommit(True)
            cursor = pconn.cursor()
            await cursor.execute("select database()")
            row = await cursor.fetchone()
            self.assertEqual(row[0], "中文考试")
            await cursor.execute("CREATE TEMPORARY TABLE t1 "
                           "(a varchar(255)) character set utf8mb4")
            await cursor.execute("insert into t1 values (?)", ("123.45 中文考试",))
            await cursor.execute("select a from t1", buffered=True)
            row = await cursor.fetchone()
            self.assertEqual(row[0], "123.45 中文考试")
            await cursor1.execute("DROP SCHEMA 中文考试")
        finally:
            await pool.close()

    async def test_pool_query(self):
        pool = await self.create_pool(acquire_timeout=1)
        conn = await pool.acquire()
        cursor = conn.cursor()
        await cursor.execute("SELECT 1")
        row = await cursor.fetchone()
        self.assertEqual(row[0], 1)
        await cursor.close()
        await pool.close()

    async def test_pool_getter(self):
        default_conf = conf()
        pool = await self.create_pool(pool_size=4)
        self.assertEqual(pool.config.max_size, 4)
        self.assertEqual(pool.config.min_size, 4)
        if "pool_reset_connection" in default_conf:
            self.assertEqual(pool.config.reset_connection,
                             default_conf["pool_reset_connection"])
        else:
            self.assertEqual(pool.config.reset_connection, False)
        await pool.close()

    async def test_pool_getter_max(self):
        default_conf = conf()
        pool = await self.create_pool(pool_size=124)
        self.assertEqual(pool.config.max_size, 124)
        if "pool_reset_connection" in default_conf:
            self.assertEqual(pool.config.reset_connection,
                             default_conf["pool_reset_connection"])
        else:
            self.assertEqual(pool.config.reset_connection, False)
        await pool.close()

    async def test_pool_connection_reset(self):
        pool = await self.create_pool(pool_size=1)
        conn = await pool.acquire()
        cursor = conn.cursor()
        await cursor.execute("SELECT 1")
        await cursor.close()
        await conn.close()
        conn = await pool.acquire()
        cursor = conn.cursor()
        await cursor.execute("SELECT 2")
        row = await cursor.fetchone()
        self.assertEqual(row[0], 2)
        await pool.close()

    async def test_conpy256(self):
        size = 10
        connections = []
        pool = await self.create_pool(pool_size=size, acquire_timeout=1)
        for i in range(size):
            c = await pool.acquire()
            self.assertNotEqual(c in connections, True)
            connections.append(c)

        await pool.close()

    async def test_async_pool_connection_url(self):
        """Test creating async pool with connection URL"""
        default_conf = conf()

        # Build connection URL from config
        user = default_conf.get('user', 'root')
        password = default_conf.get('password', '')
        host = default_conf.get('host', 'localhost')
        port = default_conf.get('port', 3306)
        database = default_conf.get('database', 'test')

        # Test 1: pool options in the URL query string (ssl honours the suite
        # default)
        _ssl = f"&ssl={'true' if default_conf['ssl'] else 'false'}" if 'ssl' in default_conf else ""
        url = f"mariadb://{user}:{password}@{host}:{port}/{database}?max_size=3{_ssl}"
        pool = await mariadb.create_async_pool(url)
        try:
            self.assertEqual(pool.config.max_size, 3)
            async with await pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("SELECT 1")
                    result = await cursor.fetchone()
                    self.assertEqual(result[0], 1)
        finally:
            await pool.close()

        # Test 2: URL plus keyword arguments, the keyword argument winning
        url2 = f"mariadb://{user}:{password}@{host}:{port}/{database}?max_size=9"
        if 'ssl' in default_conf:
            url2 += f"&ssl={'true' if default_conf['ssl'] else 'false'}"
        pool2 = await mariadb.create_async_pool(url2, max_size=3)
        try:
            self.assertEqual(pool2.config.max_size, 3)
            async with await pool2.acquire() as conn2:
                async with conn2.cursor() as cursor2:
                    await cursor2.execute("SELECT 2")
                    result2 = await cursor2.fetchone()
                    self.assertEqual(result2[0], 2)
        finally:
            await pool2.close()

        # Test 3: connection parameters as keyword arguments
        pool3 = await mariadb.create_async_pool(
            user=user,
            password=password,
            host=host,
            port=port,
            database=database,
            ssl=default_conf.get('ssl', False),
            pool_size=2)
        try:
            async with await pool3.acquire() as conn3:
                async with conn3.cursor() as cursor3:
                    await cursor3.execute("SELECT 3")
                    result3 = await cursor3.fetchone()
                    self.assertEqual(result3[0], 3)
        finally:
            await pool3.close()

    async def test_pool_name_rejected(self):
        # CONPY-377: create_async_pool() returns the pool object, there is
        # nothing to look up by name
        default_conf = conf()
        with self.assertRaises(ValueError) as ctx:
            await mariadb.create_async_pool(pool_name="async_named",
                                            **default_conf)
        self.assertIn("pool_name", str(ctx.exception))

    async def test_create_async_pool(self):
        """Test mariadb.create_async_pool() function with clean parameter separation"""
        default_conf = conf()

        # Create pool using create_async_pool function (automatically calls pool.open())
        pool = await mariadb.create_async_pool(
            host=default_conf.get('host', 'localhost'),
            port=default_conf.get('port', 3306),
            user=default_conf.get('user', 'root'),
            password=default_conf.get('password', ''),
            database=default_conf.get('database', 'test'),
            # honour the suite's TLS setting (ssl=False by default) -- otherwise the
            # pool connects with secure-by-default ssl=True and acquire() times out
            # on a server without (verifiable) TLS (MaxScale, MariaDB 10.x).
            ssl=default_conf.get('ssl', False),
            min_size=5,
            max_size=10,
            ping_threshold=250,
            max_idle_time=300.0
        )

        # Verify pool configuration
        self.assertEqual(pool.config.min_size, 5)
        self.assertEqual(pool.config.max_size, 10)
        self.assertEqual(pool.config.ping_threshold, 250.0)
        self.assertEqual(pool.config.max_idle_time, 300.0)

        # Test getting a connection
        conn = await pool.acquire()
        self.assertIsNotNone(conn)

        # Test executing a query
        cursor = conn.cursor()
        await cursor.execute("SELECT 1 as test")
        result = await cursor.fetchone()
        self.assertEqual(result[0], 1)
        await cursor.close()

        # Return connection to pool
        await conn.close()

        # Clean up
        await pool.close()

    async def test_async_connect_pool_name_not_supported(self):
        # asyncConnect() doesn't support pools: it would either create a pool
        # as a side effect or ignore the given connection arguments
        default_conf = conf()
        with self.assertRaises(mariadb.ProgrammingError):
            await mariadb.asyncConnect(pool_name="async_no_pool",
                                       **default_conf)

if __name__ == '__main__':
    unittest.main()
