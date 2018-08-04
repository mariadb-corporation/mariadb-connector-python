#!/usr/bin/env python -O

import mariadb
import datetime
import unittest
import collections

class CursorTest(unittest.TestCase):

  def setUp(self):
    self.connection= mariadb.connection(default_file='default.cnf')

  def tearDown(self):
    del self.connection

  def test_autcommit(self):
    conn= self.connection
    cursor=conn.cursor()
    self.assertEqual(conn.autocommit, True)
    conn.autocommit= False
    self.assertEqual(conn.autocommit, False)
    conn.reset()

  def test_schema(self):
    conn= self.connection
    self.assertEqual(conn.database, "test")
    cursor= conn.cursor()
    cursor.execute("CREATE OR REPLACE SCHEMA test1")
    cursor.execute("USE test1")
    self.assertEqual(conn.database, "test1")
    conn.database= "test"
    self.assertEqual(conn.database, "test")
