#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

import unittest

import mariadb
import platform

from test.base_test import create_connection, conf, is_skysql, is_maxscale


@unittest.skipIf(platform.python_implementation() == "PyPy",
                 "skip pooling tests for PyPy")
class TestPooling(unittest.TestCase):

    def setUp(self):
        pass

    #         self.connection = create_connection()
    #         self.connection.autocommit = False

    def tearDown(self):
        pass

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
                                      pool_size=16,
                                      pool_reset_connection=False,
                                      pool_validation_interval=0,
                                      **default_conf)
        self.assertEqual(pool.connection_count, 16)
        pool.close()
        self.assertEqual(pool.connection_count, 0)

    def test_conpy247_1(self):
        default_conf = conf()
        pool = mariadb.ConnectionPool(pool_name="CONPY247_1",
                                      pool_size=1,
                                      pool_reset_connection=False,
                                      pool_validation_interval=0,
                                      **default_conf)

        # service connection
        conn = create_connection()
        cursor = conn.cursor()

        pconn = pool.get_connection()
        old_id = pconn.connection_id
        cursor.execute("KILL %s" % (old_id,))
        pconn.close()

        pconn = pool.get_connection()
        self.assertNotEqual(old_id, pconn.connection_id)

        conn.close()
        pool.close()

    def test_conpy247_2(self):
        default_conf = conf()
        pool = mariadb.ConnectionPool(pool_name="CONPY247_2",
                                      pool_size=1,
                                      pool_reset_connection=True,
                                      pool_validation_interval=0,
                                      **default_conf)

        # service connection
        conn = create_connection()
        cursor = conn.cursor()

        pconn = pool.get_connection()
        old_id = pconn.connection_id
        cursor.execute("KILL %s" % (old_id,))
        pconn.close()

        pconn = pool.get_connection()
        self.assertNotEqual(old_id, pconn.connection_id)

        conn.close()
        pool.close()

    def test_conpy247_3(self):
        default_conf = conf()
        pool = mariadb.ConnectionPool(pool_name="CONPY247_3",
                                      pool_size=10,
                                      pool_reset_connection=True,
                                      pool_validation_interval=0,
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

        for i in range(0, 10):
            pconn = pool.get_connection()
            ids.append(pconn.connection_id)
            cursor.execute("KILL %s" % (pconn.connection_id,))
            pconn.close()

        new_ids = []

        for i in range(0, 10):
            pconn = pool.get_connection()
            new_ids.append(pconn.connection_id)
            self.assertEqual(pconn.connection_id in ids, False)
            cursor = pconn.cursor()
            cursor.callproc("p1")
            cursor.close()
            pconn.close()

        for i in range(0, 10):
            pconn = pool.get_connection()
            self.assertEqual(pconn.connection_id in new_ids, True)
            pconn.close()

        conn.close()
        pool.close()

    def test_conpy245(self):
        # we can't test performance here, but we can check if LRU works.
        # All connections must have been used the same number of times.

        default_conf = conf()
        pool_size = 64
        iterations = 100

        pool = mariadb.ConnectionPool(pool_name="CONPY245",
                                      pool_size=pool_size,
                                      **default_conf)
        for i in range(0, iterations):
            for j in range(0, pool_size):
                conn = pool.get_connection()
                conn.close()

        for i in range(0, pool_size):
            conn = pool.get_connection()
            self.assertEqual(conn._used, iterations + 1)
            conn.close()

        pool.close()

    def test_connection_pool_conf(self):
        pool = mariadb.ConnectionPool(pool_name="test_conf")
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
        self.assertEqual(c, conn)
        pool.close()

    def test_connection_pool_maxconn(self):
        default_conf = conf()
        pool = mariadb.ConnectionPool(pool_name="test_max_size", pool_size=6,
                                      **default_conf)
        connections = []
        for i in range(0, 6):
            connections.append(pool.get_connection())
        self.assertRaises(mariadb.PoolError, lambda:pool.get_connection())

        for c in connections:
            c.close()
        pool.close()

    def test_connection_pool_add(self):
        default_conf = conf()
        pool = mariadb.ConnectionPool(pool_name="test_connection_pool_add")
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
        pool = mariadb.ConnectionPool(pool_name="test_conpy69")
        try:
            pool.set_config(**default_conf)
        except mariadb.Error:
            pool.close()
            raise

        try:
            for i in range(1, 6):
                pool.add_connection()
            conn = mariadb.connect(pool_name="test_conpy69")
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
        pool = mariadb.ConnectionPool(pool_name="test_use", **default_conf)
        conn = mariadb.connect(pool_name="test_use")
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        row = cursor.fetchone()
        self.assertEqual(row[0], 1)
        del cursor
        pool.close()

    def test_create_pool_from_conn(self):
        default_conf = conf()
        key = "t1"
        conn = mariadb.connect(pool_name=key, **default_conf)
        cursor = conn.cursor()
        del mariadb._CONNECTION_POOLS["t1"]
        self.assertEqual(mariadb._CONNECTION_POOLS, {})
        try:
            cursor.execute("SELECT 1")
        except mariadb.ProgrammingError:
            pass

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
        self.assertEqual(p.max_size, 64)
        mariadb._CONNECTION_POOLS["getter_test"].close()

    def test_pool_connection_reset(self):
        default_conf = conf()
        conn = mariadb.connect(pool_name="reset_test",
                               pool_size=1, **default_conf)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        conn = mariadb.connect(pool_name="reset_test")
        cursor = conn.cursor()
        cursor.execute("SELECT 2")
        row = cursor.fetchone()
        self.assertEqual(row[0], 2)
        mariadb._CONNECTION_POOLS["reset_test"].close()

    def test_conpy40(self):
        default_conf = conf()
        pool = mariadb.ConnectionPool(pool_name='test_conpy40')

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
        pool = mariadb.ConnectionPool(pool_name="test_pool_add")
        try:
            mariadb.ConnectionPool(pool_name="test_pool_add")
        except mariadb.ProgrammingError:
            pass
        pool.close()
        self.assertEqual(mariadb._CONNECTION_POOLS, {})

    def test_conpy256(self):
        size = 10
        connections = []
        default_conf = conf()
        pool = mariadb.ConnectionPool(pool_name="test_conpy256",
                               pool_size=size, **default_conf)
        for i in range(size):
            c= pool.get_connection()
            self.assertNotEqual(c in connections, True)
            connections.append(c)

        pool.close()

if __name__ == '__main__':
    unittest.main()
