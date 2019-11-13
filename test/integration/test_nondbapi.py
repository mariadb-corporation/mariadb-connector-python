#!/usr/bin/env python -O

# -*- coding: utf-8 -*-

import unittest

import mariadb

from test.base_test import create_connection
from test.conf_test import conf


class CursorTest(unittest.TestCase):

    def setUp(self):
        self.connection = create_connection()

    def tearDown(self):
        del self.connection

    def test_ping(self):
        new_conn = create_connection()
        id = new_conn.connection_id;
        self.connection.kill(id)
        try:
            new_conn.ping()
        except mariadb.DatabaseError:
            pass
        del new_conn
        new_conn = create_connection()
        new_conn.auto_reconnect = True
        id = new_conn.connection_id;
        self.connection.kill(id)
        new_conn.ping()
        new_id = new_conn.connection_id
        self.assertTrue(id != new_id)
        del new_conn

    def test_change_user(self):
        cursor = self.connection.cursor()
        cursor.execute("create or replace user foo@localhost")
        cursor.execute("GRANT ALL on testp.* TO foo@localhost")
        new_conn = create_connection()
        default_conf = conf()
        new_conn.change_user("foo", "", default_conf["database"])
        self.assertEqual("foo", new_conn.user)
        del new_conn
        del cursor

    def test_reconnect(self):
        new_conn = create_connection()
        conn1_id = new_conn.connection_id
        self.connection.kill(conn1_id)
        new_conn.reconnect()
        conn2_id = new_conn.connection_id
        self.assertFalse(conn1_id == conn2_id)
        del new_conn

    def test_reset(self):
        cursor = self.connection.cursor()
        cursor.execute("SELECT 1 UNION SELECT 2")
        try:
            self.connection.ping()
        except mariadb.DatabaseError:
            pass

        self.connection.reset()
        self.connection.ping()
        del cursor

    def test_warnings(self):
        conn = self.connection
        cursor = conn.cursor()

        cursor.execute("SET session sql_mode=''")
        cursor.execute("CREATE TEMPORARY TABLE test_warnings (a tinyint)")
        cursor.execute("INSERT INTO test_warnings VALUES (300)")

        self.assertEqual(conn.warnings, 1)
        self.assertEqual(conn.warnings, cursor.warnings)
        del cursor

    def test_server_infos(self):
        self.assertTrue(self.connection.server_info)
        self.assertTrue(self.connection.server_version > 0);

    def test_escape(self):
        cursor = self.connection.cursor()
        cursor.execute("CREATE TEMPORARY TABLE test_escape (a varchar(100))")
        str = 'This is a \ and a "'
        cmd = "INSERT INTO test_escape VALUES('%s')" % str

        try:
            cursor.execute(cmd)
        except mariadb.DatabaseError:
            pass

        str = self.connection.escape_string(str)
        cmd = "INSERT INTO test_escape VALUES('%s')" % str
        cursor.execute(cmd)
        del cursor


if __name__ == '__main__':
    unittest.main()
