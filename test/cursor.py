#!/usr/bin/env python -O

import mariadb
import datetime
import unittest

class CursorTest(unittest.TestCase):

  def setUp(self):
    self.connection= mariadb.connection(default_file='default.cnf')

  def tearDown(self):
    del self.connection

  def test_date(self):
    cursor= self.connection.cursor()
    cursor.execute("CREATE OR REPLACE TABLE t1(c1 TIMESTAMP(6), c2 TIME(6), c3 DATETIME(6), c4 DATE)")
    t= datetime.datetime(2018,6,20,12,22,31,123456)
    c1= t
    c2= t.time()
    c3= t
    c4= t.date()
    cursor.execute("INSERT INTO t1 VALUES (?,?,?,?)", (c1, c2, c3, c4))

    cursor.execute("SELECT c1,c2,c3,c4 FROM t1")
    row= cursor.fetchone()
    self.assertEqual(row[0],c1)
    self.assertEqual(row[1],c2)
    self.assertEqual(row[2],c3)
    self.assertEqual(row[3],c4)
    cursor.close()

  def test_numbers(self):
    cursor= self.connection.cursor()
    cursor.execute("CREATE OR REPLACE TABLE t1 (a tinyint unsigned, b smallint unsigned, c mediumint unsigned, d int unsigned, e bigint unsigned, f double)")
    c1= 4
    c2= 200
    c3= 167557
    c4= 28688817
    c5= 7330133222578
    c6= 3.1415925

    cursor.execute("insert into t1 values (?,?,?,?,?,?)", (c1,c2,c3,c4,c5,c6))

#    cursor.execute("select * from t1")
#    row= cursor.fetchone()
#    self.assertEqual(row[0],c1)
#    self.assertEqual(row[1],c2)
#    self.assertEqual(row[2],c3)
#    self.assertEqual(row[3],c4)
#    self.assertEqual(row[4],c5)
#    self.assertEqual(row[5],c6)
    del cursor

  def test_string(self):
    cursor= self.connection.cursor()
    cursor.execute("CREATE OR REPLACE TABLE t1 (a char(5), b varchar(100), c tinytext, d mediumtext, e text, f longtext)");

    c1= "12345";
    c2= "The length of this text is < 100 characters"
    c3= "This should also fit into tinytext which has a maximum of 255 characters"
    c4= 'a' * 1000;
    c5= 'b' * 6000;
    c6= 'c' * 67000;

    cursor.execute("INSERT INTO t1 VALUES (?,?,?,?,?,?)", (c1,c2,c3,c4,c5,c6))

    cursor.execute("SELECT * from t1")
    row= cursor.fetchone()
    self.assertEqual(row[0],c1)
    self.assertEqual(row[1],c2)
    self.assertEqual(row[2],c3)
    self.assertEqual(row[3],c4)
    self.assertEqual(row[4],c5)
    self.assertEqual(row[5],c6)
    del cursor

  def test_blob(self):
    cursor= self.connection.cursor()
    cursor.execute("CREATE OR REPLACE TABLE t1 (a tinyblob, b mediumblob, c blob, d longblob)")

    c1= b'a' * 100;
    c2= b'b' * 1000;
    c3= b'c' * 10000;
    c4= b'd' * 100000;

    a= (None, None, None, None)
    cursor.execute("INSERT INTO t1 VALUES (?,?,?,?)", (c1, c2, c3, c4))

    cursor.execute("SELECT * FROM t1")
    row= cursor.fetchone()
    self.assertEqual(row[0],c1)
    self.assertEqual(row[1],c2)
    self.assertEqual(row[2],c3)
    self.assertEqual(row[3],c4)
    del cursor

  def test_fetchmany(self):
    cursor= self.connection.cursor()
    cursor.execute("CREATE OR REPLACE TABLE t1 (id int, name varchar(64), city varchar(64))");
    params= [(1, u"Jack",  u"Boston"),
           (2, u"Martin",  u"Ohio"),
           (3, u"James",  u"Washington"),
           (4, u"Rasmus",  u"Helsinki"),
           (5, u"Andrey",  u"Sofia")]
    cursor.executemany("INSERT INTO t1 VALUES (?,?,?)", params);

    #test Errors
#   # a) if no select was executed
    self.assertRaises(mariadb.Error, cursor.fetchall)
    #b ) if cursor was not executed
    del cursor
    cursor= self.connection.cursor()
    self.assertRaises(mariadb.Error, cursor.fetchall)

    cursor.execute("SELECT id, name, city FROM t1 ORDER BY id")
    self.assertEqual(0, cursor.rowcount())
    row = cursor.fetchall()
    self.assertEqual(row, params)
    self.assertEqual(5, cursor.rowcount())

    cursor.execute("SELECT id, name, city FROM t1 ORDER BY id")
    self.assertEqual(0, cursor.rowcount())
    print("row count 3: ", cursor.rowcount())
    row= cursor.fetchmany()
    print("row count 4: ", cursor.rowcount())
    self.assertEqual(row,[])

    row= cursor.fetchmany(1)
    print("row count: ", cursor.rowcount())
    self.assertEqual(row,[params[0]])

    row= cursor.fetchmany(2)
    self.assertEqual(row,([params[1], params[2]]))

    cursor.arraysize= 1
    row= cursor.fetchmany()
    self.assertEqual(row,[params[3]])

    cursor.arraysize= 2
    row= cursor.fetchmany()
    self.assertEqual(row,[params[4]])
    print("row count: ", cursor.rowcount())
