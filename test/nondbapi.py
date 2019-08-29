import mariadb
import datetime
import unittest
import collections
import time

class CursorTest(unittest.TestCase):

  def setUp(self):
    self.connection= mariadb.connection(default_file='default.cnf')

  def tearDown(self):
    del self.connection

  def test_ping(self):
    new_conn= mariadb.connection(default_file='default.cnf')
    id= new_conn.connection_id;
    self.connection.kill(id)
    try:
      new_conn.ping()
    except mariadb.DatabaseError:
      pass
    del new_conn
    new_conn= mariadb.connection(default_file='default.cnf')
    new_conn.auto_reconnect= True
    id= new_conn.connection_id;
    self.connection.kill(id)
    new_conn.ping()
    new_id= new_conn.connection_id
    self.assertTrue(id != new_id)
    del new_conn

  def test_change_user(self):
    cursor= self.connection.cursor()
    cursor.execute("create or replace user foo@localhost")
    cursor.execute("GRANT ALL on test.* TO 'foo'@'localhost'")
    new_conn= mariadb.connection(default_file='default.cnf')
    new_conn.change_user("foo", "", "test")
    self.assertEqual("foo", new_conn.user)
    del new_conn
    cursor.execute("drop user foo@localhost")
    del cursor

  def test_db(self):
    cursor= self.connection.cursor()
    cursor.execute("CREATE OR REPLACE schema test1")
    self.assertEqual(self.connection.database, "test")
    self.connection.database= "test1"
    self.assertEqual(self.connection.database, "test1")
    self.connection.database= "test"
    self.assertEqual(self.connection.database, "test")
    cursor.execute("USE test1")
    self.assertEqual(self.connection.database, "test1")
    cursor.execute("USE test")
    cursor.execute("DROP SCHEMA test1")
    del cursor

  def test_reconnect(self):
    new_conn= mariadb.connection(default_file='default.cnf')
    conn1_id= new_conn.connection_id
    self.connection.kill(conn1_id)
    new_conn.reconnect()
    conn2_id= new_conn.connection_id
    self.assertFalse(conn1_id == conn2_id)
    del new_conn

  def test_reset(self):
    cursor= self.connection.cursor()
    cursor.execute("SELECT 1 UNION SELECT 2")
    try:
      self.connection.ping()
    except mariadb.DatabaseError:
      pass

    self.connection.reset()
    self.connection.ping()
    del cursor

  def test_warnings(self):
    conn= self.connection
    cursor= conn.cursor()

    cursor.execute("SET session sql_mode=''")
    cursor.execute("CREATE OR REPLACE TABLE t1 (a tinyint)")
    cursor.execute("INSERT INTO t1 VALUES (300)")

    self.assertEqual(conn.warnings,1)
    self.assertEqual(conn.warnings, cursor.warnings)
    del cursor

  def test_server_infos(self):
    self.assertTrue(self.connection.server_info)
    self.assertTrue(self.connection.server_version > 0);

  def test_escape(self):
    cursor= self.connection.cursor()
    cursor.execute("CREATE OR REPLACE TABLE t1 (a varchar(100))")
    str= 'This is a \ and a "'
    cmd= "INSERT INTO t1 VALUES('%s')" % str

    try:
      cursor.execute(cmd)
    except mariadb.DatabaseError:
      pass

    str= self.connection.escape_string(str)
    cmd= "INSERT INTO t1 VALUES('%s')" % str
    cursor.execute(cmd)
    del cursor

