#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

import datetime
import unittest
import os
import decimal
import json
from decimal import Decimal

import mariadb
from mariadb.constants import FIELD_TYPE, EXT_FIELD_TYPE, ERR, CURSOR, INDICATOR, CLIENT

from test.base_test import create_connection, is_maxscale, is_mysql

server_indicator_version = 100206


class foo(int):
    def bar(self): pass


class TestCursor(unittest.TestCase):

    def setUp(self):
        self.connection = create_connection()
        self.connection.autocommit = False

    def tearDown(self):
        del self.connection

    def test_conpy251(self):
        cursor = self.connection.cursor()
        x = cursor.nextset()
        self.assertEqual(x, None)
        cursor.close()

    def test_multiple_close(self):
        cursor = self.connection.cursor()
        cursor.close()
        del cursor

    def test_conpy283(self):
        conn= create_connection()
        cursor= conn.cursor(dictionary=True)
        self.assertEqual(cursor._resulttype, 2)
        cursor.execute("select 1 as A union SELECT 2 as A")
        row= cursor.fetchone()
        self.assertEqual(row, {'A' : 1})
        self.assertEqual(cursor._resulttype, 2)
        cursor.scroll(-1)
        self.assertEqual(cursor._resulttype, 2)
        row= cursor.fetchone()
        self.assertEqual(row, {'A' : 1})
        row= cursor.fetchone()
        self.assertEqual(row, {'A' : 2})
        self.assertEqual(cursor._resulttype, 2)
        cursor.close()
        conn.close()

    def test_date(self):
        v = self.connection.server_version
        i = self.connection.server_info.lower()
        if (v) or ("mariadb" not in i and v < 50600):
            self.skipTest("microsecond not supported")

        cursor = self.connection.cursor()
        cursor.execute("CREATE TEMPORARY TABLE test_date("
                       "c1 TIMESTAMP(6), c2 TIME(6), "
                       "c3 DATETIME(6), c4 DATE)")
        t = datetime.datetime(2018, 6, 20, 12, 22, 31, 123456)
        c1 = t
        c2 = t.time()
        c3 = t
        c4 = t.date()
        cursor.execute("INSERT INTO test_date VALUES (?,?,?,?)",
                       (c1, c2, c3, c4))

        cursor.execute("SELECT c1,c2,c3,c4 FROM test_date")
        row = cursor.fetchone()
        self.assertEqual(row[0], c1)
        self.assertEqual(row[1], datetime.timedelta(seconds=44551,
                                                    microseconds=123456))
        self.assertEqual(row[2], c3)
        self.assertEqual(row[3], c4)
        cursor.close()

    def test_numbers(self):
        cursor = self.connection.cursor()
        cursor.execute("CREATE TEMPORARY TABLE test_numbers ("
                       "a tinyint unsigned, b smallint unsigned, "
                       "c mediumint unsigned, d int unsigned, "
                       "e bigint unsigned, f double)")
        c1 = 4
        c2 = 200
        c3 = 167557
        c4 = 28688817
        c5 = 7330133222578
        c6 = 3.1415925

        cursor.execute("insert into test_numbers values (?,?,?,?,?,?)",
                       (c1, c2, c3, c4, c5, c6))

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
        cursor.execute("CREATE TEMPORARY TABLE test_string ("
                       "a char(5), b varchar(100), c tinytext, "
                       "d mediumtext, e text, f longtext)")

        c1 = "12345"
        c2 = "The length of this text is < 100 characters"
        c3 = "This should also fit into tinytext which"\
             " has a maximum of 255 characters"
        c4 = 'a' * 1000
        c5 = 'b' * 6000
        c6 = 'c' * 67000

        cursor.execute("INSERT INTO test_string VALUES (?,?,?,?,?,?)",
                       (c1, c2, c3, c4, c5, c6))

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
        cursor.execute("CREATE TEMPORARY TABLE test_blob ("
                       "a tinyblob, b mediumblob, c blob, "
                       "d longblob)")

        c1 = b'a' * 100
        c2 = b'b' * 1000
        c3 = b'c' * 10000
        c4 = b'd' * 100000

        cursor.execute("INSERT INTO test_blob VALUES (?,?,?,?)",
                       (c1, c2, c3, c4))

        cursor.execute("SELECT * FROM test_blob")
        row = cursor.fetchone()
        self.assertEqual(row[0], c1)
        self.assertEqual(row[1], c2)
        self.assertEqual(row[2], c3)
        self.assertEqual(row[3], c4)
        del cursor

    def test_inserttuple(self):
        if is_maxscale():
            self.skipTest("MAXSCALE doesn't support BULK yet")
        cursor = self.connection.cursor()
        cursor.execute("CREATE TEMPORARY TABLE test_inserttuple ("
                       "id int, name varchar(64), "
                       "city varchar(64))")
        params = ((1, u"Jack", u"Boston"),
                  (2, u"Martin", u"Ohio"),
                  (3, u"James", u"Washington"),
                  (4, u"Rasmus", u"Helsinki"),
                  (5, u"Andrey", u"Sofia"))
        cursor.executemany("INSERT INTO test_inserttuple VALUES (?,?,?)",
                           params)

        cursor.execute("SELECT name FROM test_inserttuple ORDER BY id DESC")
        row = cursor.fetchone()
        self.assertEqual("Andrey", row[0])
        del cursor

    def test_fetchmany(self):
        if is_maxscale():
            self.skipTest("MAXSCALE doesn't support BULK yet")
        cursor = self.connection.cursor()
        cursor.execute("CREATE TEMPORARY TABLE test_fetchmany ("
                       "id int, name varchar(64), "
                       "city varchar(64))")
        params = [(1, u"Jack", u"Boston"),
                  (2, u"Martin", u"Ohio"),
                  (3, u"James", u"Washington"),
                  (4, u"Rasmus", u"Helsinki"),
                  (5, u"Andrey", u"Sofia")]
        cursor.executemany("INSERT INTO test_fetchmany VALUES (?,?,?)", params)

        # test Errors
        # a) if no select was executed
        self.assertRaises(mariadb.Error, cursor.fetchall)
        # b ) if cursor was not executed
        del cursor
        cursor = self.connection.cursor(buffered=False)
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
        cursor.execute("DROP PROCEDURE IF EXISTS p1")
        sql = """
           CREATE PROCEDURE p1()
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

    def test_ext_field_types(self):
        x = self.connection.server_version_info
        if x < (10, 10, 0) or is_mysql():
            self.skipTest("Skip (MySQL and MariaDB < 10.10)")
        cursor = self.connection.cursor()
        cursor.execute("CREATE TEMPORARY TABLE t1 (a json, b uuid, c inet4, d inet6,"\
                       "e point)")
        cursor.execute("SELECT a,b,c,d,e FROM t1")
        metadata= cursor.metadata
        self.assertEqual(metadata["ext_type_or_format"][0], EXT_FIELD_TYPE.JSON)
        self.assertEqual(metadata["type"][0], FIELD_TYPE.BLOB)
        self.assertEqual(metadata["ext_type_or_format"][1], EXT_FIELD_TYPE.UUID)
        self.assertEqual(metadata["type"][1], FIELD_TYPE.STRING)
        self.assertEqual(metadata["ext_type_or_format"][2], EXT_FIELD_TYPE.INET4)
        self.assertEqual(metadata["type"][2], FIELD_TYPE.STRING)
        self.assertEqual(metadata["ext_type_or_format"][3], EXT_FIELD_TYPE.INET6)
        self.assertEqual(metadata["type"][3], FIELD_TYPE.STRING)
        self.assertEqual(metadata["ext_type_or_format"][4], EXT_FIELD_TYPE.POINT)
        self.assertEqual(metadata["type"][4], FIELD_TYPE.GEOMETRY)
        cursor.execute("SELECT a,b,c,d,e FROM t1 WHERE 1=?", (1,))
        metadata= cursor.metadata
        self.assertEqual(metadata["ext_type_or_format"][0], EXT_FIELD_TYPE.JSON)
        self.assertEqual(metadata["type"][0], FIELD_TYPE.BLOB)
        self.assertEqual(metadata["ext_type_or_format"][1], EXT_FIELD_TYPE.UUID)
        self.assertEqual(metadata["type"][1], FIELD_TYPE.STRING)
        self.assertEqual(metadata["ext_type_or_format"][2], EXT_FIELD_TYPE.INET4)
        self.assertEqual(metadata["type"][2], FIELD_TYPE.STRING)
        self.assertEqual(metadata["ext_type_or_format"][3], EXT_FIELD_TYPE.INET6)
        self.assertEqual(metadata["type"][3], FIELD_TYPE.STRING)
        self.assertEqual(metadata["ext_type_or_format"][4], EXT_FIELD_TYPE.POINT)
        self.assertEqual(metadata["type"][4], FIELD_TYPE.GEOMETRY)

        cursor.close()

    def test_xfield_types(self):
        cursor = self.connection.cursor()
        cursor.execute("SELECT a,b,c,d,e FROM t1")
        description= cursor.description
        self.assertEqual(12, len(description[0]))
        self.assertEqual(description[0][11], EXT_FIELD_TYPE.JSON)
        cursor.execute("SELECT a,b,c,d,e FROM t1 WHERE 1=?", (1,))
        description= cursor.description
        self.assertEqual(12, len(description[0]))
        self.assertEqual(description[0][11], EXT_FIELD_TYPE.JSON)
        cursor.close()
        connection.close()

    def test_xfield_types(self):
        cursor = self.connection.cursor()
        fieldinfo = mariadb.fieldinfo()
        cursor.execute("CREATE TEMPORARY TABLE test_xfield_types ("
                       "a tinyint not null auto_increment primary "
                       "key, b smallint, c int, d bigint, e float, "
                       "f decimal, g double, h char(10), i varchar(255), "
                       "j blob, k json, index(b))")
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
        x = self.connection.server_version_info
        if not is_maxscale() and (x > (10, 5, 1) or is_mysql()):
            self.assertEqual(fieldinfo.type(info[10]), "JSON")
        else:
            self.assertEqual(fieldinfo.type(info[10]), "BLOB")
        self.assertEqual(fieldinfo.flag(info[0]),
                         "NOT_NULL | PRIMARY_KEY | AUTO_INCREMENT | NUMERIC")
        self.assertEqual(fieldinfo.flag(info[1]), "PART_KEY | NUMERIC")
        self.assertEqual(fieldinfo.flag(info[9]), "BLOB | BINARY")
        del cursor

    def test_bulk_delete(self):
        if is_maxscale():
            self.skipTest("MAXSCALE doesn't support BULK yet")
        cursor = self.connection.cursor()
        cursor.execute("CREATE TEMPORARY TABLE bulk_delete ("
                       "id int, name varchar(64), city varchar(64))")
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
        if is_maxscale():
            self.skipTest("MAXSCALE doesn't support BULK yet")

        cursor = self.connection.cursor()
        cursor.execute("CREATE TEMPORARY TABLE pyformat ("
                       "id int, name varchar(64), city varchar(64))")
        params = [{"id": 1, "name": u"Jack", "city": u"Boston"},
                  {"id": 2, "name": u"Martin", "city": u"Ohio"},
                  {"id": 3, "name": u"James", "city": u"Washington"},
                  {"id": 4, "name": u"Rasmus", "city": u"Helsinki"},
                  {"id": 5, "name": u"Andrey", "city": u"Sofia"}]
        cursor.executemany("INSERT INTO pyformat VALUES "
                           "(%(id)s,%(name)s,%(city)s)", params)
        self.assertEqual(cursor.rowcount, 5)
        cursor.execute("commit")
        cursor.execute("SELECT name FROM pyformat WHERE id=5")
        row = cursor.fetchone()
        self.assertEqual(row[0], "Andrey")

    def test_format(self):
        if is_maxscale():
            self.skipTest("MAXSCALE doesn't support BULK yet")

        cursor = self.connection.cursor()
        cursor.execute("CREATE TEMPORARY TABLE pyformat ("
                       "id int, name varchar(64), city varchar(64))")
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

    def test_conpy214(self):
        cursor = self.connection.cursor(named_tuple=True)
        cursor.execute("SELECT 1 as foo")
        rows = cursor.fetchall()
        self.assertEqual(rows[0].foo, 1)
        del cursor
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("SELECT 1 as foo")
        rows = cursor.fetchall()
        self.assertEqual(rows[0]["foo"], 1)
        del cursor

    def test_named_tuple(self):
        if is_maxscale():
            self.skipTest("MAXSCALE doesn't support BULK yet")

        cursor = self.connection.cursor(named_tuple=True)
        cursor.execute("CREATE TEMPORARY TABLE test_named_tuple ("
                       "id int, name varchar(64), city varchar(64))")
        params = [(1, u"Jack", u"Boston"),
                  (2, u"Martin", u"Ohio"),
                  (3, u"James", u"Washington"),
                  (4, u"Rasmus", u"Helsinki"),
                  (5, u"Andrey", u"Sofia")]
        cursor.executemany("INSERT INTO test_named_tuple VALUES (?,?,?)",
                           params)
        cursor.execute("SELECT * FROM test_named_tuple ORDER BY id")
        row = cursor.fetchone()

        self.assertEqual(cursor.statement,
                         "SELECT * FROM test_named_tuple ORDER BY id")
        self.assertEqual(row.id, 1)
        self.assertEqual(row.name, "Jack")
        self.assertEqual(row.city, "Boston")
        del cursor

    def test_laststatement(self):
        if is_maxscale():
            self.skipTest("MAXSCALE doesn't support BULK yet")

        cursor = self.connection.cursor(named_tuple=1)
        cursor.execute("CREATE TEMPORARY TABLE test_laststatement ("
                       "id int, name varchar(64), "
                       "city varchar(64))")
        self.assertEqual(cursor.statement,
                         "CREATE TEMPORARY TABLE test_laststatement "
                         "(id int, name varchar(64), city varchar(64))")

        params = [(1, u"Jack", u"Boston"),
                  (2, u"Martin", u"Ohio"),
                  (3, u"James", u"Washington"),
                  (4, u"Rasmus", u"Helsinki"),
                  (5, u"Andrey", u"Sofia")]
        cursor.executemany("INSERT INTO test_laststatement VALUES (?,?,?)",
                           params)
        cursor.execute("SELECT * FROM test_laststatement ORDER BY id")
        self.assertEqual(cursor.statement,
                         "SELECT * FROM test_laststatement ORDER BY id")
        del cursor

    def test_multi_cursor(self):
        cursor = self.connection.cursor()
        cursor1 = self.connection.cursor(cursor_type=CURSOR.READ_ONLY)
        cursor2 = self.connection.cursor(cursor_type=CURSOR.READ_ONLY)

        cursor.execute("CREATE TEMPORARY TABLE test_multi_cursor (a int)")
        cursor.execute("INSERT INTO test_multi_cursor VALUES "
                       "(1),(2),(3),(4),(5),(6),(7),(8)")
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
        cursor.execute("CREATE TEMPORARY TABLE test_dbapi_type ("
                       "a int, b varchar(20), "
                       "c blob, d datetime, e decimal)")
        cursor.execute("INSERT INTO test_dbapi_type VALUES "
                       "(1, 'foo', 'blabla', now(), 10.2)")
        cursor.execute("SELECT * FROM test_dbapi_type ORDER BY a")
        expected_typecodes = [
            mariadb.NUMBER,
            mariadb.STRING,
            mariadb.BINARY,
            mariadb.DATETIME,
            mariadb.NUMBER
        ]
        cursor.fetchone()
        typecodes = [row[1] for row in cursor.description]
        self.assertEqual(expected_typecodes, typecodes)
        del cursor

    def test_tuple(self):
        cursor = self.connection.cursor()
        cursor.execute("CREATE TEMPORARY TABLE dyncol1 (a blob)")
        tpl = (1, 2, 3)
        try:
            cursor.execute("INSERT INTO dyncol1 VALUES (?)", tpl)
        except mariadb.ProgrammingError:
            pass
        del cursor

    def test_indicator(self):
        if is_mysql():
            self.skipTest("Skip (MySQL)")
        if self.connection.server_version < server_indicator_version:
            self.skipTest("Requires server version >= 10.2.6")
        if is_maxscale():
            self.skipTest("MAXSCALE doesn't support BULK yet")

        cursor = self.connection.cursor()
        cursor.execute("CREATE TEMPORARY TABLE ind1 (a int, "
                       "b int default 2,c int)")
        vals = [(1, 4, 3), (INDICATOR.NULL, INDICATOR.DEFAULT, 3)]
        cursor.executemany("INSERT INTO ind1 VALUES (?,?,?)", vals)
        cursor.execute("SELECT a, b, c FROM ind1")
        row = cursor.fetchone()
        self.assertEqual(row[0], 1)
        self.assertEqual(row[1], 4)
        self.assertEqual(row[2], 3)
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
        cursor.execute("select * from test_fake_pickle")
        row = cursor.fetchone()
        self.assertEqual(row[0], k)
        del cursor

    def test_no_result(self):
        cursor = self.connection.cursor()
        cursor.execute("set @a:=1")
        try:
            cursor.fetchone()
        except mariadb.ProgrammingError:
            pass
        del cursor

    def test_collate(self):
        cursor = self.connection.cursor()
        cursor.execute("CREATE TEMPORARY TABLE `test_collate` ("
                       "`test` varchar(500) COLLATE "
                       "utf8mb4_unicode_ci NOT NULL) ENGINE=InnoDB "
                       "DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci")
        cursor.execute("SET NAMES utf8mb4")
        cursor.execute("SELECT * FROM `test_collate` WHERE `test` LIKE 'jj' "
                       "COLLATE utf8mb4_unicode_ci")
        del cursor

    def test_conpy_8(self):
        cursor = self.connection.cursor()
        cursor.execute("DROP PROCEDURE IF EXISTS p1")
        sql = """
           CREATE PROCEDURE p1()
           BEGIN
             SELECT 1 FROM DUAL UNION SELECT 0 FROM DUAL;
             SELECT 2 FROM DUAL;
           END
         """
        cursor.execute(sql)
        cursor.execute("call p1()")

        cursor.nextset()
        row = cursor.fetchone()
        self.assertEqual(row[0], 2)
        del cursor

    def test_conpy34(self):
        cursor = self.connection.cursor()
        cursor.execute("CREATE TEMPORARY TABLE t1 (a varchar(20),"
                       "b varchar(20))")
        try:
            cursor.execute("INSERT INTO test.t1(fname, sname) VALUES (?, ?)",
                           (("Walker", "Percy"), ("Flannery", "O'Connor")))
        except (mariadb.ProgrammingError, mariadb.NotSupportedError):
            pass
        del cursor

    def test_scroll(self):
        cursor = self.connection.cursor(buffered=True)
        stmt = "SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4"
        cursor.execute(stmt)

        try:
            cursor.scroll(0)
        except mariadb.ProgrammingError:
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

        try:
            cursor.scroll(-2, mode='absolute')
        except mariadb.ProgrammingError:
            pass

        del cursor

    def test_conpy_9(self):
        cursor = self.connection.cursor()
        cursor.execute(
            "CREATE TEMPORARY TABLE test_compy_9 ("
            "a varchar(20), b double(5,2), c double)")
        cursor.execute("INSERT INTO test_compy_9 VALUES "
                       "('€uro', -123.34, 12345.678)")
        cursor.execute("SELECT a,b,c FROM test_compy_9")
        cursor.fetchone()
        d = cursor.description
        self.assertEqual(d[0][2], 20)  # 20 code points
        self.assertEqual(d[0][3], 80)  # 80 characters
        self.assertEqual(d[1][2], 6)  # length=precision +  1
        self.assertEqual(d[1][4], 5)  # precision
        self.assertEqual(d[1][5], 2)  # scale
        del cursor

    def test_conpy_15(self):
        if is_maxscale():
            self.skipTest("MAXSCALE doesn't support BULK yet")
        cursor = self.connection.cursor()
        cursor.execute("CREATE TEMPORARY TABLE test_conpy_15 ("
                       "a int not null auto_increment primary key,"
                       "b varchar(20))")
        self.assertEqual(cursor.lastrowid, None)
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
        # row = cursor.fetchone()
        # self.assertEqual(row[0], 4)

        # Bug MDEV-16593
        # vals= [(None, "bar"), (None, "foo")]
        # cursor.executemany("INSERT INTO t1 VALUES (?,?)", vals)
        # self.assertEqual(cursor.lastrowid, 6)
        del cursor

    def test_conpy_14(self):
        if is_maxscale():
            self.skipTest("MAXSCALE doesn't support BULK yet")
        cursor = self.connection.cursor()
        self.assertEqual(cursor.rowcount, -1)
        cursor.execute(
            "CREATE TEMPORARY TABLE test_conpy_14 ("
            "a int not null auto_increment primary key, b varchar(20))")
        self.assertEqual(cursor.rowcount, 0)
        cursor.execute("INSERT INTO test_conpy_14 VALUES (null, 'foo')")
        self.assertEqual(cursor.rowcount, 1)
        vals = [(3, "bar"), (4, "this")]
        cursor.executemany("INSERT INTO test_conpy_14 VALUES (?,?)", vals)
        self.assertEqual(cursor.rowcount, 2)
        del cursor

    def test_closed(self):
        cursor = self.connection.cursor()
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
        cursor.execute("select 1 union select 2 union select 3 "
                       "union select 4 union select 5")
        for i, row in enumerate(cursor):
            self.assertEqual(i + 1, cursor.rownumber)
            self.assertEqual(i + 1, row[0])

    def test_update_bulk(self):
        if is_maxscale():
            self.skipTest("MAXSCALE doesn't support BULK yet")

        cursor = self.connection.cursor()
        cursor.execute("CREATE TEMPORARY TABLE test_update_bulk ("
                       "a int primary key, b int)")
        vals = [(i,) for i in range(1000)]
        cursor.executemany("INSERT INTO test_update_bulk VALUES (?, NULL)",
                           vals)
        self.assertEqual(cursor.rowcount, 1000)
        self.connection.autocommit = False
        cursor.executemany("UPDATE test_update_bulk SET b=2 WHERE a=?",
                           vals)
        self.connection.commit()
        self.assertEqual(cursor.rowcount, 1000)
        self.connection.autocommit = True
        del cursor

    def test_multi_execute(self):
        cursor = self.connection.cursor()
        cursor.execute("CREATE TEMPORARY TABLE test_multi_execute ("
                       "a int auto_increment primary key, b int)")
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
        e = b"\xf0\x9f\x98\x8e\xf0\x9f\x8c\xb6\xf0\x9f\x8e\xa4\xf0\x9f\xa5\x82"
        self.assertEqual(row[0], e)
        del cursor, con

    def test_conpy27(self):
        if is_mysql():
            self.skipTest("Skip (MySQL)")
        con = create_connection()
        cursor = con.cursor(prepared=True, buffered=True)
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
        cursor.execute("CREATE TEMPORARY TABLE test_multiple_cursor("
                       "col1 int, col2 varchar(100))")
        cursor.execute("INSERT INTO test_multiple_cursor "
                       "VALUES (1, 'val1'), (2, 'val2')")
        cursor.execute("SELECT * FROM test_multiple_cursor LIMIT 1")
        cursor.fetchone()
        self.assertEqual(None, cursor.fetchone())
        cursor2.execute("SELECT * FROM test_multiple_cursor LIMIT 1")
        cursor2.fetchone()
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
        con = create_connection()
        cursor = con.cursor()
        cursor.execute("DROP PROCEDURE IF EXISTS p1")
        cursor.execute("CREATE PROCEDURE p1( )\nBEGIN\n SELECT 1;\nEND")
        cursor.callproc("p1")
        row = cursor.fetchone()
        self.assertEqual(row[0], 1)
        cursor.execute("DROP PROCEDURE IF EXISTS p1")

    def test_sp2(self):
        con = create_connection()
        if con.server_version < 100301:
            self.skipTest("Not supported in versions < 10.3")
        cursor = con.cursor()
        cursor.execute("DROP PROCEDURE IF EXISTS p2")
        cursor.execute("CREATE PROCEDURE p2(IN s1 VARCHAR(20),"
                       "IN s2 VARCHAR(20), OUT o1 VARCHAR(40) )\n"
                       "BEGIN\n"
                       "SET o1:=CAST(CONCAT(s1,s2) AS char "
                       "CHARACTER SET utf8mb4);\nEND")
        cursor.callproc("p2", ("foo", "bar", 1))
        self.assertEqual(cursor.sp_outparams, True)
        row = cursor.fetchone()
        self.assertEqual(row[0], "foobar")
        cursor.nextset()
        del cursor
        cursor = con.cursor()
        cursor.execute("CALL p2(?,?,?)", ("foo", "bar", 0))
        self.assertEqual(cursor.sp_outparams, True)
        row = cursor.fetchone()
        self.assertEqual(row[0], "foobar")
        cursor.execute("DROP PROCEDURE IF EXISTS p2")
        del cursor, con

    def test_sp3(self):
        con = create_connection()
        if con.server_version < 100301:
            self.skipTest("Not supported in versions < 10.3")
        cursor = con.cursor()
        cursor.execute("DROP PROCEDURE IF EXISTS p3")
        cursor.execute("CREATE PROCEDURE p3(IN s1 VARCHAR(20),"
                       "IN s2 VARCHAR(20), OUT o1 VARCHAR(40) )\n"
                       "BEGIN\n"
                       "SELECT '1';\n"
                       "SET o1:=CAST(CONCAT(s1,s2) "
                       "AS char CHARACTER SET utf8mb4);\n"
                       "END")
        cursor.callproc("p3", ("foo", "bar", 1))
        self.assertEqual(cursor.sp_outparams, False)
        row = cursor.fetchone()
        self.assertEqual(row[0], "1")
        cursor.nextset()
        self.assertEqual(cursor.sp_outparams, True)
        row = cursor.fetchone()
        self.assertEqual(row[0], "foobar")
        cursor.execute("DROP PROCEDURE IF EXISTS p3")
        del cursor, con

    def test_conpy42(self):
        if is_mysql():
            self.skipTest("Skip (MySQL)")
        con = create_connection()
        cursor = con.cursor()
        cursor.execute("CREATE TEMPORARY TABLE conpy42(a GEOMETRY)")
        cursor.execute("INSERT INTO conpy42 VALUES "
                       "(PointFromText('point(1 1)'))")
        cursor.execute("SELECT a FROM conpy42")
        row = cursor.fetchone()
        expected = b'' . join([b'\x00\x00\x00\x00\x01\x01\x00\x00\x00\x00\x00',
                               b'\x00\x00\x00\x00\xf0?\x00\x00\x00\x00\x00',
                               b'\x00\xf0?'])
        self.assertEqual(row[0], expected)
        del cursor

    def test_conpy35(self):
        con = create_connection()
        cursor = con.cursor()
        cursor.execute("CREATE TEMPORARY table sample ("
                       "id BIGINT AUTO_INCREMENT PRIMARY KEY,"
                       "name VARCHAR(64))")

        for name in ('foo', 'bar', 'baz'):
            cursor.execute("INSERT INTO sample SET name = ?", (name,))
        self.assertEqual(cursor.lastrowid, 3)

        cursor = con.cursor(cursor_type=CURSOR.READ_ONLY)
        cursor.execute("SELECT * FROM sample ORDER BY id")
        i = 0
        for row in cursor:
            i = i + 1
            self.assertEqual(row[0], i)
        del cursor

    def test_conpy45(self):
        con = create_connection()
        cursor = con.cursor()
        cursor.execute("CREATE TEMPORARY table t1 (a time(3), b datetime(2))")
        cursor.execute("INSERT INTO t1 VALUES ('13:12:24.05111', "
                       "'2020-10-10 14:12:24.123456')")
        cursor.execute("SELECT a,b FROM t1")
        row = cursor.fetchone()
        self.assertEqual(row[0],
                         datetime.timedelta(seconds=47544, microseconds=51000))
        self.assertEqual(row[1],
                         datetime.datetime(2020, 10, 10, 14, 12, 24, 120000))
        del cursor
        del con

    def test_conpy46(self):
        con = create_connection()
        with con.cursor() as cursor:
            cursor.execute("SELECT 'foo'")
            row = cursor.fetchone()
        self.assertEqual(row[0], "foo")
        try:
            cursor.execute("SELECT 'bar'")
        except mariadb.ProgrammingError:
            pass
        del con

    def test_conpy47(self):
        con = create_connection()
        cursor = con.cursor(buffered=True)
        cursor.execute("SELECT ?", (True, ))
        row = cursor.fetchone()
        self.assertEqual(row[0], 1)
        cursor.execute("SELECT ?", (False,))
        row = cursor.fetchone()
        self.assertEqual(row[0], 0)
        del con

    def test_conpy48(self):
        con = create_connection()
        cur = con.cursor()
        cur.execute("select %s", [True])
        row = cur.fetchone()
        self.assertEqual(row[0], 1)
        cur.execute("create temporary table t1 (a int)")
        cur.executemany("insert into t1 values (%s)", [[1], (2,)])
        cur.execute("select a from t1")
        row = cur.fetchone()
        self.assertEqual(row[0], 1)
        row = cur.fetchone()
        self.assertEqual(row[0], 2)
        del con

    def test_conpy51(self):
        con = create_connection()
        cur = con.cursor(buffered=True)
        cur.execute('create temporary table temp (a int unsigned)')
        cur.execute('insert into temp values (1), (2), (3)')
        cur.execute('select a from temp order by a')
        con.commit()
        row = cur.fetchall()
        self.assertEqual(row[0][0], 1)
        self.assertEqual(row[1][0], 2)
        self.assertEqual(row[2][0], 3)
        del con

    def test_conpy52(self):
        con = create_connection()
        cur = con.cursor(buffered=True)
        cur.execute('create temporary table temp (a int unsigned)')
        cur.execute('insert into temp values (1), (2), (3)')
        cur.execute('select a from temp order by a')
        con.commit()
        row = cur.fetchall()
        self.assertEqual(row[0][0], 1)
        self.assertEqual(row[1][0], 2)
        self.assertEqual(row[2][0], 3)
        cur.execute('select a from temp where a > ?', (0,))
        con.commit()
        row = cur.fetchall()
        self.assertEqual(row[0][0], 1)
        self.assertEqual(row[1][0], 2)
        self.assertEqual(row[2][0], 3)
        cur.execute("drop table if exists temp")
        del con

    def test_conpy49(self):
        con = create_connection()
        cur = con.cursor()
        cur.execute("create temporary table t1 (a decimal(10,2))")
        cur.execute("insert into t1 values (?)", (Decimal('10.2'),))
        cur.execute("select a from t1")
        row = cur.fetchone()
        self.assertEqual(row[0], Decimal('10.20'))
        del con

    def test_conpy56(self):
        con = create_connection()
        cur = con.cursor(dictionary=True)
        cur.execute("select 'foo' as bar, 'bar' as foo")
        row = cur.fetchone()
        self.assertEqual(row["foo"], "bar")
        self.assertEqual(row["bar"], "foo")
        del con

    def test_conpy53(self):
        con = create_connection()
        cur = con.cursor()
        cur.execute("select 1", ())
        row = cur.fetchone()
        self.assertEqual(row[0], 1)
        cur.execute("select 1", [])
        row = cur.fetchone()
        self.assertEqual(row[0], 1)
        del con

    def test_conpy58(self):
        con = create_connection()
        cursor = con.cursor()
        cursor.execute("SELECT %(val)s", {"val": 3})
        row = cursor.fetchone()
        self.assertEqual(row[0], 3)
        cursor.execute("CREATE TEMPORARY TABLE t1 (a int)")
        cursor.executemany("INSERT INTO t1 VALUES (%(val)s)",
                           [{"val": 1}, {"val": 2}])
        cursor.execute("SELECT a FROM t1 ORDER by a")
        row = cursor.fetchall()
        self.assertEqual(row[0][0], 1)
        self.assertEqual(row[1][0], 2)
        del con

    def test_conpy59(self):
        con = create_connection()
        cursor = con.cursor()
        cursor.execute("CREATE TEMPORARY TABLE t1 (a date)")
        cursor.execute("INSERT INTO t1 VALUES('0000-01-01')")
        cursor.execute("SELECT a FROM t1")
        row = cursor.fetchone()
        self.assertEqual(row[0], None)
        del con

    def test_conpy61(self):
        if is_maxscale():
            self.skipTest("MAXSCALE doesn't support BULK yet")
        if is_mysql():
            self.skipTest("Skip (MySQL)")
        con = create_connection()
        if self.connection.server_version < server_indicator_version:
            self.skipTest("Requires server version >= 10.2.6")
        cursor = con.cursor()
        cursor.execute("CREATE TEMPORARY TABLE ind1 "
                       "(a int, b int default 2,c int)")
        vals = [(1, 4, 3), (None, 2, 3)]
        cursor.executemany("INSERT INTO ind1 VALUES (?,?,?)", vals)
        cursor.execute("SELECT a, b, c FROM ind1")
        row = cursor.fetchone()
        self.assertEqual(row[0], 1)
        row = cursor.fetchone()
        self.assertEqual(row[0], None)
        cursor.execute("DELETE FROM ind1")
        vals = [(1, 4, 3), (INDICATOR.NULL, INDICATOR.DEFAULT, None)]
        cursor.executemany("INSERT INTO ind1 VALUES (?,?,?)", vals)
        cursor.execute("SELECT a, b, c FROM ind1")
        row = cursor.fetchone()
        self.assertEqual(row[0], 1)
        row = cursor.fetchone()
        self.assertEqual(row[0], None)
        self.assertEqual(row[1], 2)
        self.assertEqual(row[2], None)

        del cursor

    def test_conpy62(self):
        con = create_connection()
        cur = con.cursor()
        con = create_connection()
        query = "select round(.75 * (? / 3), 2) as val"
        cur.execute(query, [5])
        row = cur.fetchone()
        self.assertEqual(row[0], Decimal(1.25))

    def test_conpy67(self):
        con = create_connection()
        cur = con.cursor(buffered=False)
        cur.execute("SELECT 1")
        self.assertEqual(cur.rowcount, 0)
        cur = con.cursor()
        cur.execute("SELECT 1", buffered=False)
        self.assertEqual(cur.rowcount, 0)
        cur.close()

        cur = con.cursor()
        cur.execute("CREATE TEMPORARY TABLE test_conpy67 (a int)")
        cur.execute("SELECT * from test_conpy67")
        self.assertEqual(cur.rowcount, 0)
        cur.fetchall()
        self.assertEqual(cur.rowcount, 0)

    def test_negative_numbers(self):
        con = create_connection()
        cur = con.cursor()
        cur.execute("drop table if exists t1")
        cur.execute("create table t1(a tinyint, b int, c bigint)")
        cur.execute("insert into t1 values (?,?,?)", (-1, -300, -2147483649))
        cur.execute("select a, b, c FROM t1")
        row = cur.fetchone()
        self.assertEqual(row[0], -1)
        self.assertEqual(row[1], -300)
        self.assertEqual(row[2], -2147483649)
        del cur
        con.close()

    def test_none_val(self):
        con = create_connection()
        cur = con.cursor()
        cur.execute("CREATE TEMPORARY TABLE t1 (a int)")
        vals = [(1,), (2,), (4,), (None,), (3,)]
        cur.executemany("INSERT INTO t1 VALUES (?)", vals)
        cur.execute("select a from t1 order by a")
        rows = cur.fetchall()
        self.assertEqual(rows[0][0], None)
        del cur

    def test_conpy81(self):
        con = create_connection()
        cur = con.cursor()
        cur.execute("CREATE TEMPORARY TABLE t1 (a int)")
        cur.execute("INSERT INTO t1 VALUES(1)")
        cur.execute("SELECT a FROM t1")
        row = cur.fetchone()
        self.assertEqual(row[0], 1)
        cur.execute("SELECT a FROM t1 WHERE 1=?", (1,))
        row = cur.fetchone()
        self.assertEqual(row[0], 1)
        del cur

    def test_conpy94(self):
        con = create_connection()
        cur = con.cursor()
        a = foo(2)
        cur.execute("SELECT ?", (a,))
        row = cur.fetchone()
        self.assertEqual(row[0], 2)
        del cur

    def test_conpy98(self):
        con = create_connection()
        cursor = con.cursor()
        cursor.execute("SELECT CAST('foo' AS BINARY) AS anon_1")
        row = cursor.fetchone()
        self.assertEqual(row[0], b'foo')
        del cursor

    def test_conpy68(self):
        con = create_connection()
        if con.server_version < 100207:
            self.skipTest("Not supported in versions < 10.2.7")
        cursor = con.cursor()
        cursor.execute("CREATE TEMPORARY TABLE t1 (a JSON)")
        content = {'a': 'aaa', 'b': 'bbb', 'c': 123}
        cursor.execute("INSERT INTO t1 VALUES(?)", (json.dumps(content),))
        cursor.execute("SELECT a FROM t1")
        row = cursor.fetchone()
        self.assertEqual(row[0], json.dumps(content))
        del cursor

    def test_conpy123(self):
        con = create_connection({"client_flag": CLIENT.MULTI_STATEMENTS})
        cursor1 = con.cursor()
        cursor1.execute("SELECT 1; SELECT 2")
        cursor1.close()
        cursor2 = con.cursor()
        cursor2.execute("SELECT 1")
        row = cursor2.fetchone()
        self.assertEqual(row[0], 1)
        cursor2.close()
        con.close()

    def test_conpy103(self):
        con = create_connection()
        cursor = con.cursor()
        cursor.execute("CREATE TEMPORARY TABLE t1 (a decimal(10,2))")
        cursor.executemany("INSERT INTO t1 VALUES (?)", [[decimal.Decimal(1)]])
        cursor.execute("SELECT a FROM t1")
        row = cursor.fetchone()
        self.assertEqual(row[0], decimal.Decimal(1))

    def test_conpy129(self):
        conn = create_connection()
        server_version = conn.server_version
        major = int(server_version / 10000)
        minor = int((server_version % 10000) / 100)
        patch = server_version % 100
        self.assertEqual(conn.server_version_info, (major, minor, patch))
        self.assertEqual(conn.get_server_version(), (major, minor, patch))

    def test_conpy167(self):
        conn = create_connection()
        cursor = conn.cursor()

        cursor.execute("CREATE TEMPORARY table t1 ("
                       "a int not NULL auto_increment primary key, b int)")
        cursor.execute("INSERT INTO t1 VALUES (NULL, ?)", (1, ))
        self.assertEqual(cursor.rowcount, 1)
        cursor.executemany("INSERT INTO t1 VALUES (NULL, ?)", [(2, ), (3,)])
        self.assertEqual(cursor.rowcount, 2)
        del cursor

    def test_conpy168(self):
        conn = create_connection()
        cursor = conn.cursor()
        x = os.urandom(32)
        cursor.execute("SELECT cast(? as binary)", (x,))
        row = cursor.fetchone()
        self.assertEqual(row[0], x)
        del cursor

    def test_conpy133(self):
        if is_mysql():
            self.skipTest("Skip (MySQL)")
        conn = create_connection()

        cursor = conn.cursor()
        cursor.execute("SELECT /*! ? */", (1,))
        row = cursor.fetchone()
        self.assertEqual(row[0], 1)
        del cursor

        cursor = conn.cursor()
        cursor.execute("SELECT /*M! ? */", (1,))
        row = cursor.fetchone()
        self.assertEqual(row[0], 1)
        del cursor

        cursor = conn.cursor()
        cursor.execute("SELECT /*M!50601 ? */", (1,))
        row = cursor.fetchone()
        self.assertEqual(row[0], 1)
        del cursor

        cursor = conn.cursor()
        cursor.execute("SELECT /*!40301 ? */", (1,))
        row = cursor.fetchone()
        self.assertEqual(row[0], 1)
        del cursor

        cursor = conn.cursor()
        try:
            cursor.execute("SELECT /*!50701 ? */", (1,))
        except mariadb.ProgrammingError:
            pass
        del cursor

        cursor = conn.cursor()
        try:
            cursor.execute("SELECT /*!250701 ? */", (1,))
        except mariadb.ProgrammingError:
            pass
        del cursor

    def check_closed(self):
        conn = create_connection()
        cursor1 = conn.cursor()
        cursor2 = conn.cursor()
        cursor1.close()

        try:
            cursor1.execute("select 1")
        except (mariadb.ProgrammingError):
            pass
        del cursor1

        conn.close()
        try:
            cursor2.execute("select 1")
        except (mariadb.ProgrammingError):
            pass
        del cursor2, conn

    def test_conpy194(self):
        if is_mysql():
            self.skipTest("Skip (MySQL)")

        if (self.connection.server_version < 105000):
            self.skipTest("Insert returning requires MariaDB >= 10.5")

        conn = create_connection()
        cursor = conn.cursor()

        cursor.execute("create temporary table t1 "
                       "(a int not null auto_increment primary key,"
                       "b varchar(10))")

        data = [(1, ), (2, ), (3, )]

        cursor.executemany("insert into t1 values (?, 'foo') returning a",
                           data)
        rows = cursor.fetchall()
        self.assertEqual(rows, data)

        cursor.executemany("delete from t1 where a=? returning a", data)
        rows = cursor.fetchall()
        self.assertEqual(rows, data)

        cursor.execute("select a from t1")
        rows = cursor.fetchall()
        self.assertEqual(rows, [])

        data = [(1, "foo"), (2, "bar"), (3, "hello")]
        cursor.executemany("insert into t1 values (?,?) returning a,b", data)
        rows = cursor.fetchall()
        self.assertEqual(rows, data)

        cursor.executemany("replace into t1 values (?,?) returning a,b",
                           [(1, "xyz")])
        rows = cursor.fetchall()
        self.assertEqual(rows, [(1, "xyz")])

        del cursor, conn

    def test_conpy178(self):
        conn = create_connection()
        cursor = conn.cursor()
        cursor.execute("DROP PROCEDURE IF EXISTS p2")
        cursor.execute("CREATE PROCEDURE p2(IN s1 VARCHAR(20), "
                       "IN s2 VARCHAR(20), OUT o1 VARCHAR(40) )\n"
                       "BEGIN\nSET o1:=CAST(CONCAT(s1,s2) AS "
                       "char CHARACTER SET utf8mb4);\nEND")

        for i in range(0, 500):
            cursor.callproc("p2", ("foo", "bar", 1))
            row = cursor.fetchone()
            self.assertEqual(row[0], b"foobar" if is_mysql() else "foobar")

        conn.close()

    def test_conpy205(self):
        conn = create_connection()
        cursor = conn.cursor()

        cursor.execute("select %(name)s", {"name": "Marc"})
        row = cursor.fetchone()
        self.assertEqual(row[0], "Marc")

        cursor.execute("select %(name)s", {"name": "Marc",
                                           "noname": "unknown"})
        row = cursor.fetchone()
        self.assertEqual(row[0], "Marc")

        try:
            cursor.execute("select ?", {"noname": "unknown"})
        except (mariadb.ProgrammingError):
            pass

        try:
            cursor.execute("select %(name)s", (1,))
        except (mariadb.ProgrammingError):
            pass

        try:
            cursor.execute("select %(name)s", {"noname": "unknown"})
        except (mariadb.ProgrammingError):
            pass

        try:
            cursor.execute("select ?")
        except (mariadb.ProgrammingError):
            pass

        try:
            cursor.execute("select ?,?,?", (1, 2))
        except (mariadb.ProgrammingError):
            pass

        try:
            cursor.execute("select ?,?,?", (1, 2, 3, 4))
        except (mariadb.ProgrammingError):
            pass

        cursor.close()

    def test_conpy203(self):
        conn = create_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT")
        except mariadb.ProgrammingError as err:
            self.assertEqual(err.errno, ERR.ER_PARSE_ERROR)

    def test_unicode_parsing(self):
        conn = create_connection()
        cursor = conn.cursor()

        cursor.execute("create temporary table Unitéble2 ( 測試 int, méil int)")
        cursor.execute("insert into Unitéble2 values (%(測試)s, %(méil)s)",
                       {"測試": 1, "méil": 2})
        self.assertEqual(cursor.rowcount, 1)
        cursor.execute("SELECT `Unitéble2`.`測試` AS `Unitéble2_測試`,"
                       " `Unitéble2`.`méil` AS `Unitéble2_méil` FROM "
                       "`Unitéble2` WHERE ? = `Unitéble2`.`測試`", (1, ))
        cursor.fetchall()
        self.assertEqual(cursor.rowcount, 1)
        del cursor

    def test_conpy209(self):
        conn = create_connection()
        cursor = conn.cursor()
        data = ("col_Unitéble_id_seq", "foobar")
        sql = "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE "\
              "TABLE_TYPE='SEQUENCE' and TABLE_NAME=? and TABLE_SCHEMA=?"
        transformed = b"" .  join([b'SELECT TABLE_NAME FROM ',
                                   b'INFORMATION_SCHEMA.TABLES ',
                                   b'WHERE TABLE_TYPE=\'SEQUENCE\'',
                                   b' and TABLE_NAME=',
                                   b'\'col_Unit\xc3\xa9ble_id_seq\'',
                                   b' and TABLE_SCHEMA=\'foobar\''])
        cursor.execute(sql, data)
        self.assertEqual(transformed, cursor._transformed_statement)
        del cursor

    def test_conpy277(self):
        conn = create_connection()
        cursor = conn.cursor()
        cursor.execute("SET session sql_mode='TRADITIONAL,ANSI_QUOTES,ONLY_FULL_GROUP_BY,PIPES_AS_CONCAT'")
        cursor.execute('select ? as x', ('hi',))
        row= cursor.fetchone()
        self.assertEqual(row[0], 'hi')
        cursor.close()
        conn.close()

    def test_conpy213(self):
        conversions = {**{FIELD_TYPE.NEWDECIMAL: float}}
        connection = create_connection({"converter": conversions})
        cursor = connection.cursor()
        cursor.execute("SELECT 1.1")
        rows = cursor.fetchall()
        self.assertEqual(rows[0][0], 1.1)
        cursor.execute("SELECT 1.1")
        row = cursor.fetchone()
        self.assertEqual(row[0], 1.1)
        del cursor
        del connection

    def test_conpy218(self):
        conn = create_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1",  None)
        row = cursor.fetchone()
        self.assertEqual(row[0], 1)
        cursor.execute("SELECT 2",  ())
        row = cursor.fetchone()
        self.assertEqual(row[0], 2)
        cursor.execute("SELECT 3",  [])
        row = cursor.fetchone()
        self.assertEqual(row[0], 3)
        cursor.execute("SELECT 4",  {})
        row = cursor.fetchone()
        self.assertEqual(row[0], 4)
        del cursor
        del conn

    def test_conpy222(self):
        conn = create_connection()
        cursor = conn.cursor()
        cursor.close()
        del cursor

        cursor = conn.cursor()
        del cursor
        try:
            cursor.close()   # noqa: F821
        except Exception:
            pass

    def test_conpy_224(self):

        if is_maxscale():
            self.skipTest("MAXSCALE doesn't support BULK yet")

        cursor = self.connection.cursor()

        cursor.execute("CREATE TEMPORARY TABLE test_inserttuple ("
                       "id int, name varchar(64), "
                       "city varchar(64))")

        params = ((1, u"Jack", u"Boston"),
                  (2, u"Martin", u"Ohio"),
                  (3, u"James", u"Washington"),
                  (4, u"Rasmus", u"Helsinki"),
                  (5, u"Andrey", u"Sofia"))

        cursor.executemany("INSERT INTO test_inserttuple VALUES (?,?,?)",
                           params)

        cursor.executemany("INSERT INTO test_inserttuple VALUES (?,?,?)",
                           params)

        cursor = self.connection.cursor()

        cursor.execute("SELECT name FROM test_inserttuple ORDER BY id DESC")

        row = cursor.fetchone()

        self.assertEqual("Andrey", row[0])

        del cursor

    def test_conpy225(self):
        conn = create_connection()
        cursor = conn.cursor()

        cursor.execute("CREATE TEMPORARY TABLE x01 (a int, b int)")
        params = ((1, 2), (2, 3), (3, 4), (4, 5))

        cursor.executemany("INSERT INTO x01 VALUES (?,?)", params)
        self.assertEqual(cursor.rowcount, 4)
        if (not is_mysql()):
            self.assertEqual(cursor.affected_rows, 4)

        cursor.execute("UPDATE x01 SET a=1 WHERE a=1")
        self.assertEqual(cursor.rowcount, 0)
        self.assertEqual(cursor.affected_rows, 0)

        cursor.execute("UPDATE x01 SET a=1 WHERE a=4")
        self.assertEqual(cursor.affected_rows, 1)
        self.assertEqual(cursor.rowcount, 1)

    def test_conpy270(self):
        connection = create_connection()
        x = connection.server_version_info
        if x < (10, 7, 0) or is_mysql():
            self.skipTest("Skip (MySQL and MariaDB < 10.7)")

        cursor = connection.cursor()

        cursor.execute("drop table if exists t1")
        cursor.execute("create table t1 (a uuid)")
        cursor.execute("insert into t1 values (uuid())")

        # text protocol
        cursor.execute("select a from t1")
        self.assertEqual(cursor.description[0][1], mariadb.STRING);
        cursor.fetchall()

        # binary protcol
        cursor.execute("select a from t1 WHERE 1=?", (1,))
        self.assertEqual(cursor.description[0][1], mariadb.STRING);
        cursor.fetchall()

        cursor.close()
        connection.close()
    
    def test_conpy269(self):
        if is_mysql():
            self.skipTest("Skip (MySQL)")
        connection = create_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT 1 UNION SELECT 2")
        self.assertEqual(cursor.rowcount, 2)
        cursor.close()
        self.assertEqual(cursor.rowcount, -1)
        connection.close()

    def test_conpy258(self):
        connection = create_connection()
        cursor = connection.cursor()
        cursor.execute("CREATE TEMPORARY TABLE t1 (a INT(9) ZEROFILL)")
        cursor.execute("INSERT INTO t1 VALUES(123)")
        cursor.execute("SELECT a FROM t1")
        row = cursor.fetchone()
        self.assertEqual(row[0], 123)
        cursor.close()
        cursor = connection.cursor(binary=True)
        cursor.execute("SELECT a FROM t1")
        row = cursor.fetchone()
        self.assertEqual(row[0], 123)
        cursor.close()
        connection.close()

    def test_conpy276(self):
        connection = create_connection()
        cursor = connection.cursor()

        cursor.execute("SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4")
        connection.close()

        row= cursor.fetchone()
        self.assertEqual(row[0], 1)
        rows= cursor.fetchall()
        self.assertEqual(rows, [(2,),(3,),(4,)])
        cursor._seek(0)
        row= cursor.fetchone()
        self.assertEqual(row[0], 1)
        self.assertEqual(cursor.rowcount, 4)
        cursor.close()

    def test_conpy91(self):
        with create_connection() as connection:
            with connection.cursor() as cursor:
                for parameter_type in (int, decimal.Decimal):
                    with self.subTest(parameter_type=parameter_type):
                        with self.subTest(parameter_count=1):
                            with self.subTest(parameter_style='?'):
                                cursor.execute('select ?',
                                               [parameter_type(1)])
                                [[value]] = cursor.fetchall()
                                self.assertEqual(value, 1)
                            with self.subTest(parameter_style='%s'):
                                cursor.execute('select %s',
                                               [parameter_type(1)])
                                [[value]] = cursor.fetchall()
                                self.assertEqual(value, 1)
                            with self.subTest(parameter_style='%(name)s'):
                                cursor.execute('select %(value)s',
                                               dict(value=parameter_type(1)))
                                [[value]] = cursor.fetchall()
                                self.assertEqual(value, 1)
                        with self.subTest(parameter_count=2):
                            with self.subTest(parameter_style='?'):
                                cursor.execute('select ?, ?',
                                               [parameter_type(1), 1])
                                [[value, _]] = cursor.fetchall()
                                self.assertEqual(value, 1)
                            with self.subTest(parameter_style='%s'):
                                cursor.execute('select %s, %s',
                                               [parameter_type(1), 1])
                                [[value, _]] = cursor.fetchall()
                                self.assertEqual(value, 1)
                            with self.subTest(parameter_style='%(name)s'):
                                cursor.execute('select %(value)s, %(dummy)s',
                                               dict(value=parameter_type(1),
                                                    dummy=1))
                                [[value, _]] = cursor.fetchall()
                                self.assertEqual(value, 1)


if __name__ == '__main__':
    unittest.main()
