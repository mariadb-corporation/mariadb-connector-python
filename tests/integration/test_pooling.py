#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

import unittest
import os
import mariadb
import platform

from ..base_test import create_connection, conf, is_skysql, is_maxscale

# Check if mariadb_pool is available and functional
try:
    from mariadb_pool import ConnectionPoolWrapper
    HAS_MARIADB_POOL = True
except (ImportError, AttributeError):
    HAS_MARIADB_POOL = False



@unittest.skipIf(not HAS_MARIADB_POOL,
                 "mariadb_pool package not installed")
class TestPooling(unittest.TestCase):

    def setUp(self):
        pass

    #         self.connection = create_connection()
    #         self.connection.autocommit = False

    def tearDown(self):
        # Clean up any remaining pools
        for pool_name in list(mariadb._CONNECTION_POOLS.keys()):
            try:
                mariadb._CONNECTION_POOLS[pool_name].close()
            except:
                pass
    
    @classmethod
    def tearDownClass(cls):
        """Ensure all pools are closed at end of test class"""
        # Close all remaining pools to prevent segfaults
        for pool_name in list(mariadb._CONNECTION_POOLS.keys()):
            try:
                pool = mariadb._CONNECTION_POOLS[pool_name]
                if hasattr(pool, 'close'):
                    pool.close()
            except:
                pass
        mariadb._CONNECTION_POOLS.clear()

    #         del self.connection

    def test_connection_pools(self):
        pool = mariadb.ConnectionPool(pool_name="test_connection")
        self.assertEqual(mariadb._CONNECTION_POOLS["test_connection"], pool)
        pool.close()
        self.assertEqual(mariadb._CONNECTION_POOLS, {})

    def test_conpy39(self):
        try:
            mariadb.ConnectionPool()
        except mariadb.ProgrammingError:
            pass

    def test_conpy246(self):
        # test if a pooled connection will be roll backed

        default_conf = conf()

        pool = mariadb.ConnectionPool(pool_name="CONPY246",
                                        pool_size=1,
                                        pool_reset_connection=False,
                                        acquire_timeout=1,
                                        **default_conf)
        conn = pool.get_connection()
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS conpy246")
        cursor.execute("CREATE TABLE conpy246(a int)")
        cursor.execute("INSERT INTO conpy246 VALUES (1)")
        cursor.close()
        conn.close()
        conn = pool.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM conpy246")
        self.assertEqual(cursor.rowcount, 0)
        cursor.execute("DROP TABLE conpy246")
        cursor.close()
        conn.close()
        pool.close()

    def test_conpy250(self):
        default_conf = conf()
        pool = mariadb.ConnectionPool(pool_name="CONPY250",
                                        pool_size=8,
                                        pool_reset_connection=False,
                                        pool_validation_interval=0,
                                        acquire_timeout=1,
                                        **default_conf)
        self.assertEqual(pool.connection_count, 8)
        pool.close()
        self.assertEqual(pool.connection_count, 0)

    def test_conpy247_1(self):
        default_conf = conf()
        pool = mariadb.ConnectionPool(pool_name="CONPY247_1",
                                        pool_size=1,
                                        pool_reset_connection=False,
                                        pool_validation_interval=0,
                                        acquire_timeout=1,
                                        ping_threshold=0,
                                        **default_conf)

        # service connection
        conn = create_connection()
        cursor = conn.cursor()

        pconn = pool.get_connection()
        old_id = pconn.connection_id
        cursor.execute("KILL %s" % (old_id,))
        cursor.close()
        pconn.close()

        pconn = pool.get_connection()
        self.assertNotEqual(old_id, pconn.connection_id)

        conn.close()
        pool.close()

    def test_conpy247_2(self):
        default_conf = conf()
        with mariadb.ConnectionPool(pool_name="CONPY247_2",
                                        pool_size=1,
                                        pool_reset_connection=True,
                                        pool_validation_interval=0,
                                        acquire_timeout=1,
                                        **default_conf) as pool:

            # service connection
            conn = create_connection()
            cursor = conn.cursor()

            pconn = pool.get_connection()
            old_id = pconn.connection_id
            cursor.execute("KILL %s" % (old_id,))
            cursor.close()
            pconn.close()

            pconn = pool.get_connection()
            self.assertNotEqual(old_id, pconn.connection_id)

            conn.close()

    def test_conpy247_3(self):
        default_conf = conf()
        pool = mariadb.ConnectionPool(pool_name="CONPY247_3",
                                        pool_size=10,
                                        pool_reset_connection=True,
                                        pool_validation_interval=0,
                                        acquire_timeout=10,
                                        **default_conf)

        # service connection
        conn = create_connection()
        cursor = conn.cursor()
        ids = []
        cursor.execute("DROP PROCEDURE IF EXISTS p1")
        sql = """CREATE PROCEDURE p1()
                 BEGIN
                   SELECT 1;
                   SELECT 2;
                 END"""

        cursor.execute(sql)
        try:
            for i in range(0, 10):
                pconn = pool.get_connection()
                ids.append(pconn.connection_id)
                cursor.execute("KILL %s" % (pconn.connection_id,))
                pconn.close()

            new_ids = []

            conns = []
            for i in range(0, 10):
                pconn = pool.get_connection()
                conns.append(pconn)
                new_ids.append(pconn.connection_id)
                self.assertEqual(pconn.connection_id in ids, False)
            for conn1 in conns:    
                pcursor = conn1.cursor()
                pcursor.callproc("p1")
                pcursor.close()
                conn1.close()

            for i in range(0, 10):
                pconn = pool.get_connection()
                self.assertEqual(pconn.connection_id in new_ids, True)
                pconn.close()

            conn.close()
        finally:
            pool.close()
            self.assertEqual(mariadb._CONNECTION_POOLS, {})

    def test_conpy245(self):
        if os.environ.get('RUN_LONG_TEST') != '1':
            self.skipTest("Skipping long-running test. Set RUN_LONG_TEST=1 to run.")           
        # we can't test performance here, but we can check if LRU works.
        # All connections must have been used the same number of times.

        default_conf = conf()
        pool_size = 64
        iterations = 100

        pool = mariadb.ConnectionPool(pool_name="CONPY245",
                                        pool_size=pool_size,
                                        acquire_timeout=1,
                                        **default_conf)
        for i in range(0, iterations):
            for j in range(0, pool_size):
                conn = pool.get_connection()
                conn.close()

        for i in range(0, pool_size):
            conn = pool.get_connection()
            self.assertEqual(conn._pooled_connection.use_count, iterations + 1)
            conn.close()

        pool.close()

    def test_connection_pool_conf(self):
        pool = mariadb.ConnectionPool(pool_name="test_conf", min_size=0, max_size=20)
        default_conf = conf()
        conn = create_connection()
        try:
            pool.add_connection(conn)
        except mariadb.PoolError:
            pass
        try:
            pool.set_config(**default_conf)
        except mariadb.Error:
            pool.close()
            raise

        pool.add_connection(conn)
        c = pool.get_connection()
        self.assertEqual(c.connection_id, conn.connection_id)
        pool.close()

    def test_connection_pool_maxconn(self):
        default_conf = conf()
        pool = mariadb.ConnectionPool(pool_name="test_max_size", pool_size=6, acquire_timeout=1,
                                        **default_conf)
        print(pool.pool_size)
        connections = []
        for i in range(0, 6):
            connections.append(pool.get_connection())
        self.assertRaises(mariadb.PoolError, lambda:pool.get_connection())

        for c in connections:
            print(c.connection_id)
            c.close()
        pool.close()

    def test_connection_pool_add(self):
        default_conf = conf()
        pool = mariadb.ConnectionPool(pool_name="test_connection_pool_add", min_size=0, max_size=20, acquire_timeout=1)
        try:
            pool.set_config(**default_conf)
        except mariadb.Error:
            pool.close()
            raise

        for i in range(1, 6):
            pool.add_connection()
        try:
            pool.add_connection()
        except mariadb.PoolError:
            pass
        pool.close()

    def test_conpy69(self):
        if is_skysql():
            self.skipTest("skipping on SkySQL")
        if is_maxscale():
            self.skipTest("skipping on maxscale, bug")

        conn = create_connection()
        conn.autocommit = True
        cursor1 = conn.cursor()
        cursor1.execute("CREATE SCHEMA IF NOT EXISTS 中文考试")
        cursor1.execute("COMMIT")
        default_conf = conf()
        default_conf["database"] = "中文考试"
        pool = mariadb.ConnectionPool(pool_name="test_conpy69", min_size=0, max_size=20, acquire_timeout=1)
        try:
            pool.set_config(**default_conf)
        except mariadb.Error:
            pool.close()
            raise

        try:
            for i in range(1, 6):
                pool.add_connection()
            conn = mariadb.connect(pool_name="test_conpy69",
                                   **default_conf)
            conn.autocommit = True
            cursor = conn.cursor()
            cursor.execute("select database()")
            row = cursor.fetchone()
            self.assertEqual(row[0], "中文考试")
            cursor.execute("CREATE TEMPORARY TABLE t1 "
                           "(a varchar(255)) character set utf8mb4")
            cursor.execute("insert into t1 values (?)", ("123.45 中文考试",))
            cursor.execute("select a from t1", buffered=True)
            row = cursor.fetchone()
            self.assertEqual(row[0], "123.45 中文考试")
            cursor1.execute("DROP SCHEMA 中文考试")
        finally:
            pool.close()

    def test__CONNECTION_POOLS(self):
        default_conf = conf()
        pool = mariadb.ConnectionPool(pool_name="test_use", acquire_timeout=1, **default_conf)
        conn = mariadb.connect(pool_name="test_use", **default_conf)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        row = cursor.fetchone()
        self.assertEqual(row[0], 1)
        del cursor
        pool.close()
        self.assertEqual(mariadb._CONNECTION_POOLS, {})

    def test_create_pool_from_conn(self):
        default_conf = conf()
        key = "t1"
        conn = mariadb.connect(pool_name=key, **default_conf)
        cursor = conn.cursor()
        p = mariadb._CONNECTION_POOLS["t1"]
        del mariadb._CONNECTION_POOLS["t1"]
        self.assertEqual(mariadb._CONNECTION_POOLS, {})
        try:
            cursor.execute("SELECT 1")
        except mariadb.ProgrammingError:
            pass
        p.close()

    def test_pool_getter(self):
        default_conf = conf()
        mariadb.connect(pool_name="getter_test",
                          pool_size=4, **default_conf)
        p = mariadb._CONNECTION_POOLS["getter_test"]
        self.assertEqual(p.pool_name, "getter_test")
        self.assertEqual(p.pool_size, 4)
        if "pool_reset_connection" in default_conf:
            self.assertEqual(p.pool_reset_connection,
                             default_conf["pool_reset_connection"])
        else:
            self.assertEqual(p.pool_reset_connection, True)
        self.assertEqual(p.max_size, 4)
        mariadb._CONNECTION_POOLS["getter_test"].close()
        self.assertEqual(mariadb._CONNECTION_POOLS, {})


    def test_pool_getter_max_size(self):
        default_conf = conf()
        mariadb.connect(pool_name="getter_test",
                          pool_size=124, **default_conf)
        p = mariadb._CONNECTION_POOLS["getter_test"]
        self.assertEqual(p.pool_name, "getter_test")
        self.assertEqual(p.pool_size, 64)
        if "pool_reset_connection" in default_conf:
            self.assertEqual(p.pool_reset_connection,
                             default_conf["pool_reset_connection"])
        else:
            self.assertEqual(p.pool_reset_connection, True)
        self.assertEqual(p.max_size, 64)
        mariadb._CONNECTION_POOLS["getter_test"].close()
        self.assertEqual(mariadb._CONNECTION_POOLS, {})


    def test_pool_connection_reset(self):
        default_conf = conf()
        conn = mariadb.connect(pool_name="reset_test",
                                 pool_size=1, **default_conf)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        conn = mariadb.connect(pool_name="reset_test", **default_conf)
        cursor = conn.cursor()
        cursor.execute("SELECT 2")
        row = cursor.fetchone()
        self.assertEqual(row[0], 2)
        mariadb._CONNECTION_POOLS["reset_test"].close()

    def test_conpy40(self):
        default_conf = conf()
        pool = mariadb.ConnectionPool(pool_name='test_conpy40', min_size=0, max_size=3, acquire_timeout=1)

        try:
            pool.set_config(pool_size=3)
        except mariadb.PoolError:
            pass

        try:
            pool.set_config(**default_conf)
        except mariadb.Error:
            pool.close()
            raise

        for j in range(3):
            c = mariadb.connect(**default_conf)
            pool.add_connection(c)
        pool.close()

    def test_pool_add(self):
        pool = mariadb.ConnectionPool(pool_name="test_pool_add", acquire_timeout=1)
        try:
            mariadb.ConnectionPool(pool_name="test_pool_add")
        except (mariadb.ProgrammingError, mariadb.PoolError):
            pass
        pool.close()
        self.assertEqual(mariadb._CONNECTION_POOLS, {})

    def test_conpy256(self):
        size = 10
        connections = []
        default_conf = conf()
        pool = mariadb.ConnectionPool(pool_name="test_conpy256",
                                        pool_size=size, acquire_timeout=1, **default_conf)
        for i in range(size):
            c= pool.get_connection()
            self.assertNotEqual(c in connections, True)
            connections.append(c)

        pool.close()

    def test_create_pool(self):
        """Test mariadb.create_pool() function with clean parameter separation"""
        default_conf = conf()
        
        # Create pool using create_pool function
        pool = mariadb.create_pool(
            host=default_conf.get('host', 'localhost'),
            port=default_conf.get('port', 3306),
            user=default_conf.get('user', 'root'),
            password=default_conf.get('password', ''),
            database=default_conf.get('database', 'test'),
            # Honour the suite's TLS setting (ssl=False by default). Without it the
            # pool would connect with the secure-by-default ssl=True and never be
            # able to create a connection on a server without (verifiable) TLS --
            # e.g. MariaDB 10.x -- so acquire() would time out with a PoolError.
            ssl=default_conf.get('ssl', False),
            min_size=5,
            max_size=10,
            ping_threshold=0.25,
            max_idle_time=300.0
        )
        
        # Verify pool configuration
        self.assertEqual(pool.config.min_size, 5)
        self.assertEqual(pool.config.max_size, 10)
        self.assertEqual(pool.config.ping_threshold, 0.25)
        self.assertEqual(pool.config.max_idle_time, 300.0)
        
        # Test getting a connection
        conn = pool.acquire()
        self.assertIsNotNone(conn)
        
        # Test executing a query
        cursor = conn.cursor()
        cursor.execute("SELECT 1 as test")
        result = cursor.fetchone()
        self.assertEqual(result[0], 1)
        cursor.close()
        
        # Return connection to pool
        conn.close()
        
        # Clean up
        pool.close()

    def test_connection_args(self):
        from mariadb_pool.connection_pool_wrapper import connection_args

        # pool_name and pool configuration keywords are not part of the
        # connection arguments, unset values are ignored and aliases are
        # resolved, so both describe the same connection
        self.assertEqual(connection_args({"user": "u", "password": "p",
                                          "host": "h", "database": "d",
                                          "port": None}),
                         connection_args({"username": "u", "passwd": "p",
                                          "host": "h", "db": "d",
                                          "pool_name": "x", "pool_size": 2,
                                          "pool_reset_connection": False,
                                          "acquire_timeout": 1}))

        # different values or additional arguments don't match
        self.assertNotEqual(connection_args({"host": "h", "password": "p"}),
                            connection_args({"host": "h", "password": "x"}))
        self.assertNotEqual(connection_args({"host": "h"}),
                            connection_args({"host": "h", "port": 3307}))
        self.assertEqual(connection_args({"pool_name": "x"}), {})

    def test_connect_pool_name_deprecated(self):
        default_conf = conf()
        with self.assertWarns(DeprecationWarning):
            conn = mariadb.connect(pool_name="test_deprecated",
                                   pool_size=1, acquire_timeout=1,
                                   **default_conf)
        conn.close()
        with self.assertWarns(DeprecationWarning):
            conn = mariadb.connect(pool_name="test_deprecated",
                                   **default_conf)
        conn.close()
        mariadb._CONNECTION_POOLS["test_deprecated"].close()

    def test_pool_connection_args(self):
        default_conf = conf()
        pool = mariadb.ConnectionPool(pool_name="test_conn_args",
                                      pool_size=1, acquire_timeout=1,
                                      **default_conf)
        try:
            # identical connection arguments: pool keyword arguments are
            # ignored, so they can be passed as well
            conn = mariadb.connect(pool_name="test_conn_args", pool_size=1,
                                   **default_conf)
            conn.close()

            # pool_name alone is not enough, all connection arguments of
            # the pool have to be provided
            self.assertRaises(mariadb.PoolError, mariadb.connect,
                              pool_name="test_conn_args")

            # different value for a connection argument
            other_conf = default_conf.copy()
            other_conf["database"] = "test_conn_args_other_db"
            self.assertRaises(mariadb.PoolError, mariadb.connect,
                              pool_name="test_conn_args", **other_conf)

            # additional connection argument
            self.assertRaises(mariadb.PoolError, mariadb.connect,
                              pool_name="test_conn_args", autocommit=True,
                              **default_conf)

            # missing connection argument
            reduced_conf = default_conf.copy()
            del reduced_conf["host"]
            self.assertRaises(mariadb.PoolError, mariadb.connect,
                              pool_name="test_conn_args", **reduced_conf)
        finally:
            pool.close()

if __name__ == '__main__':
    unittest.main()
