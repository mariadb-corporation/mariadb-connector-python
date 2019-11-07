#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

import collections
import datetime
import unittest

import mariadb

from test.base_test import create_connection


class TestCursor(unittest.TestCase):

    def setUp(self):
        self.connection = create_connection()
        self.connection.autocommit = False

    def tearDown(self):
        del self.connection

    def test_date(self):
        if self.connection.server_version < 50600:
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
        cursor = self.connection.cursor()
        cursor.execute("SELECT 1 UNION SELECT 2 UNION SELECT 3", buffered=True)
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
        if self.connection.server_version < 100200:
            self.skipTest("bulk not supported")

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
        params = [(1, 2)]
        cursor.executemany("DELETE FROM bulk_delete WHERE id=?", params)
        self.assertEqual(cursor.rowcount, 2)

    def test_named_tuple(self):
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
        cursor = self.connection.cursor()
        cursor.execute("CREATE TEMPORARY TABLE ind1 (a int, b int default 2,c int)")
        vals = (mariadb.indicator_null, mariadb.indicator_default, 3)
        cursor.executemany("INSERT INTO ind1 VALUES (?,?,?)", [vals])
        cursor.execute("SELECT a, b, c FROM ind1")
        row = cursor.fetchone()
        self.assertEqual(row[0], None)
        self.assertEqual(row[1], 2)
        self.assertEqual(row[2], 3)

    def test_tuple2(self):
        cursor = self.connection.cursor()
        cursor.execute("CREATE TEMPORARY TABLE dyncol1 (a blob)")
        t = datetime.datetime(2018, 6, 20, 12, 22, 31, 123456)
        val = ([1, t, 3, (1, 2, 3)],)
        cursor.execute("INSERT INTO dyncol1 VALUES (?)", val)
        cursor.execute("SELECT a FROM dyncol1")
        row = cursor.fetchone()

        self.assertEqual(row, val)
        del cursor

    def test_set(self):
        cursor = self.connection.cursor()
        cursor.execute("CREATE TEMPORARY TABLE dyncol1 (a blob)")
        t = datetime.datetime(2018, 6, 20, 12, 22, 31, 123456)
        a = collections.OrderedDict(
            [('apple', 4), ('banana', 3), ('orange', 2), ('pear', 1), ('4', 3), (4, 4)])
        val = ([1, t, 3, (1, 2, 3), {1, 2, 3}, a],)
        cursor.execute("INSERT INTO dyncol1 VALUES (?)", val)
        cursor.execute("SELECT a FROM dyncol1")
        row = cursor.fetchone()
        self.assertEqual(row, val)
        del cursor

    def test_reset(self):
        cursor = self.connection.cursor()
        cursor.execute("SELECT 1 UNION SELECT 2", buffered=False)
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

    def test_conpy_7(self):
        cursor = self.connection.cursor()
        stmt = "SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4"
        cursor.execute(stmt, buffered=True)
        cursor.scroll(2, mode='relative')
        row = cursor.fetchone()
        self.assertEqual(row[0], 3)
        cursor.scroll(-2, mode='relative')
        row = cursor.fetchone()
        del cursor

    def test_compy_9(self):
        cursor = self.connection.cursor()
        cursor.execute(
            "CREATE TEMPORARY TABLE test_compy_9 (a varchar(20), b double(6,3), c double)");
        cursor.execute("INSERT INTO test_compy_9 VALUES ('€uro', 123.345, 12345.678)")
        cursor.execute("SELECT a,b,c FROM test_compy_9")
        cursor.fetchone()
        d = cursor.description;
        self.assertEqual(d[0][2], 4);  # 4 code points only
        self.assertEqual(d[0][3], -1);  # variable length
        self.assertEqual(d[1][2], 7);  # length=precision +  1
        self.assertEqual(d[1][4], 6);  # precision
        self.assertEqual(d[1][5], 3);  # decimals
        del cursor

    def test_conpy_15(self):
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
        cursor = self.connection.cursor()
        self.assertEqual(cursor.rowcount, -1)
        cursor.execute(
            "CREATE TEMPORARY TABLE test_conpy_14 (a int not null auto_increment primary key, b varchar(20))");
        self.assertEqual(cursor.rowcount, -1)
        cursor.execute("INSERT INTO test_conpy_14 VALUES (null, 'foo')")
        self.assertEqual(cursor.rowcount, 1)
        vals = [(3, "bar"), (4, "this")]
        cursor.executemany("INSERT INTO test_conpy_14 VALUES (?,?)", vals)
        rowcount = cursor.rowcount;
        self.assertEqual(rowcount, 2)
        cursor.execute("SELECT * FROM test_conpy_14")
        row = cursor.fetchall()
        self.assertEqual(row, [(1, "foo"), (3, "bar"), (4, "this")])
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
        except mariadb.DatabaseError:
            pass
        del cursor

    def test_iterator(self):
        cursor = self.connection.cursor()
        cursor.execute("select 1 union select 2 union select 3 union select 4 union select 5")
        for i, row in enumerate(cursor):
            self.assertEqual(i + 1, cursor.rownumber)
            self.assertEqual(i + 1, row[0])

    def test_update_bulk(self):
        if self.connection.server_version < 100200:
            self.skipTest("bulk not supported")

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
        for i in range(1, 100):
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
        con = create_connection({"charset": "utf8mb4"})
        cursor = con.cursor()
        cursor.execute(
            "CREATE TEMPORARY TABLE `test_utf8` (`test` blob)")
        cursor.execute("INSERT INTO test_utf8 VALUES (?)", ("😎🌶🎤🥂",))
        cursor.execute("SELECT * FROM test_utf8")
        row = cursor.fetchone()
        self.assertEqual(row[0], b"\xf0\x9f\x98\x8e\xf0\x9f\x8c\xb6\xf0\x9f\x8e\xa4\xf0\x9f\xa5\x82")
        del cursor, con


if __name__ == '__main__':
    unittest.main()
