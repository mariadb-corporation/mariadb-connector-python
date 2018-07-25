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

    cursor.execute("select * from t1")
    row= cursor.fetchone()
    self.assertEqual(row[0],c1)
    self.assertEqual(row[1],c2)
    self.assertEqual(row[2],c3)
    self.assertEqual(row[3],c4)
    self.assertEqual(row[4],c5)
    self.assertEqual(row[5],c6)
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
    # a) if no select was executed
    self.assertRaises(mariadb.Error, cursor.fetchall)
    #b ) if cursor was not executed
    del cursor
    cursor= self.connection.cursor()
    self.assertRaises(mariadb.Error, cursor.fetchall)

    cursor.execute("SELECT id, name, city FROM t1 ORDER BY id")
    self.assertEqual(0, cursor.rowcount)
    row = cursor.fetchall()
    self.assertEqual(row, params)
    self.assertEqual(5, cursor.rowcount)

    cursor.execute("SELECT id, name, city FROM t1 ORDER BY id")
    self.assertEqual(0, cursor.rowcount)

    row= cursor.fetchmany(1)
    self.assertEqual(row,[params[0]])
    self.assertEqual(1, cursor.rowcount)

    row= cursor.fetchmany(2)
    self.assertEqual(row,([params[1], params[2]]))
    self.assertEqual(3, cursor.rowcount)

    cursor.arraysize= 1
    row= cursor.fetchmany()
    self.assertEqual(row,[params[3]])
    self.assertEqual(4, cursor.rowcount)

    cursor.arraysize= 2
    row= cursor.fetchmany()
    self.assertEqual(row,[params[4]])
    self.assertEqual(5, cursor.rowcount)
    del cursor

  def test1_multi_result(self):
    cursor= self.connection.cursor()
    sql= """
           CREATE OR REPLACE PROCEDURE p1()
           BEGIN
             SELECT 1 FROM DUAL;
             SELECT 2 FROM DUAL;
           END
         """
    cursor.execute(sql)
    cursor.execute("call p1()")
    row= cursor.fetchone()
    self.assertEqual(row[0], 1)
    cursor.nextset()
    row= cursor.fetchone()
    self.assertEqual(row[0], 2)
    del cursor

  def test_buffered(self):
    cursor= self.connection.cursor()
    cursor.execute("SELECT 1 UNION SELECT 2 UNION SELECT 3", buffered=True)
    self.assertEqual(cursor.rowcount, 3)
    cursor.scroll(1)
    row= cursor.fetchone()
    self.assertEqual(row[0],2) 
    del cursor

  def test_xfield_types(self):
    cursor= self.connection.cursor()
    fieldinfo= mariadb.fieldinfo()
    cursor.execute("CREATE OR REPLACE TABLE t1 (a tinyint not null auto_increment primary key, b smallint, c int, d bigint, e float, f decimal, g double, h char(10), i varchar(255), j blob, index(b))");
    info= cursor.description
    self.assertEqual(info, None)
    cursor.execute("SELECT * FROM t1")
    info= cursor.description
    self.assertEqual(fieldinfo.type(info[0]), "TINY")
    self.assertEqual(fieldinfo.type(info[1]), "SHORT")
    self.assertEqual(fieldinfo.type(info[2]), "LONG")
    self.assertEqual(fieldinfo.type(info[3]), "LONGLONG")
    self.assertEqual(fieldinfo.type(info[4]), "FLOAT")
    self.assertEqual(fieldinfo.type(info[5]), "NEWDECIMAL")
    self.assertEqual(fieldinfo.type(info[6]), "DOUBLE")
    self.assertEqual(fieldinfo.type(info[7]), "STRING")
    self.assertEqual(fieldinfo.type(info[8]), "VAR_STRING")
    self.assertEqual(fieldinfo.type(info[9]), "BLOB")
    self.assertEqual(fieldinfo.flag(info[0]), "NOT_NULL | PRIMARY_KEY | AUTO_INCREMENT | NUMERIC")
    self.assertEqual(fieldinfo.flag(info[1]), "PART_KEY | NUMERIC")
    self.assertEqual(fieldinfo.flag(info[9]), "BLOB | BINARY")
    del cursor

  def test_named_tuple(self):
    cursor= self.connection.cursor(named_tuple=1)
    cursor.execute("CREATE OR REPLACE TABLE t1 (id int, name varchar(64), city varchar(64))");
    params= [(1, u"Jack",  u"Boston"),
           (2, u"Martin",  u"Ohio"),
           (3, u"James",  u"Washington"),
           (4, u"Rasmus",  u"Helsinki"),
           (5, u"Andrey",  u"Sofia")]
    cursor.executemany("INSERT INTO t1 VALUES (?,?,?)", params);
    cursor.execute("SELECT * FROM t1 ORDER BY id")
    row= cursor.fetchone()

    self.assertEqual(cursor.statement, "SELECT * FROM t1 ORDER BY id")
    self.assertEqual(row.id, 1)
    self.assertEqual(row.name, "Jack")
    self.assertEqual(row.city, "Boston")
    del cursor

  def test_laststatement(self):
    cursor= self.connection.cursor(named_tuple=1)
    cursor.execute("CREATE OR REPLACE TABLE t1 (id int, name varchar(64), city varchar(64))");
    self.assertEqual(cursor.statement, "CREATE OR REPLACE TABLE t1 (id int, name varchar(64), city varchar(64))")

    params= [(1, u"Jack",  u"Boston"),
           (2, u"Martin",  u"Ohio"),
           (3, u"James",  u"Washington"),
           (4, u"Rasmus",  u"Helsinki"),
           (5, u"Andrey",  u"Sofia")]
    cursor.executemany("INSERT INTO t1 VALUES (?,?,?)", params);
    cursor.execute("SELECT * FROM t1 ORDER BY id")
    self.assertEqual(cursor.statement, "SELECT * FROM t1 ORDER BY id")
    del cursor

  def test_multi_cursor(self):
    cursor= self.connection.cursor()
    cursor1= self.connection.cursor(cursor_type=1)
    cursor2= self.connection.cursor(cursor_type=1)

    cursor.execute("CREATE OR REPLACE TABLE t1 (a int)")
    cursor.execute("INSERT INTO t1 VALUES (1),(2),(3),(4),(5),(6),(7),(8)")
    del cursor

    cursor1.execute("SELECT a FROM t1 ORDER BY a")
    cursor2.execute("SELECT a FROM t1 ORDER BY a DESC")

    for i in range (0,8):
      self.assertEqual(cursor1.rownumber, i)
      row1= cursor1.fetchone()
      row2= cursor2.fetchone()
      self.assertEqual(cursor1.rownumber, cursor2.rownumber)
      self.assertEqual(row1[0]+row2[0], 9)

    del cursor1
    del cursor2

  def test_connection_attr(self):
    cursor= self.connection.cursor()
    self.assertEqual(cursor.connection, self.connection)
    del cursor

  def test_dbapi_type(self):
    cursor= self.connection.cursor()
    cursor.execute("CREATE OR REPLACE TABLE t1 (a int, b varchar(20), c blob, d datetime, e decimal)")
    cursor.execute("INSERT INTO t1 VALUES (1, 'foo', 'blabla', now(), 10.2)");
    cursor.execute("SELECT * FROM t1 ORDER BY a")
    expected_typecodes= [
      mariadb.NUMBER,
      mariadb.STRING,
      mariadb.BINARY,
      mariadb.DATETIME,
      mariadb.NUMBER
    ]
    row= cursor.fetchone()
    typecodes= [row[1] for row in cursor.description]
    self.assertEqual(expected_typecodes, typecodes)
    del cursor

  def test_tuple(self):
    cursor= self.connection.cursor()
    cursor.execute("CREATE OR REPLACE TABLE dyncol1 (a blob)");
    tpl=(1,2,3)
    cursor.execute("INSERT INTO dyncol1 VALUES (?)", tpl);
    del cursor

  def test_indicator(self):
    cursor= self.connection.cursor()
    cursor.execute("CREATE OR REPLACE TABLE ind1 (a int, b int default 2,c int)");
    vals= (mariadb.indicator_null, mariadb.indicator_default, 3)
    cursor.executemany("INSERT INTO ind1 VALUES (?,?,?)", [vals])
    cursor.execute("SELECT a, b, c FROM ind1")
    row= cursor.fetchone()
    self.assertEqual(row[0], None)
    self.assertEqual(row[1], 2)
    self.assertEqual(row[2], 3)

  def test_tuple(self):
    cursor= self.connection.cursor()
    cursor.execute("CREATE OR REPLACE TABLE dyncol1 (a blob)");
    t= datetime.datetime(2018,6,20,12,22,31,123456)
    val=([1,t,3,(1,2,3)],)
    cursor.execute("INSERT INTO dyncol1 VALUES (?)", val);
    cursor.execute("SELECT a FROM dyncol1")
    row= cursor.fetchone()
    self.assertEqual(row,val);
    del cursor

  def test_set(self):
    cursor= self.connection.cursor()
    cursor.execute("CREATE OR REPLACE TABLE dyncol1 (a blob)");
    t= datetime.datetime(2018,6,20,12,22,31,123456)
    a= collections.OrderedDict([('apple', 4), ('banana', 3), ('orange', 2), ('pear', 1),  ('4',3), (4,4)])
    val=([1,t,3,(1,2,3), {1,2,3},a],)
    cursor.execute("INSERT INTO dyncol1 VALUES (?)", val);
    cursor.execute("SELECT a FROM dyncol1")
    row= cursor.fetchone()
    self.assertEqual(row,val);
    del cursor

  def test_reset(self):
    cursor= self.connection.cursor()
    cursor.execute("SELECT 1 UNION SELECT 2", buffered=False)
    cursor.execute("SELECT 1 UNION SELECT 2")
    del cursor

  def test_fake_pickle(self):
    cursor= self.connection.cursor()
    cursor.execute("create or replace table t1 (a blob)")
    k=bytes([0x80,0x03,0x00,0x2E])
    cursor.execute("insert into t1 values (?)", (k,))
    cursor.execute("select * from t1");
    row= cursor.fetchone()
    self.assertEqual(row[0],k)
    del cursor

  def test_no_result(self):
    cursor= self.connection.cursor()
    cursor.execute("set @a:=1")
    try:
      row= cursor.fetchone()
    except mariadb.ProgrammingError:
      pass
    del cursor

  def test_collate(self):
    cursor= self.connection.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS `tt` (`test` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci")
    cursor.execute("SET NAMES utf8mb4")
    cursor.execute("SELECT * FROM `tt` WHERE `test` LIKE 'jj' COLLATE utf8mb4_unicode_ci")
    del cursor

  def test_conpy_8(self):
    cursor=self.connection.cursor()
    sql= """
           CREATE OR REPLACE PROCEDURE p1()
           BEGIN
             SELECT 1 FROM DUAL UNION SELECT 0 FROM DUAL;
             SELECT 2 FROM DUAL;
           END
         """
    cursor.execute(sql)
    cursor.execute("call p1()")

    cursor.nextset()
    row= cursor.fetchone()
    self.assertEqual(row[0],2);
    del cursor

  def test_conpy_7(self):
    cursor=self.connection.cursor()
    stmt= "SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4"
    cursor.execute(stmt, buffered=True)
    cursor.scroll(2, mode='relative')
    row= cursor.fetchone()
    self.assertEqual(row[0],3)
    cursor.scroll(-2, mode='relative')
    row= cursor.fetchone()
    print(row)
    del cursor

  def test_compy_9(self):
    cursor=self.connection.cursor(buffered=True)
    cursor.execute("SELECT 'utf8mb4', 123.5678")
    print(cursor.description) 
