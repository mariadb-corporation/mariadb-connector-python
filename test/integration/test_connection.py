#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

import os
import unittest

import mariadb

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

        new_conn = mariadb.connect(default_file="./client.cnf")
        self.assertEqual(new_conn.database, default_conf["database"])
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

    def test_ed25519(self):
        if os.environ.get("MAXSCALE_VERSION"):
            self.skipTest("MAXSCALE doesn't support ed25519 for now")
        if self.connection.server_version < 100122:
            self.skipTest("ed25519 now supported")

        conn = self.connection
        cursor = conn.cursor()
        cursor.execute("INSTALL SONAME 'auth_ed25519'")
        cursor.execute("DROP USER IF EXISTS verificationEd25519AuthPlugin")
        if self.connection.server_version < 100400:
            cursor.execute("CREATE USER verificationEd25519AuthPlugin@'%' IDENTIFIED VIA ed25519 "
                           "USING '6aW9C7ENlasUfymtfMvMZZtnkCVlcb1ssxOLJ0kj/AA'")
        else:
            cursor.execute("CREATE USER verificationEd25519AuthPlugin@'%' IDENTIFIED VIA ed25519 "
                           "USING PASSWORD('MySup8%rPassw@ord')")
        cursor.execute("GRANT ALL on *.* to verificationEd25519AuthPlugin@'%'")
        conn2 = create_connection({"user": "verificationEd25519AuthPlugin", "password":
            "MySup8%rPassw@ord"})
        cursor.execute("DROP USER IF EXISTS verificationEd25519AuthPlugin")
        del cursor, conn2

if __name__ == '__main__':
    unittest.main()
