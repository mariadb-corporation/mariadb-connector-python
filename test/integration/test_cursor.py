#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

import collections
import datetime
import unittest
import os
from decimal import Decimal

import mariadb

from test.base_test import create_connection


class TestCursor(unittest.TestCase):

    def setUp(self):
        self.connection = create_connection()
        self.connection.autocommit = False

    def tearDown(self):
        del self.connection

    def test_multiple_close(self):
        cursor = self.connection.cursor()
        cursor.close()
        del cursor

    def test_date(self):
        if (self.connection.server_version < 50500) or (
                ("mariadb" not in self.connection.server_info.lower()) and self.connection.server_version < 50600):
            self.skipTest("microsecond not supported")

        cursor = self.connection.cursor()
        cursor.execute(
            "CREATE TEMPORARY TABLE test_date(c1 TIMESTAMP(6), c2 TIME(6), c3 DATETIME(6), c4 DATE)")
        t = datetime.datetime(2018, 6, 20, 12, 22, 31, 123456)
        c1 = t
        c2 = t.time()
        c3 = t
        c4 = t.date()
        cursor.execute("INSERT INTO test_date VALUES (?,?,?,?)", (c1, c2, c3, c4))

        cursor.execute("SELECT c1,c2,c3,c4 FROM test_date")
        row = cursor.fetchone()
        self.assertEqual(row[0], c1)
        self.assertEqual(row[1], c2)
        self.assertEqual(row[2], c3)
        self.assertEqual(row[3], c4)
        cursor.close()

    def test_numbers(self):
        cursor = self.connection.cursor()
        cursor.execute(
            "CREATE TEMPORARY TABLE test_numbers (a tinyint unsigned, b smallint unsigned, c mediumint "
            "unsigned, d int unsigned, e bigint unsigned, f double)")
        c1 = 4
        c2 = 200
        c3 = 167557
        c4 = 28688817
        c5 = 7330133222578
        c6 = 3.1415925

        cursor.execute("insert into test_numbers values (?,?,?,?,?,?)", (c1, c2, c3, c4, c5, c6))

        cursor.execute("select * from test_numbers")
        row = cursor.fetchone()
        self.assertEqual(row[0], c1)
        self.assertEqual(row[1], c2)
        self.assertEqual(row[2], c3)
        self.assertEqual(row[3], c4)
        self.assertEqual(row[4], c5)
        self.assertEqual(row[5], c6)
        del cursor

    def test_string(self):
        cursor = self.connection.cursor()
        cursor.execute(
            "CREATE TEMPORARY TABLE test_string (a char(5), b varchar(100), c tinytext, "
            "d mediumtext, e text, f longtext)");

        c1 = "12345";
        c2 = "The length of this text is < 100 characters"
        c3 = "This should also fit into tinytext which has a maximum of 255 characters"
        c4 = 'a' * 1000;
        c5 = 'b' * 6000;
        c6 = 'c' * 67000;

        cursor.execute("INSERT INTO test_string VALUES (?,?,?,?,?,?)", (c1, c2, c3, c4, c5, c6))

        cursor.execute("SELECT * from test_string")
        row = cursor.fetchone()
        self.assertEqual(row[0], c1)
        self.assertEqual(row[1], c2)
        self.assertEqual(row[2], c3)
        self.assertEqual(row[3], c4)
        self.assertEqual(row[4], c5)
        self.assertEqual(row[5], c6)
        del cursor

    def test_blob(self):
        cursor = self.connection.cursor()
        cursor.execute("CREATE TEMPORARY TABLE test_blob (a tinyblob, b mediumblob, c blob, "
                       "d longblob)")

        c1 = b'a' * 100;
        c2 = b'b' * 1000;
        c3 = b'c' * 10000;
        c4 = b'd' * 100000;

        a = (None, None, None, None)
        cursor.execute("INSERT INTO test_blob VALUES (?,?,?,?)", (c1, c2, c3, c4))

        cursor.execute("SELECT * FROM test_blob")
        row = cursor.fetchone()
        self.assertEqual(row[0], c1)
        self.assertEqual(row[1], c2)
        self.assertEqual(row[2], c3)
        self.assertEqual(row[3], c4)
        del cursor

    def test_fetchmany(self):
        if os.environ.get("MAXSCALE_VERSION"):
            self.skipTest("MAXSCALE doesn't support BULK yet")
        cursor = self.connection.cursor()
        cursor.execute("CREATE TEMPORARY TABLE test_fetchmany (id int, name varchar(64), "
                       "city varchar(64))");
        params = [(1, u"Jack", u"Boston"),
                  (2, u"Martin", u"Ohio"),
                  (3, u"James", u"Washington"),
                  (4, u"Rasmus", u"Helsinki"),
                  (5, u"Andrey", u"Sofia")]
        cursor.executemany("INSERT INTO test_fetchmany VALUES (?,?,?)", params);

        # test Errors
        # a) if no select was executed
        self.assertRaises(mariadb.Error, cursor.fetchall)
        # b ) if cursor was not executed
        del cursor
        cursor = self.connection.cursor()
        self.assertRaises(mariadb.Error, cursor.fetchall)

        cursor.execute("SELECT id, name, city FROM test_fetchmany ORDER BY id")
        self.assertEqual(0, cursor.rowcount)
        row = cursor.fetchall()
        self.assertEqual(row, params)
        self.assertEqual(5, cursor.rowcount)

        cursor.execute("SELECT id, name, city FROM test_fetchmany ORDER BY id")
        self.assertEqual(0, cursor.rowcount)

        row = cursor.fetchmany(1)
        self.assertEqual(row, [params[0]])
        self.assertEqual(1, cursor.rowcount)

        row = cursor.fetchmany(2)
        self.assertEqual(row, ([params[1], params[2]]))
        self.assertEqual(3, cursor.rowcount)

        cursor.arraysize = 1
        row = cursor.fetchmany()
        self.assertEqual(row, [params[3]])
        self.assertEqual(4, cursor.rowcount)

        cursor.arraysize = 2
        row = cursor.fetchmany()
        self.assertEqual(row, [params[4]])
        self.assertEqual(5, cursor.rowcount)
        del cursor

    def test1_multi_result(self):
        if self.connection.server_version < 100103:
            self.skipTest("CREATE OR REPLACE PROCEDURE not supported")

        cursor = self.connection.cursor()
        sql = """
           CREATE OR REPLACE PROCEDURE p1()
           BEGIN
             SELECT 1 FROM DUAL;
             SELECT 2 FROM DUAL;
           END
         """
        cursor.execute(sql)
        cursor.execute("call p1()")
        row = cursor.fetchone()
        self.assertEqual(row[0], 1)
        cursor.nextset()
        row = cursor.fetchone()
        self.assertEqual(row[0], 2)
        del cursor

    def test_buffered(self):
        cursor = self.connection.cursor(buffered=True)
        cursor.execute("SELECT 1 UNION SELECT 2 UNION SELECT 3")
        self.assertEqual(cursor.rowcount, 3)
        cursor.scroll(1)
        row = cursor.fetchone()
        self.assertEqual(row[0], 2)
        del cursor

    def test_xfield_types(self):
        cursor = self.connection.cursor()
        fieldinfo = mariadb.fieldinfo()
        cursor.execute(
            "CREATE TEMPORARY TABLE test_xfield_types (a tinyint not null auto_increment primary "
            "key, b smallint, c int, d bigint, e float, f decimal, g double, h char(10), i varchar(255), j blob, index(b))");
        info = cursor.description
        self.assertEqual(info, None)
        cursor.execute("SELECT * FROM test_xfield_types")
        info = cursor.description
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
        self.assertEqual(fieldinfo.flag(info[0]),
                         "NOT_NULL | PRIMARY_KEY | AUTO_INCREMENT | NUMERIC")
        self.assertEqual(fieldinfo.flag(info[1]), "PART_KEY | NUMERIC")
        self.assertEqual(fieldinfo.flag(info[9]), "BLOB | BINARY")
        del cursor

    def test_bulk_delete(self):
        if os.environ.get("MAXSCALE_VERSION"):
            self.skipTest("MAXSCALE doesn't support BULK yet")
        cursor = self.connection.cursor()
        cursor.execute(
            "CREATE TEMPORARY TABLE bulk_delete (id int, name varchar(64), city varchar(64))");
        params = [(1, u"Jack", u"Boston"),
                  (2, u"Martin", u"Ohio"),
                  (3, u"James", u"Washington"),
                  (4, u"Rasmus", u"Helsinki"),
                  (5, u"Andrey", u"Sofia")]
        cursor.executemany("INSERT INTO bulk_delete VALUES (?,?,?)", params)
        self.assertEqual(cursor.rowcount, 5)
        params = [(1,), (2,)]
        cursor.executemany("DELETE FROM bulk_delete WHERE id=?", params)
        self.assertEqual(cursor.rowcount, 2)
        del cursor

    def test_pyformat(self):
        if os.environ.get("MAXSCALE_VERSION"):
            self.skipTest("MAXSCALE doesn't support BULK yet")

        cursor = self.connection.cursor()
        cursor.execute(
            "CREATE TEMPORARY TABLE pyformat (id int, name varchar(64), city varchar(64))");
        params = [{"id": 1, "name": u"Jack", "city": u"Boston"},
                  {"id": 2, "name": u"Martin", "city": u"Ohio"},
                  {"id": 3, "name": u"James", "city": u"Washington"},
                  {"id": 4, "name": u"Rasmus", "city": u"Helsinki"},
                  {"id": 5, "name": u"Andrey", "city": u"Sofia"}]
        cursor.executemany("INSERT INTO pyformat VALUES (%(id)s,%(name)s,%(city)s)", params)
        self.assertEqual(cursor.rowcount, 5)
        cursor.execute("commit")
        cursor.execute("SELECT name FROM pyformat WHERE id=5")
        row = cursor.fetchone()
        self.assertEqual(row[0], "Andrey")

    def test_format(self):
        if os.environ.get("MAXSCALE_VERSION"):
            self.skipTest("MAXSCALE doesn't support BULK yet")

        cursor = self.connection.cursor()
        cursor.execute(
            "CREATE TEMPORARY TABLE pyformat (id int, name varchar(64), city varchar(64))");
        params = [(1, u"Jack", u"Boston"),
                  (2, u"Martin", u"Ohio"),
                  (3, u"James", u"Washington"),
                  (4, u"Rasmus", u"Helsinki"),
                  (5, u"Andrey", u"Sofia")]
        cursor.executemany("INSERT INTO pyformat VALUES (%s,%s,%s)", params)
        self.assertEqual(cursor.rowcount, 5)
        cursor.execute("commit")
        cursor.execute("SELECT name FROM pyformat WHERE id=5")
        row = cursor.fetchone()
        self.assertEqual(row[0], "Andrey")

    def test_named_tuple(self):
        if os.environ.get("MAXSCALE_VERSION"):
            self.skipTest("MAXSCALE doesn't support BULK yet")

        cursor = self.connection.cursor(named_tuple=1)
        cursor.execute(
            "CREATE TEMPORARY TABLE test_named_tuple (id int, name varchar(64), city varchar(64))");
        params = [(1, u"Jack", u"Boston"),
                  (2, u"Martin", u"Ohio"),
                  (3, u"James", u"Washington"),
                  (4, u"Rasmus", u"Helsinki"),
                  (5, u"Andrey", u"Sofia")]
        cursor.executemany("INSERT INTO test_named_tuple VALUES (?,?,?)", params);
        cursor.execute("SELECT * FROM test_named_tuple ORDER BY id")
        row = cursor.fetchone()

        self.assertEqual(cursor.statement, "SELECT * FROM test_named_tuple ORDER BY id")
        self.assertEqual(row.id, 1)
        self.assertEqual(row.name, "Jack")
        self.assertEqual(row.city, "Boston")
        del cursor

    def test_laststatement(self):
        if os.environ.get("MAXSCALE_VERSION"):
            self.skipTest("MAXSCALE doesn't support BULK yet")

        cursor = self.connection.cursor(named_tuple=1)
        cursor.execute("CREATE TEMPORARY TABLE test_laststatement (id int, name varchar(64), "
                       "city varchar(64))");
        self.assertEqual(cursor.statement,
                         "CREATE TEMPORARY TABLE test_laststatement (id int, name varchar(64), city varchar(64))")

        params = [(1, u"Jack", u"Boston"),
                  (2, u"Martin", u"Ohio"),
                  (3, u"James", u"Washington"),
                  (4, u"Rasmus", u"Helsinki"),
                  (5, u"Andrey", u"Sofia")]
        cursor.executemany("INSERT INTO test_laststatement VALUES (?,?,?)", params);
        cursor.execute("SELECT * FROM test_laststatement ORDER BY id")
        self.assertEqual(cursor.statement, "SELECT * FROM test_laststatement ORDER BY id")
        del cursor

    def test_multi_cursor(self):
        cursor = self.connection.cursor()
        cursor1 = self.connection.cursor(cursor_type=1)
        cursor2 = self.connection.cursor(cursor_type=1)

        cursor.execute("CREATE TEMPORARY TABLE test_multi_cursor (a int)")
        cursor.execute("INSERT INTO test_multi_cursor VALUES (1),(2),(3),(4),(5),(6),(7),(8)")
        del cursor

        cursor1.execute("SELECT a FROM test_multi_cursor ORDER BY a")
        cursor2.execute("SELECT a FROM test_multi_cursor ORDER BY a DESC")

        for i in range(0, 8):
            self.assertEqual(cursor1.rownumber, i)
            row1 = cursor1.fetchone()
            row2 = cursor2.fetchone()
            self.assertEqual(cursor1.rownumber, cursor2.rownumber)
            self.assertEqual(row1[0] + row2[0], 9)

        del cursor1
        del cursor2

    def test_connection_attr(self):
        cursor = self.connection.cursor()
        self.assertEqual(cursor.connection, self.connection)
        del cursor

    def test_dbapi_type(self):
        cursor = self.connection.cursor()
        cursor.execute(
            "CREATE TEMPORARY TABLE test_dbapi_type (a int, b varchar(20), c blob, d datetime, e decimal)")
        cursor.execute("INSERT INTO test_dbapi_type VALUES (1, 'foo', 'blabla', now(), 10.2)");
        cursor.execute("SELECT * FROM test_dbapi_type ORDER BY a")
        expected_typecodes = [
            mariadb.NUMBER,
            mariadb.STRING,
            mariadb.BINARY,
            mariadb.DATETIME,
            mariadb.NUMBER
        ]
        row = cursor.fetchone()
        typecodes = [row[1] for row in cursor.description]
        self.assertEqual(expected_typecodes, typecodes)
        del cursor

    def test_tuple(self):
        cursor = self.connection.cursor()
        cursor.execute("CREATE TEMPORARY TABLE dyncol1 (a blob)")
        tpl = (1, 2, 3)
        cursor.execute("INSERT INTO dyncol1 VALUES (?)", tpl)
        del cursor

    def test_indicator(self):
        if self.connection.server_version < 100206:
            self.skipTest("Requires server version >= 10.2.6")
        if os.environ.get("MAXSCALE_VERSION"):
            self.skipTest("MAXSCALE doesn't support BULK yet")

        cursor = self.connection.cursor()
        cursor.execute("CREATE TEMPORARY TABLE ind1 (a int, b int default 2,c int)")
        vals = (mariadb.indicator_null, mariadb.indicator_default, 3)
        cursor.executemany("INSERT INTO ind1 VALUES (?,?,?)", [vals])
        cursor.execute("SELECT a, b, c FROM ind1")
        row = cursor.fetchone()
        self.assertEqual(row[0], None)
        self.assertEqual(row[1], 2)
        self.assertEqual(row[2], 3)

    def test_reset(self):
        cursor = self.connection.cursor()
        cursor.execute("SELECT 1 UNION SELECT 2")
        cursor.execute("SELECT 1 UNION SELECT 2")
        del cursor

    def test_fake_pickle(self):
        cursor = self.connection.cursor()
        cursor.execute("CREATE TEMPORARY TABLE test_fake_pickle (a blob)")
        k = bytes([0x80, 0x03, 0x00, 0x2E])
        cursor.execute("insert into test_fake_pickle values (?)", (k,))
        cursor.execute("select * from test_fake_pickle");
        row = cursor.fetchone()
        self.assertEqual(row[0], k)
        del cursor

    def test_no_result(self):
        cursor = self.connection.cursor()
        cursor.execute("set @a:=1")
        try:
            row = cursor.fetchone()
        except mariadb.ProgrammingError:
            pass
        del cursor

    def test_collate(self):
        cursor = self.connection.cursor()
        cursor.execute(
            "CREATE TEMPORARY TABLE `test_collate` (`test` varchar(500) COLLATE "
            "utf8mb4_unicode_ci NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci")
        cursor.execute("SET NAMES utf8mb4")
        cursor.execute(
            "SELECT * FROM `test_collate` WHERE `test` LIKE 'jj' COLLATE utf8mb4_unicode_ci")
        del cursor

    def test_conpy_8(self):
        if self.connection.server_version < 100103:
            self.skipTest("CREATE OR REPLACE PROCEDURE not supported")

        cursor = self.connection.cursor()
        sql = """
           CREATE OR REPLACE PROCEDURE p1()
           BEGIN
             SELECT 1 FROM DUAL UNION SELECT 0 FROM DUAL;
             SELECT 2 FROM DUAL;
           END
         """
        cursor.execute(sql)
        cursor.execute("call p1()")

        cursor.nextset()
        row = cursor.fetchone()
        self.assertEqual(row[0], 2);
        del cursor

    def test_conpy34(self):
        cursor = self.connection.cursor()
        cursor.execute("CREATE TEMPORARY TABLE t1 (a varchar(20), b varchar(20))")
        try:
            cursor.execute("INSERT INTO test.t1(fname, sname) VALUES (?, ?)", (("Walker", "Percy"), ("Flannery", "O'Connor")))
        except mariadb.DataError:
            pass
        del cursor
     

    def test_scroll(self):
        cursor = self.connection.cursor(buffered=True)
        stmt = "SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4"
        cursor.execute(stmt)

        try:
            cursor.scroll(0)
        except mariadb.DataError:
            pass

        cursor.scroll(2, mode='relative')
        row = cursor.fetchone()
        self.assertEqual(row[0], 3)
        cursor.scroll(-3, mode='relative')
        row = cursor.fetchone()
        self.assertEqual(row[0], 1)
        cursor.scroll(1)
        row = cursor.fetchone()
        self.assertEqual(row[0], 3)

        try:
            cursor.scroll(1)
        except mariadb.DatabaseError:
            pass

        cursor.scroll(0, mode='absolute')
        row = cursor.fetchone()
        self.assertEqual(row[0], 1)

        cursor.scroll(2, mode='absolute')
        row = cursor.fetchone()
        self.assertEqual(row[0], 3)

        cursor.scroll(-2, mode='absolute')
        self.assertEqual(None, cursor.fetchone())

        del cursor

    def test_conpy_9(self):
        cursor = self.connection.cursor()
        cursor.execute(
            "CREATE TEMPORARY TABLE test_compy_9 (a varchar(20), b double(5,2), c double)");
        cursor.execute("INSERT INTO test_compy_9 VALUES ('€uro', -123.34, 12345.678)")
        cursor.execute("SELECT a,b,c FROM test_compy_9")
        cursor.fetchone()
        d = cursor.description;
        self.assertEqual(d[0][2], 20);  # 20 code points
        self.assertEqual(d[0][3], 80);  # 80 characters
        self.assertEqual(d[1][2], 6);  # length=precision +  1
        self.assertEqual(d[1][4], 5);  # precision
        self.assertEqual(d[1][5], 2);  # scale
        del cursor

    def test_conpy_15(self):
        if os.environ.get("MAXSCALE_VERSION"):
            self.skipTest("MAXSCALE doesn't support BULK yet")
        cursor = self.connection.cursor()
        cursor.execute(
            "CREATE TEMPORARY TABLE test_conpy_15 (a int not null auto_increment primary key, b varchar(20))");
        self.assertEqual(cursor.lastrowid, 0)
        cursor.execute("INSERT INTO test_conpy_15 VALUES (null, 'foo')")
        self.assertEqual(cursor.lastrowid, 1)
        cursor.execute("SELECT LAST_INSERT_ID()")
        row = cursor.fetchone()
        self.assertEqual(row[0], 1)
        vals = [(3, "bar"), (4, "this")]
        cursor.executemany("INSERT INTO test_conpy_15 VALUES (?,?)", vals)
        self.assertEqual(cursor.lastrowid, 4)
        # Bug MDEV-16847
        # cursor.execute("SELECT LAST_INSERT_ID()")
        # row= cursor.fetchone()
        # self.assertEqual(row[0], 4)

        # Bug MDEV-16593
        # vals= [(None, "bar"), (None, "foo")]
        # cursor.executemany("INSERT INTO t1 VALUES (?,?)", vals)
        # self.assertEqual(cursor.lastrowid, 6)
        del cursor

    def test_conpy_14(self):
        if os.environ.get("MAXSCALE_VERSION"):
            self.skipTest("MAXSCALE doesn't support BULK yet")
        cursor = self.connection.cursor()
        self.assertEqual(cursor.rowcount, -1)
        cursor.execute(
            "CREATE TEMPORARY TABLE test_conpy_14 (a int not null auto_increment primary key, b varchar(20))");
        self.assertEqual(cursor.rowcount, -1)
        cursor.execute("INSERT INTO test_conpy_14 VALUES (null, 'foo')")
        self.assertEqual(cursor.rowcount, 1)
        vals = [(3, "bar"), (4, "this")]
        cursor.executemany("INSERT INTO test_conpy_14 VALUES (?,?)", vals)
        self.assertEqual(cursor.rowcount, 2)
        del cursor

    def test_closed(self):
        cursor = self.connection.cursor()
        cursor.close()
        cursor.close()
        self.assertEqual(cursor.closed, True)
        try:
            cursor.execute("set @a:=1")
        except mariadb.ProgrammingError:
            pass
        del cursor

    def test_emptycursor(self):
        cursor = self.connection.cursor()
        try:
            cursor.execute("")
        except mariadb.ProgrammingError:
            pass
        del cursor

    def test_iterator(self):
        cursor = self.connection.cursor()
        cursor.execute("select 1 union select 2 union select 3 union select 4 union select 5")
        for i, row in enumerate(cursor):
            self.assertEqual(i + 1, cursor.rownumber)
            self.assertEqual(i + 1, row[0])

    def test_update_bulk(self):
        if os.environ.get("MAXSCALE_VERSION"):
            self.skipTest("MAXSCALE doesn't support BULK yet")

        cursor = self.connection.cursor()
        cursor.execute("CREATE TEMPORARY TABLE test_update_bulk (a int primary key, b int)")
        vals = [(i,) for i in range(1000)]
        cursor.executemany("INSERT INTO test_update_bulk VALUES (?, NULL)", vals);
        self.assertEqual(cursor.rowcount, 1000)
        self.connection.autocommit = False
        cursor.executemany("UPDATE test_update_bulk SET b=2 WHERE a=?", vals);
        self.connection.commit()
        self.assertEqual(cursor.rowcount, 1000)
        self.connection.autocommit = True
        del cursor

    def test_multi_execute(self):
        cursor = self.connection.cursor()
        cursor.execute(
            "CREATE TEMPORARY TABLE test_multi_execute (a int auto_increment primary key, b int)")
        self.connection.autocommit = False
        for i in range(1, 1000):
            cursor.execute("INSERT INTO test_multi_execute VALUES (?,1)", (i,))
        self.connection.autocommit = True
        del cursor

    def test_conpy21(self):
        conn = self.connection
        cursor = conn.cursor()
        self.assertFalse(cursor.closed)
        conn.close()
        self.assertTrue(cursor.closed)
        del cursor, conn

    def test_utf8(self):
        # F0 9F 98 8E 😎 unicode 6 smiling face with sunglasses
        # F0 9F 8C B6 🌶 unicode 7 hot pepper
        # F0 9F 8E A4 🎤 unicode 8 no microphones
        # F0 9F A5 82 🥂 unicode 9 champagne glass
        con = create_connection()
        cursor = con.cursor()
        cursor.execute(
            "CREATE TEMPORARY TABLE `test_utf8` (`test` blob)")
        cursor.execute("INSERT INTO test_utf8 VALUES (?)", ("😎🌶🎤🥂",))
        cursor.execute("SELECT * FROM test_utf8")
        row = cursor.fetchone()
        self.assertEqual(row[0], b"\xf0\x9f\x98\x8e\xf0\x9f\x8c\xb6\xf0\x9f\x8e\xa4\xf0\x9f\xa5\x82")
        del cursor, con

    def test_conpy27(self):
        con = create_connection()
        cursor = con.cursor(prepared=True)
        cursor.execute("SELECT ?", (1,))
        row = cursor.fetchone()
        self.assertEqual(row[0], 1)
        cursor.execute("SELECT ?, ?, ?", ('foo',))
        row = cursor.fetchone()
        self.assertEqual(row[0], 'foo')
        del cursor, con

    def test_multiple_cursor(self):
        cursor = self.connection.cursor()
        cursor2 = self.connection.cursor()
        cursor.execute("CREATE TEMPORARY TABLE test_multiple_cursor(col1 int, col2 varchar(100))")
        cursor.execute("INSERT INTO test_multiple_cursor VALUES (1, 'val1'), (2, 'val2')")
        cursor.execute("SELECT * FROM test_multiple_cursor LIMIT 1")
        row = cursor.fetchone()
        self.assertEqual(None, cursor.fetchone())
        cursor2.execute("SELECT * FROM test_multiple_cursor LIMIT 1")
        row = cursor2.fetchone()
        del cursor, cursor2


    def test_inaccurate_rownumber(self):
        cursor = self.connection.cursor(buffered=True)
        self.assertEqual(cursor.rownumber, None)
        stmt = "SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4"
        cursor.execute(stmt)
        self.assertEqual(cursor.rownumber, 0)
        cursor.scroll(2, mode='absolute')
        self.assertEqual(cursor.rownumber, 2)
        cursor.fetchone()
        self.assertEqual(cursor.rownumber, 3)

        cursor.execute("DO 1")
        self.assertEqual(cursor.rownumber, None)

        cursor.execute("DO ?", (2,))
        self.assertEqual(cursor.rownumber, None)

        cursor.execute("SELECT 1")
        self.assertEqual(cursor.rownumber, 0)
        cursor.fetchone()
        self.assertEqual(cursor.rownumber, 1)
        cursor.fetchone()
        self.assertEqual(cursor.rownumber, 1)

        cursor.execute("SELECT ?", (1,))
        self.assertEqual(cursor.rownumber, 0)
        cursor.fetchone()
        self.assertEqual(cursor.rownumber, 1)
        cursor.fetchone()
        self.assertEqual(cursor.rownumber, 1)

        del cursor

    def test_sp1(self):
        con= create_connection()
        cursor= con.cursor()
        cursor.execute("DROP PROCEDURE IF EXISTS p1")
        cursor.execute("CREATE PROCEDURE p1( )\nBEGIN\n SELECT 1;\nEND")
        cursor.callproc("p1")
        row= cursor.fetchone()
        self.assertEqual(row[0], 1)
        cursor.execute("DROP PROCEDURE IF EXISTS p1")

    def test_sp2(self):
        con= create_connection()
        cursor= con.cursor()
        cursor.execute("DROP PROCEDURE IF EXISTS p2")
        cursor.execute("CREATE PROCEDURE p2(IN s1 VARCHAR(20), IN s2 VARCHAR(20), OUT o1 VARCHAR(40) )\nBEGIN\n SET o1:=CONCAT(s1,s2);\nEND")
        cursor.callproc("p2", ("foo", "bar", 1))
        self.assertEqual(cursor.sp_outparams, True)
        row= cursor.fetchone()
        self.assertEqual(row[0], "foobar")
        cursor.nextset()
        del cursor
        cursor=con.cursor()
        cursor.execute("CALL p2(?,?,?)", ("foo", "bar", 0))
        self.assertEqual(cursor.sp_outparams, True)
        row= cursor.fetchone()
        self.assertEqual(row[0], "foobar")
        cursor.execute("DROP PROCEDURE IF EXISTS p2")
        del cursor, con

    def test_sp3(self):
        con= create_connection()
        cursor= con.cursor()
        cursor.execute("DROP PROCEDURE IF EXISTS p3")
        cursor.execute("CREATE PROCEDURE p3(IN s1 VARCHAR(20), IN s2 VARCHAR(20), OUT o1 VARCHAR(40) )\nBEGIN\n SELECT '1';SET o1:=CONCAT(s1,s2);\nEND")
        cursor.callproc("p3", ("foo", "bar", 1))
        self.assertEqual(cursor.sp_outparams, False)
        row= cursor.fetchone()
        self.assertEqual(row[0], "1")
        cursor.nextset()
        self.assertEqual(cursor.sp_outparams, True)
        row= cursor.fetchone()
        self.assertEqual(row[0], "foobar")
        cursor.execute("DROP PROCEDURE IF EXISTS p3")
        del cursor, con

    def test_conpy42(self):
        con= create_connection()
        cursor = con.cursor()
        cursor.execute("CREATE TEMPORARY TABLE conpy42(a GEOMETRY)")
        cursor.execute("INSERT INTO conpy42 VALUES (PointFromText('point(1 1)'))")
        cursor.execute("SELECT a FROM conpy42")
        row= cursor.fetchone()
        self.assertEqual(row[0], b'\x00\x00\x00\x00\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\xf0?\x00\x00\x00\x00\x00\x00\xf0?')
        del cursor

    def test_conpy35(self):
        con= create_connection()
        cursor = con.cursor(cursor_type=mariadb.CURSOR_TYPE_READ_ONLY)
        cursor.execute("CREATE TEMPORARY table sample (id BIGINT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(64))");

        for name in ('foo', 'bar', 'baz'):
            cursor.execute("INSERT INTO sample SET name = ?", (name,))
        self.assertEqual(cursor.lastrowid, 3)

        cursor.execute("SELECT * FROM sample ORDER BY id")
        i= 0
        for row in cursor:
            i= i+1
            self.assertEqual(row[0], i)
        del cursor

    def test_conpy45(self):
        con= create_connection()
        cursor = con.cursor()
        cursor.execute("CREATE TEMPORARY table t1 (a time(3), b datetime(2))")
        cursor.execute("INSERT INTO t1 VALUES ('13:12:24.05111', '2020-10-10 14:12:24.123456')")
        cursor.execute("SELECT a,b FROM t1");
        row= cursor.fetchone()
        self.assertEqual(row[0], datetime.time(13, 12, 24, 51000))
        self.assertEqual(row[1], datetime.datetime(2020, 10, 10, 14, 12, 24, 120000))
        del cursor
        del con

    def test_conpy46(self):
        con= create_connection()
        with con.cursor() as cursor:
           cursor.execute("SELECT 'foo'")
           row= cursor.fetchone()
        self.assertEqual(row[0], "foo")
        try:
           cursor.execute("SELECT 'bar'")
        except mariadb.ProgrammingError:
            pass
        del con

    def test_conpy47(self):
        con= create_connection()
        cursor=con.cursor()
        cursor.execute("SELECT ?", (True, ))
        row= cursor.fetchone()
        self.assertEqual(row[0], 1)
        cursor.execute("SELECT ?", (False, ))
        row= cursor.fetchone()
        self.assertEqual(row[0], 0)
        del con

    def test_conpy48(self):
        con= create_connection()
        cur=con.cursor()
        cur.execute("select %s", [True])
        row= cur.fetchone()
        self.assertEqual(row[0], 1)
        cur.execute("create temporary table t1 (a int)")
        cur.executemany("insert into t1 values (%s)", [[1],(2,)])
        cur.execute("select a from t1")
        row= cur.fetchone()
        self.assertEqual(row[0], 1)
        row= cur.fetchone()
        self.assertEqual(row[0], 2)
        del con

    def test_conpy51(self):
        con= create_connection()
        cur=con.cursor(buffered=True)
        cur.execute('create temporary table temp (a int unsigned)')
        cur.execute('insert into temp values (1), (2), (3)')
        cur.execute('select a from temp order by a')
        con.commit()
        row= cur.fetchall()
        self.assertEqual(row[0][0], 1)
        self.assertEqual(row[1][0], 2)
        self.assertEqual(row[2][0], 3)
        del con

    def test_conpy52(self):
        con= create_connection()
        cur=con.cursor(buffered=True)
        cur.execute('create temporary table temp (a int unsigned)')
        cur.execute('insert into temp values (1), (2), (3)')
        cur.execute('select a from temp order by a')
        con.commit()
        row= cur.fetchall()
        self.assertEqual(row[0][0], 1)
        self.assertEqual(row[1][0], 2)
        self.assertEqual(row[2][0], 3)
        cur.execute('select a from temp where a > ?', (0, ))
        con.commit()
        row= cur.fetchall()
        self.assertEqual(row[0][0], 1)
        self.assertEqual(row[1][0], 2)
        self.assertEqual(row[2][0], 3)
        cur.execute("drop table if exists temp")
        del con

    def test_conpy49(self):
        con= create_connection()
        cur=con.cursor()
        cur.execute("create temporary table t1 (a decimal(10,2))")
        cur.execute("insert into t1 values (?)", (Decimal('10.2'),))
        cur.execute("select a from t1")
        row=cur.fetchone()
        self.assertEqual(row[0], Decimal('10.20'))
        del con

if __name__ == '__main__':
    unittest.main()
