#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

import unittest

import mariadb
import platform

from ..base_test import conf, is_skysql, is_maxscale

# Check if AsyncConnection is available
HAS_ASYNC_CONNECTION = hasattr(mariadb, 'AsyncConnection') and mariadb.AsyncConnection is not None

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
    from mariadb_pool import AsyncConnectionPoolWrapper
    HAS_MARIADB_POOL = True
except (ImportError, AttributeError):
    HAS_MARIADB_POOL = False


@unittest.skipIf(not HAS_MARIADB_POOL or not HAS_ASYNC_CONNECTION,
                 "AsyncConnection or mariadb_pool package not installed")
class AsyncTestPooling(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        pass

    async def asyncTearDown(self):
        # Clean up any remaining pools
        for pool_name in list(mariadb._ASYNC_CONNECTION_POOLS.keys()):
            try:
                await mariadb._ASYNC_CONNECTION_POOLS[pool_name].close()
            except:
                pass
    
    @classmethod
    async def asyncTearDownClass(cls):
        """Ensure all async pools are closed at end of test class"""
        # Close all remaining pools to prevent segfaults
        for pool_name in list(mariadb._ASYNC_CONNECTION_POOLS.keys()):
            try:
                pool = mariadb._ASYNC_CONNECTION_POOLS[pool_name]
                if hasattr(pool, 'close'):
                    await pool.close()
            except:
                pass
        mariadb._ASYNC_CONNECTION_POOLS.clear()

    async def test_ASYNC_CONNECTION_POOLS(self):
        pool = mariadb.AsyncConnectionPool(pool_name="test_connection")
        self.assertEqual(mariadb._ASYNC_CONNECTION_POOLS["test_connection"], pool)
        await pool.close()
        self.assertEqual(mariadb._ASYNC_CONNECTION_POOLS, {})

    async def test_conpy39(self):
        try:
            mariadb.AsyncConnectionPool()
        except mariadb.ProgrammingError:
            pass

    async def test_conpy246(self):
        # test if a pooled connection will be roll backed

        default_conf = conf()

        pool = mariadb.AsyncConnectionPool(pool_name="CONPY246",
                                        pool_size=1,
                                        pool_reset_connection=False,
                                        acquire_timeout=1,
                                        **default_conf)
        await pool.open()
        conn = await pool.get_connection()
        cursor = conn.cursor()
        await cursor.execute("DROP TABLE IF EXISTS conpy246")
        await cursor.execute("CREATE TABLE conpy246(a int)")
        await cursor.execute("INSERT INTO conpy246 VALUES (1)")
        await cursor.close()
        await conn.close()
        conn = await pool.get_connection()
        cursor = conn.cursor()
        await cursor.execute("SELECT * FROM conpy246")
        self.assertEqual(cursor.rowcount, 0)
        await cursor.execute("DROP TABLE conpy246")
        await cursor.close()
        await conn.close()
        await pool.close()

    async def test_conpy250(self):
        default_conf = conf()
        pool = mariadb.AsyncConnectionPool(pool_name="CONPY250",
                                        pool_size=8,
                                        pool_reset_connection=False,
                                        pool_validation_interval=0,
                                        acquire_timeout=1,
                                        **default_conf)
        await pool.open()
        self.assertEqual(pool.connection_count, 8)
        await pool.close()
        self.assertEqual(pool.connection_count, 0)

    async def test_conpy247_1(self):
        default_conf = conf()
        pool = mariadb.AsyncConnectionPool(pool_name="CONPY247_1",
                                        pool_size=1,
                                        pool_reset_connection=False,
                                        pool_validation_interval=0,
                                        acquire_timeout=1,
                                        **default_conf)
        await pool.open()

        # service connection
        conn = await create_async_connection()
        cursor = conn.cursor()

        pconn = await pool.get_connection()
        old_id = pconn.connection_id
        await cursor.execute("KILL %s" % (old_id,))
        await cursor.close()
        await pconn.close()

        pconn = await pool.get_connection()
        self.assertNotEqual(old_id, pconn.connection_id)

        await conn.close()
        await pool.close()

    async def test_conpy247_2(self):
        default_conf = conf()
        pool = mariadb.AsyncConnectionPool(pool_name="CONPY247_2",
                                        pool_size=1,
                                        pool_reset_connection=True,
                                        pool_validation_interval=0,
                                        acquire_timeout=1,
                                        **default_conf)
        await pool.open()

        # service connection
        conn = await create_async_connection()
        cursor = conn.cursor()

        pconn = await pool.get_connection()
        old_id = pconn.connection_id
        await cursor.execute("KILL %s" % (old_id,))
        await cursor.close()
        await pconn.close()

        pconn = await pool.get_connection()
        self.assertNotEqual(old_id, pconn.connection_id)

        await conn.close()
        await pool.close()

    async def test_conpy247_3(self):
        default_conf = conf()
        pool = mariadb.AsyncConnectionPool(pool_name="CONPY247_3",
                                        pool_size=10,
                                        pool_reset_connection=True,
                                        pool_validation_interval=0,
                                        acquire_timeout=10,
                                        **default_conf)
        await pool.open()

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
                pconn = await pool.get_connection()
                ids.append(pconn.connection_id)
                await cursor.execute("KILL %s" % (pconn.connection_id,))
                await pconn.close()

            new_ids = []

            conns = []
            for i in range(0, 10):
                pconn = await pool.get_connection()
                conns.append(pconn)
                new_ids.append(pconn.connection_id)
                self.assertEqual(pconn.connection_id in ids, False)
            for conn1 in conns:    
                pcursor = conn1.cursor()
                await pcursor.callproc("p1")
                await pcursor.close()
                await conn1.close()

            for i in range(0, 10):
                pconn = await pool.get_connection()
                self.assertEqual(pconn.connection_id in new_ids, True)
                await pconn.close()

            await conn.close()
        finally:
            await pool.close()
            self.assertEqual(mariadb._ASYNC_CONNECTION_POOLS, {})

    async def test_conpy245(self):
        # we can't test performance here, but we can check if LRU works.
        # All connections must have been used the same number of times.

        default_conf = conf()
        pool_size = 64
        iterations = 100

        pool = mariadb.AsyncConnectionPool(pool_name="CONPY245",
                                        pool_size=pool_size,
                                        acquire_timeout=1,
                                        **default_conf)
        await pool.open()
        for i in range(0, iterations):
            for j in range(0, pool_size):
                conn = await pool.get_connection()
                await conn.close()

        for i in range(0, pool_size):
            conn = await pool.get_connection()
            self.assertEqual(conn._pooled_connection.use_count, iterations + 1)
            await conn.close()

        await pool.close()

    async def test_connection_pool_conf(self):
        pool = mariadb.AsyncConnectionPool(pool_name="test_conf", min_size=0, max_size=20)
        default_conf = conf()
        conn = await create_async_connection()
        try:
            await pool.add_connection(conn)
        except mariadb.PoolError:
            pass
        try:
            pool.set_config(**default_conf)
        except mariadb.Error:
            await pool.close()
            raise

        await pool.add_connection(conn)
        c = await pool.get_connection()
        self.assertEqual(c.connection_id, conn.connection_id)
        await pool.close()

    async def test_connection_pool_maxconn(self):
        default_conf = conf()
        pool = mariadb.AsyncConnectionPool(pool_name="test_max_size", pool_size=6, acquire_timeout=1,
                                        **default_conf)
        await pool.open()
        connections = []
        for i in range(0, 6):
            connections.append(await pool.get_connection())
        
        with self.assertRaises(mariadb.PoolError):
            await pool.get_connection()

        for c in connections:
            await c.close()
        await pool.close()

    async def test_connection_pool_add(self):
        default_conf = conf()
        pool = mariadb.AsyncConnectionPool(pool_name="test_connection_pool_add", min_size=0, max_size=20, acquire_timeout=1)
        try:
            pool.set_config(**default_conf)
        except mariadb.Error:
            await pool.close()
            raise

        for i in range(1, 6):
            await pool.add_connection()
        try:
            await pool.add_connection()
        except mariadb.PoolError:
            pass
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
        default_conf = conf()
        default_conf["database"] = "中文考试"
        pool = mariadb.AsyncConnectionPool(pool_name="test_conpy69", min_size=0, max_size=20, acquire_timeout=1)
        try:
            pool.set_config(**default_conf)
        except mariadb.Error:
            await pool.close()
            raise

        try:
            for i in range(1, 6):
                await pool.add_connection()
            pconn = await mariadb.asyncConnect(pool_name="test_conpy69")
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

    async def test__ASYNC_CONNECTION_POOLS(self):
        default_conf = conf()
        pool = mariadb.AsyncConnectionPool(pool_name="test_use", acquire_timeout=1, **default_conf)
        await pool.open()
        conn = await mariadb.asyncConnect(pool_name="test_use")
        cursor = conn.cursor()
        await cursor.execute("SELECT 1")
        row = await cursor.fetchone()
        self.assertEqual(row[0], 1)
        del cursor
        await pool.close()
        self.assertEqual(mariadb._ASYNC_CONNECTION_POOLS, {})

    async def test_create_pool_from_conn(self):
        default_conf = conf()
        key = "t1"
        conn = await mariadb.asyncConnect(pool_name=key, **default_conf)
        cursor = conn.cursor()
        pool = mariadb._ASYNC_CONNECTION_POOLS["t1"]
        del mariadb._ASYNC_CONNECTION_POOLS["t1"]
        self.assertEqual(mariadb._ASYNC_CONNECTION_POOLS, {})
        try:
            await cursor.execute("SELECT 1")
        except mariadb.ProgrammingError:
            pass
        await pool.close()

    async def test_pool_getter(self):
        default_conf = conf()
        await mariadb.asyncConnect(pool_name="getter_test",
                          pool_size=4, **default_conf)
        p = mariadb._ASYNC_CONNECTION_POOLS["getter_test"]
        self.assertEqual(p.pool_name, "getter_test")
        self.assertEqual(p.pool_size, 4)
        if "pool_reset_connection" in default_conf:
            self.assertEqual(p.pool_reset_connection,
                             default_conf["pool_reset_connection"])
        else:
            self.assertEqual(p.pool_reset_connection, True)
        self.assertEqual(p.max_size, 4)
        await mariadb._ASYNC_CONNECTION_POOLS["getter_test"].close()
        self.assertEqual(mariadb._ASYNC_CONNECTION_POOLS, {})


    async def test_pool_getter_max(self):
        default_conf = conf()
        await mariadb.asyncConnect(pool_name="getter_test",
                          pool_size=124, **default_conf)
        p = mariadb._ASYNC_CONNECTION_POOLS["getter_test"]
        self.assertEqual(p.pool_name, "getter_test")
        self.assertEqual(p.pool_size, 64)
        if "pool_reset_connection" in default_conf:
            self.assertEqual(p.pool_reset_connection,
                             default_conf["pool_reset_connection"])
        else:
            self.assertEqual(p.pool_reset_connection, True)
        self.assertEqual(p.max_size, 64)
        await mariadb._ASYNC_CONNECTION_POOLS["getter_test"].close()
        self.assertEqual(mariadb._ASYNC_CONNECTION_POOLS, {})

    async def test_pool_connection_reset(self):
        default_conf = conf()
        conn = await mariadb.asyncConnect(pool_name="reset_test",
                                 pool_size=1, **default_conf)
        cursor = conn.cursor()
        await cursor.execute("SELECT 1")
        await cursor.close()
        await conn.close()
        conn = await mariadb.asyncConnect(pool_name="reset_test")
        cursor = conn.cursor()
        await cursor.execute("SELECT 2")
        row = await cursor.fetchone()
        self.assertEqual(row[0], 2)
        await mariadb._ASYNC_CONNECTION_POOLS["reset_test"].close()

    async def test_conpy40(self):
        default_conf = conf()
        pool = mariadb.AsyncConnectionPool(pool_name='test_conpy40', min_size=0, max_size=3, acquire_timeout=1)

        try:
            pool.set_config(pool_size=3)
        except mariadb.PoolError:
            pass

        try:
            pool.set_config(**default_conf)
        except mariadb.Error:
            await pool.close()
            raise

        for j in range(3):
            c = await mariadb.asyncConnect(**default_conf)
            await pool.add_connection(c)
        await pool.close()

    async def test_pool_add(self):
        pool = mariadb.AsyncConnectionPool(pool_name="test_pool_add", acquire_timeout=1)
        try:
            mariadb.AsyncConnectionPool(pool_name="test_pool_add")
        except (mariadb.ProgrammingError, mariadb.PoolError):
            pass
        await pool.close()
        self.assertEqual(mariadb._ASYNC_CONNECTION_POOLS, {})

    async def test_conpy256(self):
        size = 10
        connections = []
        default_conf = conf()
        pool = mariadb.AsyncConnectionPool(pool_name="test_conpy256",
                                        pool_size=size, acquire_timeout=1, **default_conf)
        await pool.open()
        for i in range(size):
            c = await pool.get_connection()
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
        
        # Test 1: URL with pool_name in query params
        url = f"mariadb://{user}:{password}@{host}:{port}/{database}?pool_name=test_url_pool"
        async with mariadb.AsyncConnectionPool(url) as pool:
            await pool.open()
            
            # Verify pool is registered
            self.assertIn("test_url_pool", mariadb._ASYNC_CONNECTION_POOLS)
            self.assertEqual(pool.pool_name, "test_url_pool")
            
            # Test connection works
            async with await pool.get_connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("SELECT 1")
                    result = await cursor.fetchone()
                    self.assertEqual(result[0], 1)
        
        self.assertNotIn("test_url_pool", mariadb._ASYNC_CONNECTION_POOLS)
        
        # Test 2: URL as first arg, pool_name as kwarg
        url2 = f"mariadb://{user}:{password}@{host}:{port}/{database}"
        async with mariadb.AsyncConnectionPool(url2, pool_name="test_url_pool2", pool_size=3) as pool2:
            await pool2.open()
        
            self.assertIn("test_url_pool2", mariadb._ASYNC_CONNECTION_POOLS)
            self.assertEqual(pool2.pool_name, "test_url_pool2")
            
            # Test connection works
            async with await pool2.get_connection() as conn2:
                async with conn2.cursor() as cursor2:
                    await cursor2.execute("SELECT 2")
                    result2 = await cursor2.fetchone()
                    self.assertEqual(result2[0], 2)
            
        self.assertNotIn("test_url_pool2", mariadb._ASYNC_CONNECTION_POOLS)
        
        # Test 3: Pool name as first arg, connection params as kwargs
        async with mariadb.AsyncConnectionPool("test_url_pool3", 
                                           user=user,
                                           password=password,
                                           host=host,
                                           port=port,
                                           database=database,
                                           pool_size=2) as pool3:
            await pool3.open()
        
            self.assertIn("test_url_pool3", mariadb._ASYNC_CONNECTION_POOLS)
            self.assertEqual(pool3.pool_name, "test_url_pool3")
            
            async with await pool3.get_connection() as conn3:
                async with conn3.cursor() as cursor3:
                    await cursor3.execute("SELECT 3")
                    result3 = await cursor3.fetchone()
                    self.assertEqual(result3[0], 3)
        
        # Test 4 name and url
        async with mariadb.AsyncConnectionPool("test_url_pool4", url2 , pool_size=3) as pool4:
            await pool4.open()
        
            self.assertIn("test_url_pool4", mariadb._ASYNC_CONNECTION_POOLS)
            self.assertEqual(pool4.pool_name, "test_url_pool4")
            
            # Test connection works
            async with await pool4.get_connection() as conn4:
                await conn4.open()
            
        self.assertNotIn("test_url_pool2", mariadb._ASYNC_CONNECTION_POOLS)
        
        self.assertNotIn("test_url_pool3", mariadb._ASYNC_CONNECTION_POOLS)

if __name__ == '__main__':
    unittest.main()
