#!/usr/bin/env python -O

import mysql.connector
import datetime
import unittest

class CursorTest(unittest.TestCase):

  def setUp(self):
    self.connection= mysql.connector.connect(user='root', database='test')

  def tearDown(self):
    self.connection.close()
    del self.connection

  def test_parameter(self):
    cursor= self.connection.cursor()
    cursor.execute("CREATE OR REPLACE TABLE t1(a int auto_increment primary key not null, b int, c int, d varchar(20),e date)")
    cursor.execute("SET @@autocommit=0");
    c = (1,2,3, "bar", datetime.date(2018,11,11))
    list_in= []
    for i in range(1,300000):
      row= (i,i,i,"bar", datetime.date(2019,1,1))
      list_in.append(row)
    cursor.executemany("INSERT INTO t1 VALUES (%s,%s,%s,%s,%s)", list_in)
    print("rows inserted:", len(list_in))
    self.connection.commit()
    cursor.execute("SELECT * FROM t1 order by a")
    list_out= cursor.fetchall()
    print("rows fetched: ", len(list_out))
    self.assertEqual(list_in,list_out)

    cursor.close()

