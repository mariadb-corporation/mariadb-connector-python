#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

import os
import unittest

from test.base_test import create_connection
from test.conf_test import conf


class TestConnection(unittest.TestCase):

    def setUp(self):
        self.connection = create_connection()

    def tearDown(self):
        del self.connection

    def test_connection_default_file(self):
        if os.path.exists("client.cnf"):
            os.remove("client.cnf")
        default_conf = conf()
        f = open("client.cnf", "w+")
        f.write("[client]\n")
        f.write("host=%s\n" % default_conf["host"])
        f.write("port=%i\n" % default_conf["port"])
        f.write("database=%s\n" % default_conf["database"])
        f.close()

        new_conn = create_connection({"user": default_conf["user"], "default_file": "./client.cnf"})
        self.assertEqual(new_conn.database, default_conf["database"])
        os.remove("client.cnf")
        del new_conn

    def test_autocommit(self):
        conn = self.connection
        cursor = conn.cursor()
        self.assertEqual(conn.autocommit, True)
        conn.autocommit = False
        self.assertEqual(conn.autocommit, False)
        conn.reset()

    def test_schema(self):
        default_conf = conf()
        conn = self.connection
        self.assertEqual(conn.database, default_conf["database"])
        cursor = conn.cursor()
        cursor.execute("CREATE OR REPLACE SCHEMA test1")
        cursor.execute("USE test1")
        self.assertEqual(conn.database, "test1")
        conn.database = default_conf["database"]
        self.assertEqual(conn.database, default_conf["database"])


    def test_non_utf8_charset(self):
        try:
            create_connection({"charset": "cp1251"})
            self.fail("must have throw exception")
        except self.connection.ProgrammingError as err:
            self.assertEqual(str(err), "charset 'cp1251' not permitted")
            pass

    def test_default_charset(self):
        cursor = self.connection.cursor()
        cursor.execute("SELECT @@character_set_client as a")
        row = cursor.fetchone()
        self.assertEqual(row[0], "utf8mb4")
        del cursor

    def test_wrong_charset(self):
        try:
            create_connection({"charset": "wrong charset"})
            self.fail("must have throw exception")
        except self.connection.ProgrammingError as err:
            self.assertEqual(str(err), "Unknown charset value 'wrong charset'")
            pass

if __name__ == '__main__':
    unittest.main()
