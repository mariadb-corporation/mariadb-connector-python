#!/usr/bin/env python -O

import mariadb
import datetime
import unittest

class CursorTest(unittest.TestCase):

  def setUp(self):
    self.connection= mariadb.connection(default_file='default.cnf')

  def tearDown(self):
    self.connection.close()
    del self.connection

  def test_insert_parameter(self):
    cursor= self.connection.cursor()
    cursor.execute("CREATE OR REPLACE TABLE t1(a int not null auto_increment primary key, b int, c int, d varchar(20),e date)")
#    cursor.execute("set @@autocommit=0");
    list_in= []
    for i in range(1, 300001):
      row= (i,i,i,"bar", datetime.date(2019,1,1))
      list_in.append(row)
    cursor.executemany("INSERT INTO t1 VALUES (?,?,?,?,?)", list_in)
    self.assertEqual(len(list_in), cursor.rowcount)
    self.connection.commit()
    cursor.execute("SELECT * FROM t1 order by a")
    list_out= cursor.fetchall()
    self.assertEqual(len(list_in), cursor.rowcount);
    self.assertEqual(list_in,list_out)
    cursor.close()

  def test_update_parameter(self):
    cursor= self.connection.cursor()
    cursor.execute("CREATE OR REPLACE TABLE t1(a int not null auto_increment primary key, b int, c int, d varchar(20),e date)")
    cursor.execute("set @@autocommit=0");
    list_in= []
    for i in range(1, 300001):
      row= (i,i,i,"bar", datetime.date(2019,1,1))
      list_in.append(row)
    cursor.executemany("INSERT INTO t1 VALUES (?,?,?,?,?)", list_in)
    self.assertEqual(len(list_in), cursor.rowcount)
    self.connection.commit()
    cursor.close()
    list_update= [];

    cursor= self.connection.cursor()
    cursor.execute("set @@autocommit=0");
    for i in range(1, 300001):
      row= (i+1, i);
      list_update.append(row);
    
    cursor.executemany("UPDATE t1 SET b=? WHERE a=?", list_update);
    self.assertEqual(cursor.rowcount, 300000)
    self.connection.commit();
    cursor.close()

  def test_delete_parameter(self):
    cursor= self.connection.cursor()
    cursor.execute("CREATE OR REPLACE TABLE t1(a int not null auto_increment primary key, b int, c int, d varchar(20),e date)")
    cursor.execute("set @@autocommit=0");
    list_in= []
    for i in range(1, 300001):
      row= (i,i,i,"bar", datetime.date(2019,1,1))
      list_in.append(row)
    cursor.executemany("INSERT INTO t1 VALUES (?,?,?,?,?)", list_in)
    self.assertEqual(len(list_in), cursor.rowcount)
    self.connection.commit()
    cursor.close()
    list_delete= [];

    cursor= self.connection.cursor()
    cursor.execute("set @@autocommit=0");
    for i in range(1, 300001):
      list_delete.append((i,));
    
    cursor.executemany("DELETE FROM t1 WHERE a=?", list_delete);
    self.assertEqual(cursor.rowcount, 300000)
    self.connection.commit();
    cursor.close()
