#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

import datetime
import unittest
import os
import decimal
import json
from decimal import Decimal
import array
import time

import mariadb
from mariadb.constants import FIELD_TYPE, EXT_FIELD_TYPE, ERR, CURSOR, INDICATOR, CAPABILITY as CLIENT
from tests.integration.test_pooling_async import create_async_connection

from ..base_test import is_maxscale, is_mysql, is_native
from ..conftest import get_test_config as conf

server_indicator_version = 100206


class foo(int):
    def bar(self): pass

# Check if AsyncConnection is available
HAS_ASYNC_CONNECTION = hasattr(mariadb, 'AsyncConnection') and mariadb.AsyncConnection is not None

@unittest.skipIf(not HAS_ASYNC_CONNECTION, "AsyncConnection not available")
class AsyncTestCursor(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.connection = await mariadb.AsyncConnection.connect(**conf())
        await self.connection.set_autocommit(False)

    async def asyncTearDown(self):
        await self.connection.close()
        del self.connection

    async def test_conpy251(self):
        cursor = self.connection.cursor()
        x = cursor.nextset()
        self.assertEqual(x, None)
        await cursor.close()

    async def test_multiple_close(self):
        cursor = self.connection.cursor()
        await cursor.close()
        del cursor

    @unittest.skipIf(
        os.environ.get('PYTHON_VERSION', '').startswith('pypy'),
        "Test skipped for PyPy"
    )
    async def test_conpy306(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as conn:
            cursor=conn.cursor(binary=False)
            await cursor.execute("SELECT CAST(0xEDA080 AS CHAR CHARSET UTF8MB3)");
            try:
                await cursor.fetchone()
            except Exception:
                pass
            await cursor.close()
            cursor=conn.cursor(binary=True)
            await cursor.execute("SELECT CAST(0xEDA080 AS CHAR CHARSET UTF8MB3)");
            try:
                await cursor.fetchone()
            except Exception:
                pass
            await cursor.close()

    async def test_conpy313(self):
        cursor = self.connection.cursor()
        invalid = ("NaN", "sNaN", "Infinity", "-Infinity")
        for val in invalid:
            try:
                await cursor.execute("SELECT ?", (decimal.Decimal(val),))
                self.fail(f"Expected NotSupportedError for decimal value {val}")
            except mariadb.NotSupportedError as e:
                self.assertIn(f"'{decimal.Decimal(val).__str__()}'", str(e))

        invalid = ("inf", "+inf", "nan", "-inf")
        for val in invalid:
            try:
                await cursor.execute("SELECT ?", (float(val),))
                self.fail(f"Expected NotSupportedError for float value {val}")
            except mariadb.NotSupportedError as e:
                self.assertIn(f"'{float(val)}'", str(e))

        await cursor.close()

    async def test_cursor_reconnect(self):
        if is_native():
            self.skipTest("skip test for native not supprting deprecated reconnect")
        if is_maxscale():
            self.skipTest("skip test for maxscale")

        async with await mariadb.AsyncConnection.connect(**{**conf(), **{'reconnect' : True}}) as conn:
            self.assertEqual(conn.auto_reconnect, True)
            cursor= conn.cursor(binary=True)
            await cursor.execute("SET session wait_timeout=3")

            # binary protocol should fail
            await cursor.execute("SELECT 1 UNION SELECT 2 UNION SELECT 3")
            time.sleep(5)
            try:
                 await cursor.fetchone()
            except mariadb.ProgrammingError:
                 pass

            await cursor.close()

            # Text protocol unbuffered should fail
            cursor= conn.cursor(binary=False, buffered=False)
            await cursor.execute("SET session wait_timeout=3")

            # text protocol unbuffered should fail
            await cursor.execute("SELECT 1 UNION SELECT 2 UNION SELECT 3")
            time.sleep(5)
            try:
                await cursor.fetchone()
            except mariadb.ProgrammingError:
                pass

            # reeusing cursor should work
            cursor= conn.cursor(binary=False, buffered=True)
            await cursor.execute("SET session wait_timeout=3")
            time.sleep(5)
            # reconnect
            await cursor.execute("SELECT 1 UNION SELECT 2 UNION SELECT 3")
            self.assertNotEqual(cursor._thread_id, cursor.connection.thread_id)
            row= await cursor.fetchone()
            self.assertEqual(row[0],1)
            # execute should update cursor._thread_id
            await cursor.execute("SELECT 1 UNION SELECT 2 UNION SELECT 3")
            self.assertEqual(cursor._thread_id, cursor.connection.thread_id)

            await cursor.close()

    async def test_conpy283(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as conn:

            cursor= conn.cursor(named_tuple=True)
            self.assertEqual(cursor._resulttype, 1)
            await cursor.close()
            
            cursor= conn.cursor()
            self.assertEqual(cursor._resulttype, 0)
            await cursor.close()

            cursor= conn.cursor(dictionary=True)
            self.assertEqual(cursor._resulttype, 2)
            await cursor.execute("select 1 as A union SELECT 2 as A")
            row= await cursor.fetchone()
            self.assertEqual(row, {'A' : 1})
            self.assertEqual(cursor._resulttype, 2)
            await cursor.scroll(-1)
            self.assertEqual(cursor._resulttype, 2)
            row= await cursor.fetchone()
            self.assertEqual(row, {'A' : 1})
            row= await cursor.fetchone()
            self.assertEqual(row, {'A' : 2})
            self.assertEqual(cursor._resulttype, 2)
            await cursor.close()

    async def test_conpy295(self):
        cursor= self.connection.cursor()
        await cursor.execute("DROP TABLE IF EXISTS items")
        await cursor.execute("CREATE TABLE items(id int, dsc varchar(200),d varchar(20), p tinyint, price int)")
        data= [(1408531143, 'Amazon', '2021-04-16', True, -1),
               (1442076847, 'Uber', '2021-04-15', True, -100000)]
        await cursor.executemany("INSERT INTO items VALUES (?,?,?,?,?)", data)
        await cursor.execute("SELECT * FROM items")
        rows= await cursor.fetchall()
        self.assertEqual(rows, data)
        await cursor.close()

    async def test_conpy299(self):
        if is_mysql():
            self.skipTest("Skip (MySQL)")
        if self.connection.server_version < 110702:
            self.skipTest("Requires server version >= 11.7.2")

        cursor= self.connection.cursor()
        await cursor.execute("DROP TABLE IF EXISTS t_vector")
        await cursor.execute("CREATE TABLE t_vector (id int not null, v VECTOR(3) NOT NULL, VECTOR INDEX(v))")

        # Vector can't be empty
        empty= array.array('f', [])
        try:
            await cursor.execute("INSERT INTO t_vector VALUES (?,?)", (1, empty))
        except mariadb.IntegrityError:
            pass

        # Valid vector
        data= array.array('f', [201.1, 302.2, 403.3])

        await cursor.execute("INSERT INTO t_vector VALUES (?,?)", (1, data))
        await cursor.execute("SELECT id, v, Vec_ToText(v) FROM t_vector")
        row= await cursor.fetchone()
        await self.connection.commit()
        check_data= [row[1], array.array('f', eval(row[2]))]

        await cursor.execute("DROP TABLE t_vector")
        await cursor.close()

        self.assertEqual(check_data[0], data.tobytes())
        self.assertEqual(check_data[1], data)


    async def test_date(self):
        v = self.connection.server_version
        i = self.connection.server_info.lower()
        if (v) or ("mariadb" not in i and v < 50600):
            self.skipTest("microsecond not supported")

        cursor = self.connection.cursor()
        await cursor.execute("CREATE TEMPORARY TABLE test_date("
                       "c1 TIMESTAMP(6), c2 TIME(6), "
                       "c3 DATETIME(6), c4 DATE)")
        t = datetime.datetime(2018, 6, 20, 12, 22, 31, 123456)
        c1 = t
        c2 = t.time()
        c3 = t
        c4 = t.date()
        await cursor.execute("INSERT INTO test_date VALUES (?,?,?,?)",
                       (c1, c2, c3, c4))

        await cursor.execute("SELECT c1,c2,c3,c4 FROM test_date")
        row = await cursor.fetchone()
        self.assertEqual(row[0], c1)
        self.assertEqual(row[1], datetime.timedelta(seconds=44551,
                                                    microseconds=123456))
        self.assertEqual(row[2], c3)
        self.assertEqual(row[3], c4)
        await cursor.close()

    async def test_numbers(self):
        cursor = self.connection.cursor()
        await cursor.execute("CREATE TEMPORARY TABLE test_numbers ("
                       "a tinyint unsigned, b smallint unsigned, "
                       "c mediumint unsigned, d int unsigned, "
                       "e bigint unsigned, f double)")
        c1 = 4
        c2 = 200
        c3 = 167557
        c4 = 28688817
        c5 = 7330133222578
        c6 = 3.1415925

        await cursor.execute("insert into test_numbers values (?,?,?,?,?,?)",
                       (c1, c2, c3, c4, c5, c6))

        await cursor.execute("select * from test_numbers")
        row = await cursor.fetchone()
        self.assertEqual(row[0], c1)
        self.assertEqual(row[1], c2)
        self.assertEqual(row[2], c3)
        self.assertEqual(row[3], c4)
        self.assertEqual(row[4], c5)
        self.assertEqual(row[5], c6)
        del cursor

    async def test_string(self):
        cursor = self.connection.cursor()
        await cursor.execute("CREATE TEMPORARY TABLE test_string ("
                       "a char(5), b varchar(100), c tinytext, "
                       "d mediumtext, e text, f longtext)")

        c1 = "12345"
        c2 = "The length of this text is < 100 characters"
        c3 = "This should also fit into tinytext which"\
             " has a maximum of 255 characters"
        c4 = 'a' * 1000
        c5 = 'b' * 6000
        c6 = 'c' * 67000

        await cursor.execute("INSERT INTO test_string VALUES (?,?,?,?,?,?)",
                       (c1, c2, c3, c4, c5, c6))

        await cursor.execute("SELECT * from test_string")
        row = await cursor.fetchone()
        
        self.assertEqual(row[0], c1)
        self.assertEqual(row[1], c2)
        self.assertEqual(row[2], c3)
        self.assertEqual(row[3], c4)
        self.assertEqual(row[4], c5)
        self.assertEqual(row[5], c6)
        del cursor

    async def test_blob(self):
        cursor = self.connection.cursor()
        await cursor.execute("CREATE TEMPORARY TABLE test_blob ("
                       "a tinyblob, b mediumblob, c blob, "
                       "d longblob)")

        c1 = b'a' * 100
        c2 = b'b' * 1000
        c3 = b'c' * 10000
        c4 = b'd' * 100000

        await cursor.execute("INSERT INTO test_blob VALUES (?,?,?,?)",
                       (c1, c2, c3, c4))

        await cursor.execute("SELECT * FROM test_blob")
        row = await cursor.fetchone()
        self.assertEqual(row[0], c1)
        self.assertEqual(row[1], c2)
        self.assertEqual(row[2], c3)
        self.assertEqual(row[3], c4)
        del cursor

    async def test_inserttuple(self):
        if is_maxscale():
            self.skipTest("MAXSCALE doesn't support BULK yet")
        cursor = self.connection.cursor()
        await cursor.execute("CREATE TEMPORARY TABLE test_inserttuple ("
                       "id int, name varchar(64), "
                       "city varchar(64))")
        params = ((1, u"Jack", u"Boston"),
                  (2, u"Martin", u"Ohio"),
                  (3, u"James", u"Washington"),
                  (4, u"Rasmus", u"Helsinki"),
                  (5, u"Andrey", u"Sofia"))
        await cursor.executemany("INSERT INTO test_inserttuple VALUES (?,?,?)",
                           params)

        await cursor.execute("SELECT name FROM test_inserttuple ORDER BY id DESC")
        row = await cursor.fetchone()
        self.assertEqual("Andrey", row[0])
        del cursor

    async def test_fetchmany(self):
        if is_maxscale():
            self.skipTest("MAXSCALE doesn't support BULK yet")
        cursor = self.connection.cursor()
        await cursor.execute("CREATE TEMPORARY TABLE test_fetchmany ("
                       "id int, name varchar(64), "
                       "city varchar(64))")
        params = [(1, u"Jack", u"Boston"),
                  (2, u"Martin", u"Ohio"),
                  (3, u"James", u"Washington"),
                  (4, u"Rasmus", u"Helsinki"),
                  (5, u"Andrey", u"Sofia")]
        await cursor.executemany("INSERT INTO test_fetchmany VALUES (?,?,?)", params)

        # test Errors
        # a) if no select was executed
        with self.assertRaises(mariadb.Error):
            await cursor.fetchall()
        # b ) if cursor was not executed
        del cursor
        cursor = self.connection.cursor(buffered=False)
        with self.assertRaises(mariadb.Error):
            await cursor.fetchall()

        await cursor.execute("SELECT id, name, city FROM test_fetchmany ORDER BY id")
        self.assertEqual(0, cursor.rowcount)
        row = await cursor.fetchall()
        self.assertEqual(row, params)
        self.assertEqual(5, cursor.rowcount)

        await cursor.execute("SELECT id, name, city FROM test_fetchmany ORDER BY id")
        self.assertEqual(0, cursor.rowcount)

        row = await cursor.fetchmany(1)
        self.assertEqual(row, [params[0]])
        self.assertEqual(1, cursor.rowcount)

        row = await cursor.fetchmany(2)
        self.assertEqual(row, ([params[1], params[2]]))
        self.assertEqual(3, cursor.rowcount)

        cursor.arraysize = 1
        row = await cursor.fetchmany()
        self.assertEqual(row, [params[3]])
        self.assertEqual(4, cursor.rowcount)

        cursor.arraysize = 2
        row = await cursor.fetchmany()
        self.assertEqual(row, [params[4]])
        self.assertEqual(5, cursor.rowcount)
        del cursor

    async def test_fetchmany_error(self):
        if is_maxscale():
            self.skipTest("MAXSCALE doesn't support BULK yet")
        con = await mariadb.AsyncConnection.connect(**conf())
        cursor = con.cursor()
        await cursor.execute("CREATE TEMPORARY TABLE test_fetchmany2 ("
                       "id int, name varchar(64), "
                       "city varchar(64))")
        params = [(1, u"Jack", u"Boston"),
                  (2, u"Martin", u"Ohio"),
                  (3, u"James", u"Washington"),
                  (4, u"Rasmus", u"Helsinki"),
                  (5, u"Andrey", u"Sofia")]
        await cursor.executemany("INSERT INTO test_fetchmany2 VALUES (?,?,?)", params)

        await cursor.execute("DO 1")
        with self.assertRaises(mariadb.Error):
            await cursor.fetchmany(1)
        await cursor.execute("SELECT id, name, city FROM test_fetchmany2 ORDER BY id")
        row = await cursor.fetchmany(1)
        await cursor.close()
        with self.assertRaises(mariadb.Error):
            await cursor.fetchmany(1)
        cursor = con.cursor(buffered=False)
        await cursor.execute("SELECT id, name, city FROM test_fetchmany2 ORDER BY id")
        await con.close()
        with self.assertRaises(mariadb.Error):
            await cursor.fetchmany(1)
    
    async def test_fetchall_error(self):
        if is_maxscale():
            self.skipTest("MAXSCALE doesn't support BULK yet")
        con = await mariadb.AsyncConnection.connect(**conf())
        cursor = con.cursor()
        await cursor.execute("CREATE TEMPORARY TABLE test_fetchmany22 ("
                       "id int, name varchar(64), "
                       "city varchar(64))")
        params = [(1, u"Jack", u"Boston"),
                  (2, u"Martin", u"Ohio"),
                  (3, u"James", u"Washington"),
                  (4, u"Rasmus", u"Helsinki"),
                  (5, u"Andrey", u"Sofia")]
        await cursor.executemany("INSERT INTO test_fetchmany22 VALUES (?,?,?)", params)
        await cursor.execute("DO 1")
        with self.assertRaises(mariadb.Error): 
            await cursor.fetchall()

        await cursor.execute("SELECT id, name, city FROM test_fetchmany22 ORDER BY id")
        await cursor.close()
        with self.assertRaises(mariadb.Error): 
            await cursor.fetchall()

        cursor = con.cursor(buffered=False)
        await cursor.execute("SELECT id, name, city FROM test_fetchmany22 ORDER BY id")
        await con.close()
        with self.assertRaises(mariadb.Error): 
            await cursor.fetchall()


    async def test_scroll_error(self):
        if is_maxscale():
            self.skipTest("MAXSCALE doesn't support BULK yet")
        con = await mariadb.AsyncConnection.connect(**conf())
        cursor = con.cursor()
        await cursor.execute("CREATE TEMPORARY TABLE test_fetchmany3 ("
                       "id int, name varchar(64), "
                       "city varchar(64))")
        params = [(1, u"Jack", u"Boston"),
                  (2, u"Martin", u"Ohio"),
                  (3, u"James", u"Washington"),
                  (4, u"Rasmus", u"Helsinki"),
                  (5, u"Andrey", u"Sofia")]
        await cursor.executemany("INSERT INTO test_fetchmany3 VALUES (?,?,?)", params)
        await cursor.execute("DO 1")
        
        with self.assertRaises(mariadb.Error):
            await cursor.scroll(1)

        await cursor.execute("SELECT id, name, city FROM test_fetchmany3 ORDER BY id")
        await cursor.scroll(1)

        await cursor.close()
        with self.assertRaises(mariadb.Error):
            await cursor.scroll(1)

        cursor = con.cursor(buffered=False)
        await cursor.execute("SELECT id, name, city FROM test_fetchmany3 ORDER BY id")
        with self.assertRaises(mariadb.Error):
            await cursor.scroll(100)       
        with self.assertRaises(mariadb.Error):
            await cursor.scroll(1)      
        await cursor.close()
        cursor = con.cursor(buffered=False)
        await cursor.execute("SELECT id, name, city FROM test_fetchmany3 ORDER BY id")
        await con.close()
        with self.assertRaises(mariadb.Error):
            await cursor.scroll(1)


    async def test1_multi_result(self):
        cursor = self.connection.cursor()
        await cursor.execute("DROP PROCEDURE IF EXISTS p1")
        sql = """
           CREATE PROCEDURE p1()
           BEGIN
             SELECT 1 FROM DUAL;
             SELECT 2 FROM DUAL;
           END
         """
        await cursor.execute(sql)
        await cursor.execute("call p1()")
        row = await cursor.fetchone()
        self.assertEqual(row[0], 1)
        cursor.nextset()
        row = await cursor.fetchone()
        self.assertEqual(row[0], 2)
        del cursor

    async def test_buffered(self):
        cursor = self.connection.cursor(buffered=True)
        await cursor.execute("SELECT 1 UNION SELECT 2 UNION SELECT 3")
        self.assertEqual(cursor.rowcount, 3)
        await cursor.scroll(1)
        row = await cursor.fetchone()
        self.assertEqual(row[0], 2)
        del cursor

    async def test_ext_field_types(self):
        x = self.connection.server_version_info
        if x < (10, 10, 0) or is_mysql():
            self.skipTest("Skip (MySQL and MariaDB < 10.10)")
        cursor = self.connection.cursor()
        
        # Test all extended field types including all geometry types
        await cursor.execute("CREATE TEMPORARY TABLE t1 ("
                       "a json, "
                       "b uuid, "
                       "c inet4, "
                       "d inet6, "
                       "e point, "
                       "f multipoint, "
                       "g linestring, "
                       "h multilinestring, "
                       "i polygon, "
                       "j multipolygon, "
                       "k geometrycollection)")
        await cursor.execute("SELECT a,b,c,d,e,f,g,h,i,j,k FROM t1")
        metadata = cursor.metadata
        
        # JSON
        self.assertEqual(metadata["ext_type_or_format"][0], EXT_FIELD_TYPE.JSON)
        self.assertEqual(metadata["type"][0], FIELD_TYPE.BLOB)
        
        # UUID
        self.assertEqual(metadata["ext_type_or_format"][1], EXT_FIELD_TYPE.UUID)
        self.assertEqual(metadata["type"][1], FIELD_TYPE.STRING)
        
        # INET4
        self.assertEqual(metadata["ext_type_or_format"][2], EXT_FIELD_TYPE.INET4)
        self.assertEqual(metadata["type"][2], FIELD_TYPE.STRING)
        
        # INET6
        self.assertEqual(metadata["ext_type_or_format"][3], EXT_FIELD_TYPE.INET6)
        self.assertEqual(metadata["type"][3], FIELD_TYPE.STRING)
        
        # POINT
        self.assertEqual(metadata["ext_type_or_format"][4], EXT_FIELD_TYPE.POINT)
        self.assertEqual(metadata["type"][4], FIELD_TYPE.GEOMETRY)
        
        # MULTIPOINT
        self.assertEqual(metadata["ext_type_or_format"][5], EXT_FIELD_TYPE.MULTIPOINT)
        self.assertEqual(metadata["type"][5], FIELD_TYPE.GEOMETRY)
        
        # LINESTRING
        self.assertEqual(metadata["ext_type_or_format"][6], EXT_FIELD_TYPE.LINESTRING)
        self.assertEqual(metadata["type"][6], FIELD_TYPE.GEOMETRY)
        
        # MULTILINESTRING
        self.assertEqual(metadata["ext_type_or_format"][7], EXT_FIELD_TYPE.MULTILINESTRING)
        self.assertEqual(metadata["type"][7], FIELD_TYPE.GEOMETRY)
        
        # POLYGON
        self.assertEqual(metadata["ext_type_or_format"][8], EXT_FIELD_TYPE.POLYGON)
        self.assertEqual(metadata["type"][8], FIELD_TYPE.GEOMETRY)
        
        # MULTIPOLYGON
        self.assertEqual(metadata["ext_type_or_format"][9], EXT_FIELD_TYPE.MULTIPOLYGON)
        self.assertEqual(metadata["type"][9], FIELD_TYPE.GEOMETRY)
        
        # GEOMETRYCOLLECTION
        self.assertEqual(metadata["ext_type_or_format"][10], EXT_FIELD_TYPE.GEOMETRYCOLLECTION)
        self.assertEqual(metadata["type"][10], FIELD_TYPE.GEOMETRY)

        await cursor.close()

    async def test_xfield_types(self):
        if is_maxscale():
            self.skipTest("Test doesn't work with maxscale")
        cursor = self.connection.cursor()
        fieldinfo = mariadb.fieldinfo()
        await cursor.execute("CREATE TEMPORARY TABLE test_xfield_types ("
                       "a tinyint not null auto_increment primary "
                       "key, b smallint, c int, d bigint, e float, "
                       "f decimal, g double, h char(10), i varchar(255), "
                       "j blob, k json, index(b))")
        info = cursor.description
        self.assertEqual(info, None)
        await cursor.execute("SELECT * FROM test_xfield_types")
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

    async def test_bulk_delete(self):
        if is_maxscale():
            self.skipTest("MAXSCALE doesn't support BULK yet")
        cursor = self.connection.cursor()
        await cursor.execute("CREATE TEMPORARY TABLE bulk_delete ("
                       "id int, name varchar(64), city varchar(64))")
        params = [(1, u"Jack", u"Boston"),
                  (2, u"Martin", u"Ohio"),
                  (3, u"James", u"Washington"),
                  (4, u"Rasmus", u"Helsinki"),
                  (5, u"Andrey", u"Sofia")]
        await cursor.executemany("INSERT INTO bulk_delete VALUES (?,?,?)", params)
        self.assertEqual(cursor.rowcount, 5)
        params = [(1,), (2,)]
        await cursor.executemany("DELETE FROM bulk_delete WHERE id=?", params)
        self.assertEqual(cursor.rowcount, 2)
        del cursor

    async def test_pyformat(self):
        if is_native():
            self.skipTest("Native doesn't support pyformat")
        if is_maxscale():
            self.skipTest("MAXSCALE doesn't support BULK yet")

        cursor = self.connection.cursor()
        await cursor.execute("CREATE TEMPORARY TABLE pyformat ("
                       "id int, name varchar(64), city varchar(64))")
        params = [{"id": 1, "name": u"Jack", "city": u"Boston"},
                  {"id": 2, "name": u"Martin", "city": u"Ohio"},
                  {"id": 3, "name": u"James", "city": u"Washington"},
                  {"id": 4, "name": u"Rasmus", "city": u"Helsinki"},
                  {"id": 5, "name": u"Andrey", "city": u"Sofia"}]
        await cursor.executemany("INSERT INTO pyformat VALUES "
                           "(%(id)s,%(name)s,%(city)s)", params)
        self.assertEqual(cursor.rowcount, 5)
        await cursor.execute("commit")
        await cursor.execute("SELECT name FROM pyformat WHERE id=5")
        row = await cursor.fetchone()
        self.assertEqual(row[0], "Andrey")

    async def test_format(self):
        if (is_native()):
            self.skipTest("Native only support qmark")
        if is_maxscale():
            self.skipTest("MAXSCALE doesn't support BULK yet")

        cursor = self.connection.cursor()
        await cursor.execute("CREATE TEMPORARY TABLE pyformat ("
                       "id int, name varchar(64), city varchar(64))")
        params = [(1, u"Jack", u"Boston"),
                  (2, u"Martin", u"Ohio"),
                  (3, u"James", u"Washington"),
                  (4, u"Rasmus", u"Helsinki"),
                  (5, u"Andrey", u"Sofia")]
        await cursor.executemany("INSERT INTO pyformat VALUES (%s,%s,%s)", params)
        self.assertEqual(cursor.rowcount, 5)
        await cursor.execute("commit")
        await cursor.execute("SELECT name FROM pyformat WHERE id=5")
        row = await cursor.fetchone()
        self.assertEqual(row[0], "Andrey")

    async def test_conpy214(self):
        cursor = self.connection.cursor(named_tuple=True)
        await cursor.execute("SELECT 1 as foo")
        rows = await cursor.fetchall()
        self.assertEqual(rows[0].foo, 1)
        del cursor
        cursor = self.connection.cursor(dictionary=True)
        await cursor.execute("SELECT 1 as foo")
        rows = await cursor.fetchall()
        self.assertEqual(rows[0]["foo"], 1)
        del cursor

    async def test_named_tuple(self):
        if is_maxscale():
            self.skipTest("MAXSCALE doesn't support BULK yet")

        cursor = self.connection.cursor(named_tuple=True)
        await cursor.execute("CREATE TEMPORARY TABLE test_named_tuple ("
                       "id int, name varchar(64), city varchar(64))")
        params = [(1, u"Jack", u"Boston"),
                  (2, u"Martin", u"Ohio"),
                  (3, u"James", u"Washington"),
                  (4, u"Rasmus", u"Helsinki"),
                  (5, u"Andrey", u"Sofia")]
        await cursor.executemany("INSERT INTO test_named_tuple VALUES (?,?,?)",
                           params)
        await cursor.execute("SELECT * FROM test_named_tuple ORDER BY id")
        row = await cursor.fetchone()
        if not is_native():
            self.assertEqual(cursor.statement,
                         "SELECT * FROM test_named_tuple ORDER BY id")
        self.assertEqual(row.id, 1)
        self.assertEqual(row.name, "Jack")
        self.assertEqual(row.city, "Boston")
        del cursor

    async def test_laststatement(self):
        if is_native():
            self.skipTest("Native doesn't support statement property")
        if is_maxscale():
            self.skipTest("MAXSCALE doesn't support BULK yet")

        cursor = self.connection.cursor(named_tuple=1)
        await cursor.execute("CREATE TEMPORARY TABLE test_laststatement ("
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
        await cursor.executemany("INSERT INTO test_laststatement VALUES (?,?,?)",
                           params)
        await cursor.execute("SELECT * FROM test_laststatement ORDER BY id")
        self.assertEqual(cursor.statement,
                         "SELECT * FROM test_laststatement ORDER BY id")
        del cursor

    async def test_multi_cursor(self):
        cursor = self.connection.cursor()
        cursor1 = self.connection.cursor(cursor_type=CURSOR.READ_ONLY)
        cursor2 = self.connection.cursor(cursor_type=CURSOR.READ_ONLY)

        await cursor.execute("CREATE TEMPORARY TABLE test_multi_cursor (a int)")
        await cursor.execute("INSERT INTO test_multi_cursor VALUES "
                       "(1),(2),(3),(4),(5),(6),(7),(8)")
        del cursor

        await cursor1.execute("SELECT a FROM test_multi_cursor ORDER BY a")
        await cursor2.execute("SELECT a FROM test_multi_cursor ORDER BY a DESC")

        for i in range(0, 8):
            self.assertEqual(cursor1.rownumber, i)
            row1 = await cursor1.fetchone()
            row2 = await cursor2.fetchone()
            self.assertEqual(cursor1.rownumber, cursor2.rownumber)
            self.assertEqual(row1[0] + row2[0], 9)

        del cursor1
        del cursor2

    async def test_connection_attr(self):
        cursor = self.connection.cursor()
        self.assertEqual(cursor.connection, self.connection)
        del cursor

    async def test_dbapi_type(self):
        cursor = self.connection.cursor()
        await cursor.execute("CREATE TEMPORARY TABLE test_dbapi_type ("
                       "a int, b varchar(20), "
                       "c blob, d datetime, e decimal)")
        await cursor.execute("INSERT INTO test_dbapi_type VALUES "
                       "(1, 'foo', 'blabla', now(), 10.2)")
        await cursor.execute("SELECT * FROM test_dbapi_type ORDER BY a")
        expected_typecodes = [
            mariadb.NUMBER,
            mariadb.STRING,
            mariadb.BINARY,
            mariadb.DATETIME,
            mariadb.NUMBER
        ]
        await cursor.fetchone()
        typecodes = [row[1] for row in cursor.description]
        self.assertEqual(expected_typecodes, typecodes)
        del cursor

    async def test_tuple(self):
        cursor = self.connection.cursor()
        await cursor.execute("CREATE TEMPORARY TABLE dyncol1 (a blob)")
        tpl = (1, 2, 3)
        try:
            await cursor.execute("INSERT INTO dyncol1 VALUES (?)", tpl)
        except mariadb.ProgrammingError:
            pass
        del cursor

    async def test_indicator(self):
        if is_native():
            self.skipTest("Skip for native, until suporting bulk")
        if is_mysql():
            self.skipTest("Skip (MySQL)")
        if self.connection.server_version < server_indicator_version:
            self.skipTest("Requires server version >= 10.2.6")
        if is_maxscale():
            self.skipTest("MAXSCALE doesn't support BULK yet")

        cursor = self.connection.cursor()
        await cursor.execute("CREATE TEMPORARY TABLE ind1 (a int, "
                       "b int default 2,c int)")
        vals = [(1, 4, 3), (INDICATOR.NULL, INDICATOR.DEFAULT, 3)]
        await cursor.executemany("INSERT INTO ind1 VALUES (?,?,?)", vals)
        await cursor.execute("SELECT a, b, c FROM ind1")
        row = await cursor.fetchone()
        self.assertEqual(row[0], 1)
        self.assertEqual(row[1], 4)
        self.assertEqual(row[2], 3)
        row = await cursor.fetchone()
        self.assertEqual(row[0], None)
        self.assertEqual(row[1], 2)
        self.assertEqual(row[2], 3)

    async def test_reset(self):
        cursor = self.connection.cursor()
        await cursor.execute("SELECT 1 UNION SELECT 2")
        await cursor.execute("SELECT 1 UNION SELECT 2")
        del cursor

    async def test_fake_pickle(self):
        cursor = self.connection.cursor()
        await cursor.execute("CREATE TEMPORARY TABLE test_fake_pickle (a blob)")
        k = bytes([0x80, 0x03, 0x00, 0x2E])
        await cursor.execute("insert into test_fake_pickle values (?)", (k,))
        await cursor.execute("select * from test_fake_pickle")
        row = await cursor.fetchone()
        self.assertEqual(row[0], k)
        del cursor

    async def test_no_result(self):
        cursor = self.connection.cursor()
        await cursor.execute("set @a:=1")
        try:
            await cursor.fetchone()
        except mariadb.ProgrammingError:
            pass
        del cursor

    async def test_collate(self):
        cursor = self.connection.cursor()
        await cursor.execute("CREATE TEMPORARY TABLE `test_collate` ("
                       "`test` varchar(500) COLLATE "
                       "utf8mb4_unicode_ci NOT NULL) ENGINE=InnoDB "
                       "DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci")
        await cursor.execute("SET NAMES utf8mb4")
        await cursor.execute("SELECT * FROM `test_collate` WHERE `test` LIKE 'jj' "
                       "COLLATE utf8mb4_unicode_ci")
        del cursor

    async def test_conpy_8(self):
        cursor = self.connection.cursor()
        await cursor.execute("DROP PROCEDURE IF EXISTS p1")
        sql = """
           CREATE PROCEDURE p1()
           BEGIN
             SELECT 1 FROM DUAL UNION SELECT 0 FROM DUAL;
             SELECT 2 FROM DUAL;
           END
         """
        await cursor.execute(sql)
        await cursor.execute("call p1()")

        cursor.nextset()
        row = await cursor.fetchone()
        self.assertEqual(row[0], 2)
        del cursor

    async def test_conpy298(self):
        import uuid, ipaddress

        x = self.connection.server_version_info
        if x < (10, 10, 0) or is_mysql():
            self.skipTest("Skip (MySQL and MariaDB < 10.10)")

        cursor= self.connection.cursor()
        await cursor.execute("DROP TABLE IF EXISTS t1")
        await cursor.execute("CREATE TABLE t1 (a inet6, b inet4, c uuid)")

        values= (ipaddress.ip_address('::'), ipaddress.ip_address('192.168.0.1'),
                 uuid.uuid4())
        await cursor.execute("INSERT INTO t1 VALUES (?, ?, ?)", values)
        await cursor.execute("SELECT a,b,c FROM t1")
        row= await cursor.fetchone()
        
        self.assertEqual(row[0], values[0].__str__())
        self.assertEqual(row[1], values[1].__str__())
        self.assertEqual(row[2], values[2].__str__())

        await cursor.execute("DROP TABLE t1")
        await cursor.close()

    async def test_native_object(self):
        if not is_native():
            self.skipTest("Skip for non-native")

        """Test native_object option for UUID, INET6, and INET4 types"""
        import uuid, ipaddress

        x = self.connection.server_version_info
        if x < (10, 10, 0) or is_mysql():
            self.skipTest("Skip (MySQL and MariaDB < 10.10)")

        # Test with native_object=False (default) - should return strings
        cursor_default = self.connection.cursor()
        await cursor_default.execute("DROP TABLE IF EXISTS t1")
        await cursor_default.execute("CREATE TABLE t1 (a inet6, b inet4, c uuid)")

        test_ipv6 = ipaddress.ip_address('2001:db8::1')
        test_ipv4 = ipaddress.ip_address('192.168.1.100')
        test_uuid = uuid.uuid4()

        await cursor_default.execute("INSERT INTO t1 VALUES (?, ?, ?)", 
                              (test_ipv6, test_ipv4, test_uuid))
        
        # Test text protocol (default behavior - returns strings)
        await cursor_default.execute("SELECT a, b, c FROM t1")
        row = await cursor_default.fetchone()
        
        self.assertIsInstance(row[0], str, "INET6 should be string by default")
        self.assertIsInstance(row[1], str, "INET4 should be string by default")
        self.assertIsInstance(row[2], str, "UUID should be string by default")
        self.assertEqual(row[0], str(test_ipv6))
        self.assertEqual(row[1], str(test_ipv4))
        self.assertEqual(row[2], str(test_uuid))

        # Test binary protocol (default behavior - returns bytes/strings)
        await cursor_default.close()
        cursor_default = self.connection.cursor(binary=True)
        await cursor_default.execute("SELECT a, b, c FROM t1")
        row = await cursor_default.fetchone()
        
        # Binary protocol returns bytes for these types by default
        self.assertIsInstance(row[0], (str, bytes), "INET6 should be string or bytes by default")
        self.assertIsInstance(row[1], (str, bytes), "INET4 should be string or bytes by default")
        self.assertIsInstance(row[2], (str, bytes), "UUID should be string or bytes by default")

        await cursor_default.close()

        # Test with native_object=True - should return native Python objects
        cursor_native = self.connection.cursor(native_object=True)
        
        # Test text protocol with native_object
        await cursor_native.execute("SELECT a, b, c FROM t1")
        row = await cursor_native.fetchone()
        
        self.assertIsInstance(row[0], (ipaddress.IPv6Address, ipaddress.IPv4Address), 
                            "INET6 should be ipaddress object with native_object=True")
        self.assertIsInstance(row[1], (ipaddress.IPv6Address, ipaddress.IPv4Address), 
                            "INET4 should be ipaddress object with native_object=True")
        self.assertIsInstance(row[2], uuid.UUID, 
                            "UUID should be uuid.UUID object with native_object=True")
        self.assertEqual(row[0], test_ipv6)
        self.assertEqual(row[1], test_ipv4)
        self.assertEqual(row[2], test_uuid)

        # Test binary protocol with native_object
        await cursor_native.close()
        cursor_native = self.connection.cursor(native_object=True, binary=True)
        await cursor_native.execute("SELECT a, b, c FROM t1")
        row = await cursor_native.fetchone()
        
        self.assertIsInstance(row[0], (ipaddress.IPv6Address, ipaddress.IPv4Address), 
                            "INET6 should be ipaddress object with native_object=True (binary)")
        self.assertIsInstance(row[1], (ipaddress.IPv6Address, ipaddress.IPv4Address), 
                            "INET4 should be ipaddress object with native_object=True (binary)")
        self.assertIsInstance(row[2], uuid.UUID, 
                            "UUID should be uuid.UUID object with native_object=True (binary)")
        self.assertEqual(row[0], test_ipv6)
        self.assertEqual(row[1], test_ipv4)
        self.assertEqual(row[2], test_uuid)

        # Test with NULL values
        await cursor_native.execute("INSERT INTO t1 VALUES (NULL, NULL, NULL)")
        await cursor_native.execute("SELECT a, b, c FROM t1 WHERE a IS NULL")
        row = await cursor_native.fetchone()
        
        self.assertIsNone(row[0], "NULL INET6 should be None")
        self.assertIsNone(row[1], "NULL INET4 should be None")
        self.assertIsNone(row[2], "NULL UUID should be None")

        # Cleanup
        await cursor_native.execute("DROP TABLE t1")
        await cursor_native.close()
        
        # Test native_object at connection level
        from ..base_test import create_connection
        
        async with await mariadb.AsyncConnection.connect(**{**conf(), **{"native_object": True}}) as conn_native:
            cursor_conn = conn_native.cursor()
            
            await cursor_conn.execute("DROP TABLE IF EXISTS t1")
            await cursor_conn.execute("CREATE TABLE t1 (a inet6, b inet4, c uuid)")
            await cursor_conn.execute("INSERT INTO t1 VALUES (?, ?, ?)", 
                            (test_ipv6, test_ipv4, test_uuid))
            
            # Connection-level native_object should apply to all cursors
            await cursor_conn.execute("SELECT a, b, c FROM t1")
            row = await cursor_conn.fetchone()
            
            self.assertIsInstance(row[0], (ipaddress.IPv6Address, ipaddress.IPv4Address), 
                                "INET6 should be ipaddress object with connection-level native_object=True")
            self.assertIsInstance(row[1], (ipaddress.IPv6Address, ipaddress.IPv4Address), 
                                "INET4 should be ipaddress object with connection-level native_object=True")
            self.assertIsInstance(row[2], uuid.UUID, 
                                "UUID should be uuid.UUID object with connection-level native_object=True")
            self.assertEqual(row[0], test_ipv6)
            self.assertEqual(row[1], test_ipv4)
            self.assertEqual(row[2], test_uuid)
            
            # Cursor-level setting should override connection-level setting
            cursor_override = conn_native.cursor(native_object=False)
            await cursor_override.execute("SELECT a, b, c FROM t1")
            row = await cursor_override.fetchone()
            
            self.assertIsInstance(row[0], str, 
                                "INET6 should be string when cursor overrides connection-level native_object")
            self.assertIsInstance(row[1], str, 
                                "INET4 should be string when cursor overrides connection-level native_object")
            self.assertIsInstance(row[2], str, 
                                "UUID should be string when cursor overrides connection-level native_object")
            
            await cursor_override.close()
            await cursor_conn.execute("DROP TABLE t1")
            await cursor_conn.close()

    async def test_conpy298_text(self):
        import uuid, ipaddress

        x = self.connection.server_version_info
        if x < (10, 10, 0) or is_mysql():
            self.skipTest("Skip (MySQL and MariaDB < 10.10)")

        cursor= self.connection.cursor(binary=False)
        await cursor.execute("DROP TABLE IF EXISTS t1")
        await cursor.execute("CREATE TABLE t1 (a inet6, b inet4, c uuid)")

        values= (ipaddress.ip_address('::'), ipaddress.ip_address('192.168.0.1'),
                 uuid.uuid4())

        await cursor.execute("INSERT INTO t1 VALUES (?, ?, ?)", values)
        await cursor.execute("SELECT a,b,c FROM t1")
        row= await cursor.fetchone()

        self.assertEqual(row[0], values[0].__str__())
        self.assertEqual(row[1], values[1].__str__())
        self.assertEqual(row[2], values[2].__str__())

        await cursor.execute("DROP TABLE t1")
        await cursor.close()


    async def test_conpy34(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("CREATE TEMPORARY TABLE t1 (a varchar(20),"
                               "b varchar(20))")
                try:
                    await cursor.execute("INSERT INTO test.t1(fname, sname) VALUES (?, ?)",
                                   (("Walker", "Percy"), ("Flannery", "O'Connor")))
                except (mariadb.ProgrammingError, mariadb.NotSupportedError):
                    pass

    async def test_scroll(self):
        cursor = self.connection.cursor(buffered=True)
        await cursor.execute("CREATE TEMPORARY TABLE test_scroll (a varchar(20),"
                        "b varchar(20))")        
        stmt = "SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4"
        await cursor.execute(stmt)

        try:
            await cursor.scroll(0)
        except mariadb.ProgrammingError:
            pass

        await cursor.scroll(2, mode='relative')
        row = await cursor.fetchone()
        self.assertEqual(row[0], 3)
        await cursor.scroll(-3, mode='relative')
        row = await cursor.fetchone()
        self.assertEqual(row[0], 1)
        await cursor.scroll(1)
        row = await cursor.fetchone()
        self.assertEqual(row[0], 3)

        try:
            await cursor.scroll(1)
        except mariadb.DatabaseError:
            pass

        await cursor.scroll(0, mode='absolute')
        row = await cursor.fetchone()
        self.assertEqual(row[0], 1)

        await cursor.scroll(2, mode='absolute')
        row = await cursor.fetchone()
        self.assertEqual(row[0], 3)

        try:
            await cursor.scroll(-2, mode='absolute')
        except mariadb.ProgrammingError:
            pass

        try:
            await cursor.scroll(1, mode='Wrong')
        except mariadb.ProgrammingError as e:
            pass

        await cursor.execute(stmt)
        row = await cursor.fetchone()

        cursor2 = self.connection.cursor(buffered=False)
        await cursor2.execute(stmt)
        await cursor2.execute("SELECT 2")
        await cursor2.execute(stmt)
        await cursor2.executemany("INSERT INTO test_scroll VALUES (?, ?)", [('a', 'b'), ('c', 'd')])


        del cursor
        del cursor2

    async def test_conpy_9(self):
        cursor = self.connection.cursor()
        await cursor.execute(
            "CREATE TEMPORARY TABLE test_compy_9 ("
            "a varchar(20), b double(5,2), c double)")
        await cursor.execute("INSERT INTO test_compy_9 VALUES "
                       "('€uro', -123.34, 12345.678)")
        await cursor.execute("SELECT a,b,c FROM test_compy_9")
        await cursor.fetchone()
        d = cursor.description
        self.assertEqual(d[0][2], 20)  # 20 code points
        self.assertEqual(d[0][3], 80)  # 80 characters
        self.assertEqual(d[1][2], 6)  # length=precision +  1
        self.assertEqual(d[1][4], 5)  # precision
        self.assertEqual(d[1][5], 2)  # scale
        del cursor

    async def test_conpy_15(self):
        if is_maxscale():
            self.skipTest("MAXSCALE doesn't support BULK yet")
        cursor = self.connection.cursor()
        await cursor.execute("CREATE TEMPORARY TABLE test_conpy_15 ("
                       "a int not null auto_increment primary key,"
                       "b varchar(20))")
        self.assertEqual(cursor.lastrowid, None)
        await cursor.execute("INSERT INTO test_conpy_15 VALUES (null, 'foo')")
        self.assertEqual(cursor.lastrowid, 1)
        await cursor.execute("SELECT LAST_INSERT_ID()")
        row = await cursor.fetchone()
        self.assertEqual(row[0], 1)
        vals = [(3, "bar"), (4, "this")]
        await cursor.executemany("INSERT INTO test_conpy_15 VALUES (?,?)", vals)
        self.assertEqual(cursor.lastrowid, 4)
        # Bug MDEV-16847
        # await cursor.execute("SELECT LAST_INSERT_ID()")
        # row = await cursor.fetchone()
        # self.assertEqual(row[0], 4)

        # Bug MDEV-16593
        # vals= [(None, "bar"), (None, "foo")]
        # await cursor.executemany("INSERT INTO t1 VALUES (?,?)", vals)
        # self.assertEqual(cursor.lastrowid, 6)
        del cursor

    async def test_conpy_14(self):
        if is_maxscale():
            self.skipTest("MAXSCALE doesn't support BULK yet")
        cursor = self.connection.cursor()
        self.assertEqual(cursor.rowcount, -1)
        await cursor.execute(
            "CREATE TEMPORARY TABLE test_conpy_14 ("
            "a int not null auto_increment primary key, b varchar(20))")
        self.assertEqual(cursor.rowcount, 0)
        await cursor.execute("INSERT INTO test_conpy_14 VALUES (null, 'foo')")
        self.assertEqual(cursor.rowcount, 1)
        vals = [(3, "bar"), (4, "this")]
        await cursor.executemany("INSERT INTO test_conpy_14 VALUES (?,?)", vals)
        self.assertEqual(cursor.rowcount, 2)
        del cursor

    async def test_closed(self):
        cursor = self.connection.cursor()
        await cursor.close()
        self.assertEqual(cursor.closed, True)
        try:
            await cursor.execute("set @a:=1")
        except mariadb.ProgrammingError:
            pass
        del cursor

    async def test_emptycursor(self):
        cursor = self.connection.cursor()
        try:
            await cursor.execute("")
        except mariadb.ProgrammingError:
            pass
        del cursor

    async def test_iterator(self):
        cursor = self.connection.cursor()
        await cursor.execute("select 1 union select 2 union select 3 "
                       "union select 4 union select 5")
        i = 0
        async for row in cursor:
            i += 1
            self.assertEqual(i, cursor.rownumber)
            self.assertEqual(i, row[0])

    async def test_update_bulk(self):
        if is_maxscale():
            self.skipTest("MAXSCALE doesn't support BULK yet")

        cursor = self.connection.cursor()
        await cursor.execute("CREATE TEMPORARY TABLE test_update_bulk ("
                       "a int primary key, b int)")
        vals = [(i,) for i in range(1000)]
        await cursor.executemany("INSERT INTO test_update_bulk VALUES (?, NULL)",
                           vals)
        self.assertEqual(cursor.rowcount, 1000)
        await self.connection.set_autocommit(False)
        await cursor.executemany("UPDATE test_update_bulk SET b=2 WHERE a=?",
                           vals)
        await self.connection.commit()
        self.assertEqual(cursor.rowcount, 1000)
        await self.connection.set_autocommit(True)
        del cursor

    async def test_multi_execute(self):
        cursor = self.connection.cursor()
        await cursor.execute("CREATE TEMPORARY TABLE test_multi_execute ("
                       "a int auto_increment primary key, b int)")
        await self.connection.set_autocommit(False)
        for i in range(1, 1000):
            await cursor.execute("INSERT INTO test_multi_execute VALUES (?,1)", (i,))
        await self.connection.set_autocommit(True)
        del cursor

    async def test_conpy21(self):
        conn = await mariadb.AsyncConnection.connect(**conf())
        cursor = conn.cursor()
        self.assertFalse(cursor.closed)
        await conn.close()
        self.assertTrue(cursor.closed)
        del cursor, conn

    async def test_utf8(self):
        # F0 9F 98 8E 😎 unicode 6 smiling face with sunglasses
        # F0 9F 8C B6 🌶 unicode 7 hot pepper
        # F0 9F 8E A4 🎤 unicode 8 no microphones
        # F0 9F A5 82 🥂 unicode 9 champagne glass
        async with await mariadb.AsyncConnection.connect(**conf()) as conn:
            cursor = conn.cursor()
            await cursor.execute(
                "CREATE TEMPORARY TABLE `test_utf8` (`test` blob)")
            await cursor.execute("INSERT INTO test_utf8 VALUES (?)", ("😎🌶🎤🥂",))
            await cursor.execute("SELECT * FROM test_utf8")
            row = await cursor.fetchone()
            e = b"\xf0\x9f\x98\x8e\xf0\x9f\x8c\xb6\xf0\x9f\x8e\xa4\xf0\x9f\xa5\x82"
            self.assertEqual(row[0], e)
            del cursor

    async def test_conpy27(self):
        if is_mysql():
            self.skipTest("Skip (MySQL)")
        async with await mariadb.AsyncConnection.connect(**conf()) as conn:
            cursor = conn.cursor(prepared=True, buffered=True)
            await cursor.execute("SELECT ?", (1,))
            row = await cursor.fetchone()
            self.assertEqual(row[0], 1)
            
            if is_native():
                # would have thrown Parameter count mismatch is not passing other
                await cursor.execute("SELECT ?, ?, ?", ('foo', 'bar', 'baz'))
            else:
                await cursor.execute("SELECT ?, ?, ?", ('foo',))
            row = await cursor.fetchone()
            self.assertEqual(row[0], 'foo')
            del cursor

    async def test_multiple_cursor(self):
        cursor = self.connection.cursor()
        cursor2 = self.connection.cursor()
        await cursor.execute("CREATE TEMPORARY TABLE test_multiple_cursor("
                       "col1 int, col2 varchar(100))")
        await cursor.execute("INSERT INTO test_multiple_cursor "
                       "VALUES (1, 'val1'), (2, 'val2')")
        await cursor.execute("SELECT * FROM test_multiple_cursor LIMIT 1")
        await cursor.fetchone()
        self.assertEqual(None, await cursor.fetchone())
        await cursor2.execute("SELECT * FROM test_multiple_cursor LIMIT 1")
        await cursor2.fetchone()
        del cursor, cursor2

    async def test_inaccurate_rownumber(self):
        cursor = self.connection.cursor(buffered=True)
        self.assertEqual(cursor.rownumber, None)
        stmt = "SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4"
        await cursor.execute(stmt)
        self.assertEqual(cursor.rownumber, 0)
        await cursor.scroll(2, mode='absolute')
        self.assertEqual(cursor.rownumber, 2)
        await cursor.fetchone()
        self.assertEqual(cursor.rownumber, 3)

        await cursor.execute("DO 1")
        self.assertEqual(cursor.rownumber, None)

        await cursor.execute("DO ?", (2,))
        self.assertEqual(cursor.rownumber, None)

        await cursor.execute("SELECT 1")
        self.assertEqual(cursor.rownumber, 0)
        await cursor.fetchone()
        self.assertEqual(cursor.rownumber, 1)
        await cursor.fetchone()
        self.assertEqual(cursor.rownumber, 1)

        await cursor.execute("SELECT ?", (1,))
        self.assertEqual(cursor.rownumber, 0)
        await cursor.fetchone()
        self.assertEqual(cursor.rownumber, 1)
        await cursor.fetchone()
        self.assertEqual(cursor.rownumber, 1)

        del cursor

    async def test_sp1(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as conn:
            cursor = conn.cursor()
            await cursor.execute("DROP PROCEDURE IF EXISTS p1")
            await cursor.execute("CREATE PROCEDURE p1( )\nBEGIN\n SELECT 1;\nEND")
            await cursor.callproc("p1")
            row = await cursor.fetchone()
            self.assertEqual(row[0], 1)
            await cursor.execute("DROP PROCEDURE IF EXISTS p1")

    async def test_sp2(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            if con.server_version < 100301:
                self.skipTest("Not supported in versions < 10.3")
            cursor = con.cursor()
            await cursor.execute("DROP PROCEDURE IF EXISTS p2")
            await cursor.execute("CREATE PROCEDURE p2(IN s1 VARCHAR(20),"
                           "IN s2 VARCHAR(20), OUT o1 VARCHAR(40) )\n"
                           "BEGIN\n"
                           "SET o1:=CAST(CONCAT(s1,s2) AS char "
                           "CHARACTER SET utf8mb4);\nEND")
            await cursor.callproc("p2", ("foo", "bar", 1))
            self.assertEqual(cursor.sp_outparams, True)
            row = await cursor.fetchone()
            self.assertEqual(row[0], "foobar")
            cursor.nextset()
            del cursor
            cursor = con.cursor()
            # not set with native, since will result in OUT or INOUT argument variable missing
            if not is_native():
                await cursor.execute("CALL p2(?,?,?)", ("foo", "bar", 0))
                self.assertEqual(cursor.sp_outparams, True)
                row = await cursor.fetchone()
                self.assertEqual(row[0], "foobar")
                await cursor.execute("DROP PROCEDURE IF EXISTS p2")
                del cursor

    async def test_sp3(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            if con.server_version < 100301:
                self.skipTest("Not supported in versions < 10.3")
            cursor = con.cursor()
            self.assertEqual(cursor.sp_outparams, False)
            await cursor.execute("DROP PROCEDURE IF EXISTS p3")
            await cursor.execute("CREATE PROCEDURE p3(IN s1 VARCHAR(20),"
                           "IN s2 VARCHAR(20), OUT o1 VARCHAR(40) )\n"
                           "BEGIN\n"
                           "SELECT '1';\n"
                           "SET o1:=CAST(CONCAT(s1,s2) "
                           "AS char CHARACTER SET utf8mb4);\n"
                           "END")
            await cursor.callproc("p3", ("foo", "bar", 1))
            self.assertEqual(cursor.sp_outparams, False)
            row = await cursor.fetchone()
            self.assertEqual(row[0], "1")
            cursor.nextset()
            self.assertEqual(cursor.sp_outparams, True)
            row = await cursor.fetchone()
            self.assertEqual(row[0], "foobar")
            await cursor.execute("DROP PROCEDURE IF EXISTS p3")
            del cursor

    async def test_conpy42(self):
        if is_mysql():
            self.skipTest("Skip (MySQL)")
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            cursor = con.cursor()
            await cursor.execute("CREATE TEMPORARY TABLE conpy42(a GEOMETRY)")
            await cursor.execute("INSERT INTO conpy42 VALUES "
                           "(PointFromText('point(1 1)'))")
            await cursor.execute("SELECT a FROM conpy42")
            row = await cursor.fetchone()
            expected = b'' . join([b'\x00\x00\x00\x00\x01\x01\x00\x00\x00\x00\x00',
                                   b'\x00\x00\x00\x00\xf0?\x00\x00\x00\x00\x00',
                                   b'\x00\xf0?'])
            self.assertEqual(row[0], expected)
            del cursor

    async def test_conpy35(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            cursor = con.cursor()
            await cursor.execute("CREATE TEMPORARY table sample ("
                           "id BIGINT AUTO_INCREMENT PRIMARY KEY,"
                           "name VARCHAR(64))")

            for name in ('foo', 'bar', 'baz'):
                await cursor.execute("INSERT INTO sample SET name = ?", (name,))
            self.assertEqual(cursor.lastrowid, 3)

            cursor = con.cursor(cursor_type=CURSOR.READ_ONLY)
            await cursor.execute("SELECT * FROM sample ORDER BY id")
            i = 0
            async for row in cursor:
                i = i + 1
                self.assertEqual(row[0], i)
            del cursor

    async def test_conpy45(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            cursor = con.cursor()
            await cursor.execute("CREATE TEMPORARY table t1 (a time(3), b datetime(2))")
            await cursor.execute("INSERT INTO t1 VALUES ('13:12:24.05111', "
                           "'2020-10-10 14:12:24.123456')")
            await cursor.execute("SELECT a,b FROM t1")
            row = await cursor.fetchone()
            self.assertEqual(row[0],
                             datetime.timedelta(seconds=47544, microseconds=51000))
            self.assertEqual(row[1],
                             datetime.datetime(2020, 10, 10, 14, 12, 24, 120000))
            del cursor

    async def test_conpy46(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            async with con.cursor() as cursor:
                await cursor.execute("SELECT 'foo'")
                row = await cursor.fetchone()
            self.assertEqual(row[0], "foo")
            try:
                await cursor.execute("SELECT 'bar'")
            except mariadb.ProgrammingError:
                pass

    async def test_conpy47(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            cursor = con.cursor(buffered=True)
            await cursor.execute("SELECT ?", (True, ))
            row = await cursor.fetchone()
            self.assertEqual(row[0], 1)
            await cursor.execute("SELECT ?", (False,))
            row = await cursor.fetchone()
            self.assertEqual(row[0], 0)
            await cursor.close()

    async def test_conpy48(self):
        if is_native():
            self.skipTest("Native only support QMARK")
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            cur = con.cursor()
            await cur.execute("select %s", [True])
            row = await cur.fetchone()
            self.assertEqual(row[0], 1)
            await cur.execute("create temporary table t1 (a int)")
            await cur.executemany("insert into t1 values (%s)", [[1], (2,)])
            await cur.execute("select a from t1")
            row = await cur.fetchone()
            self.assertEqual(row[0], 1)
            row = await cur.fetchone()
            self.assertEqual(row[0], 2)
            await cur.close()

    async def test_conpy51(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            cur = con.cursor(buffered=True)
            await cur.execute('create temporary table temp (a int unsigned)')
            await cur.execute('insert into temp values (1), (2), (3)')
            await cur.execute('select a from temp order by a')
            await con.commit()
            row = await cur.fetchall()
            self.assertEqual(row[0][0], 1)
            self.assertEqual(row[1][0], 2)
            self.assertEqual(row[2][0], 3)
            await cur.close()

    async def test_conpy52(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            cur = con.cursor(buffered=True)
            await cur.execute('create temporary table temp (a int unsigned)')
            await cur.execute('insert into temp values (1), (2), (3)')
            await cur.execute('select a from temp order by a')
            await con.commit()
            row = await cur.fetchall()
            self.assertEqual(row[0][0], 1)
            self.assertEqual(row[1][0], 2)
            self.assertEqual(row[2][0], 3)
            await cur.execute('select a from temp where a > ?', (0,))
            await con.commit()
            row = await cur.fetchall()
            self.assertEqual(row[0][0], 1)
            self.assertEqual(row[1][0], 2)
            self.assertEqual(row[2][0], 3)
            await cur.execute("drop table if exists temp")
            await cur.close()

    async def test_conpy49(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            cur = con.cursor()
            await cur.execute("create temporary table t1 (a decimal(10,2))")
            await cur.execute("insert into t1 values (?)", (Decimal('10.2'),))
            await cur.execute("select a from t1")
            row = await cur.fetchone()
            self.assertEqual(row[0], Decimal('10.20'))
            await cur.close()

    async def test_conpy56(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            cur = con.cursor(dictionary=True)
            await cur.execute("select 'foo' as bar, 'bar' as foo")
            row = await cur.fetchone()
            self.assertEqual(row["foo"], "bar")
            self.assertEqual(row["bar"], "foo")
            await cur.close()

    async def test_conpy53(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            cur = con.cursor()
            await cur.execute("select 1", ())
            row = await cur.fetchone()
            self.assertEqual(row[0], 1)
            await cur.execute("select 1", [])
            row = await cur.fetchone()
            self.assertEqual(row[0], 1)
            await cur.close()

    async def test_conpy58(self):
        if is_native():
            self.skipTest("Native only support QMARK")
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            cursor = con.cursor()
            await cursor.execute("SELECT %(val)s", {"val": 3})
            row = await cursor.fetchone()
            self.assertEqual(row[0], 3)
            await cursor.execute("CREATE TEMPORARY TABLE t1 (a int)")
            await cursor.executemany("INSERT INTO t1 VALUES (%(val)s)",
                               [{"val": 1}, {"val": 2}])
            await cursor.execute("SELECT a FROM t1 ORDER by a")
            row = await cursor.fetchall()
            self.assertEqual(row[0][0], 1)
            self.assertEqual(row[1][0], 2)
            await cursor.close()

    async def test_conpy59(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            cursor = con.cursor()
            await cursor.execute("CREATE TEMPORARY TABLE t1 (a date)")
            await cursor.execute("INSERT INTO t1 VALUES('0000-01-01')")
            await cursor.execute("SELECT a FROM t1")
            row = await cursor.fetchone()
            self.assertEqual(row[0], None)
            await cursor.close()

    async def test_conpy61(self):
        if is_maxscale():
            self.skipTest("MAXSCALE doesn't support BULK yet")
        if is_mysql():
            self.skipTest("Skip (MySQL)")
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            if self.connection.server_version < server_indicator_version:
                self.skipTest("Requires server version >= 10.2.6")
            cursor = con.cursor()
            await cursor.execute("CREATE TEMPORARY TABLE ind1 "
                           "(a int, b int default 2,c int)")
            vals = [(1, 4, 3), (None, 2, 3)]
            await cursor.executemany("INSERT INTO ind1 VALUES (?,?,?)", vals)
            await cursor.execute("SELECT a, b, c FROM ind1")
            row = await cursor.fetchone()
            self.assertEqual(row[0], 1)
            row = await cursor.fetchone()
            self.assertEqual(row[0], None)
            await cursor.execute("DELETE FROM ind1")
            vals = [(1, 4, 3), (INDICATOR.NULL, INDICATOR.DEFAULT, None)]
            await cursor.executemany("INSERT INTO ind1 VALUES (?,?,?)", vals)
            await cursor.execute("SELECT a, b, c FROM ind1")
            row = await cursor.fetchone()
            self.assertEqual(row[0], 1)
            row = await cursor.fetchone()
            self.assertEqual(row[0], None)
            self.assertEqual(row[1], 2)
            self.assertEqual(row[2], None)
            del cursor

    async def test_conpy62(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            cur = con.cursor()
            query = "select round(.75 * (? / 3), 2) as val"
            await cur.execute(query, [5])
            row = await cur.fetchone()
            self.assertEqual(row[0], Decimal(1.25))
            del cur

    async def test_conpy67(self):
         async with await mariadb.AsyncConnection.connect(**conf()) as con:
            async with con.cursor(buffered=False) as cur:                
                await cur.execute("SELECT 1")
                self.assertEqual(cur.rowcount, 0)
            async with con.cursor() as cur:
                await cur.execute("SELECT 1", buffered=False)
                self.assertEqual(cur.rowcount, 0)

            async with con.cursor() as cur:
                await cur.execute("CREATE TEMPORARY TABLE test_conpy67 (a int)")
                await cur.execute("SELECT * from test_conpy67")
                self.assertEqual(cur.rowcount, 0)
                await cur.fetchall()
                self.assertEqual(cur.rowcount, 0)

    async def test_negative_numbers(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            cur = con.cursor()
            await cur.execute("drop table if exists t1")
            await cur.execute("create table t1(a tinyint, b int, c bigint)")
            await cur.execute("insert into t1 values (?,?,?)", (-1, -300, -2147483649))
            await cur.execute("select a, b, c FROM t1")
            row = await cur.fetchone()
            self.assertEqual(row[0], -1)
            self.assertEqual(row[1], -300)
            self.assertEqual(row[2], -2147483649)
            del cur

    async def test_none_val(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            cur = con.cursor()
            await cur.execute("CREATE TEMPORARY TABLE t1 (a int)")
            vals = [(1,), (2,), (4,), (None,), (3,)]
            await cur.executemany("INSERT INTO t1 VALUES (?)", vals)
            await cur.execute("select a from t1 order by a")
            rows = await cur.fetchall()
            self.assertEqual(rows[0][0], None)
            del cur

    async def test_conpy81(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            cur = con.cursor()
            await cur.execute("CREATE TEMPORARY TABLE t1 (a int)")
            await cur.execute("INSERT INTO t1 VALUES(1)")
            await cur.execute("SELECT a FROM t1")
            row = await cur.fetchone()
            self.assertEqual(row[0], 1)
            await cur.execute("SELECT a FROM t1 WHERE 1=?", (1,))
            row = await cur.fetchone()
            self.assertEqual(row[0], 1)
            del cur

    async def test_conpy94(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            cur = con.cursor()
            a = foo(2)
            await cur.execute("SELECT ?", (a,))
            row = await cur.fetchone()
            self.assertEqual(row[0], 2)
            del cur

    async def test_conpy98(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            cursor = con.cursor()
            await cursor.execute("SELECT CAST('foo' AS BINARY) AS anon_1")
            row = await cursor.fetchone()
            self.assertEqual(row[0], b'foo')
            del cursor

    async def test_conpy68(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            if con.server_version < 100207:
                self.skipTest("Not supported in versions < 10.2.7")
            cursor = con.cursor()
            await cursor.execute("CREATE TEMPORARY TABLE t1 (a JSON)")
            content = {'a': 'aaa', 'b': 'bbb', 'c': 123}
            await cursor.execute("INSERT INTO t1 VALUES(?)", (json.dumps(content),))
            await cursor.execute("SELECT a FROM t1")
            row = await cursor.fetchone()
            self.assertEqual(row[0], json.dumps(content))
            del cursor

    async def test_conpy123(self):
        async with await mariadb.AsyncConnection.connect(**{**conf(), **{"client_flag": CLIENT.MULTI_STATEMENTS}}) as con:
            cursor1 = con.cursor()
            await cursor1.execute("SELECT 1; SELECT 2")
            await cursor1.close()
            cursor2 = con.cursor()
            await cursor2.execute("SELECT 1")
            row = await cursor2.fetchone()
            self.assertEqual(row[0], 1)
            await cursor2.close()

    async def test_conpy103(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as con:
            cursor = con.cursor()
            await cursor.execute("CREATE TEMPORARY TABLE t1 (a decimal(10,2))")
            await cursor.executemany("INSERT INTO t1 VALUES (?)", [[decimal.Decimal(1)]])
            await cursor.execute("SELECT a FROM t1")
            row = await cursor.fetchone()
            self.assertEqual(row[0], decimal.Decimal(1))
            del cursor

    async def test_conpy129(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as conn:
            server_version = conn.server_version
            major = int(server_version / 10000)
            minor = int((server_version % 10000) / 100)
            patch = server_version % 100
            self.assertEqual(conn.server_version_info, (major, minor, patch))
            self.assertEqual(conn.get_server_version(), (major, minor, patch))

    async def test_conpy167(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as conn:
            cursor = conn.cursor()

            await cursor.execute("CREATE TEMPORARY table t1 ("
                           "a int not NULL auto_increment primary key, b int)")
            await cursor.execute("INSERT INTO t1 VALUES (NULL, ?)", (1, ))
            self.assertEqual(cursor.rowcount, 1)
            await cursor.executemany("INSERT INTO t1 VALUES (NULL, ?)", [(2, ), (3,)])
            self.assertEqual(cursor.rowcount, 2)
            del cursor

    async def test_conpy168(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as conn:
            cursor = conn.cursor()
            x = os.urandom(32)
            await cursor.execute("SELECT cast(? as binary) as a", (x,))
            row = await cursor.fetchone()
            self.assertEqual(row[0], x)
            del cursor

    async def test_conpy133(self):
        if is_mysql():
            self.skipTest("Skip (MySQL)")
        async with await mariadb.AsyncConnection.connect(**conf()) as conn:

            cursor = conn.cursor()
            await cursor.execute("SELECT /*! ? */", (1,))
            row = await cursor.fetchone()
            self.assertEqual(row[0], 1)
            del cursor

            cursor = conn.cursor()
            await cursor.execute("SELECT /*M! ? */", (1,))
            row = await cursor.fetchone()
            self.assertEqual(row[0], 1)
            del cursor

            cursor = conn.cursor()
            await cursor.execute("SELECT /*M!50601 ? */", (1,))
            row = await cursor.fetchone()
            self.assertEqual(row[0], 1)
            del cursor

            cursor = conn.cursor()
            await cursor.execute("SELECT /*!40301 ? */", (1,))
            row = await cursor.fetchone()
            self.assertEqual(row[0], 1)
            del cursor

            async with conn.cursor() as cursor:
                try:
                    await cursor.execute("SELECT /*!50701 ? */", (1,))
                except mariadb.ProgrammingError as e:
                    pass

            async with conn.cursor() as cursor:
                try:
                    await cursor.execute("SELECT /*!250701 ? */", (1,))
                except mariadb.ProgrammingError as e:
                    pass

    async def check_closed(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as conn:
            cursor1 = conn.cursor()
            cursor2 = conn.cursor()
            await cursor1.close()

            try:
                await cursor1.execute("select 1")
            except (mariadb.ProgrammingError):
                pass
            del cursor1

            await conn.close()
            try:
                await cursor2.execute("select 1")
            except (mariadb.ProgrammingError):
                pass
            del cursor2

    async def test_conpy194(self):
        if is_mysql():
            self.skipTest("Skip (MySQL)")

        if (self.connection.server_version < 105000):
            self.skipTest("Insert returning requires MariaDB >= 10.5")

        async with await mariadb.AsyncConnection.connect(**conf()) as conn:
            cursor = conn.cursor()
            await cursor.execute("create temporary table t1 "
                           "(a int not null auto_increment primary key,"
                           "b varchar(10))")

            data = [(1, ), (2, ), (3, )]

            await cursor.executemany("insert into t1 values (?, 'foo') returning a",
                               data)
            rows = await cursor.fetchall()
            self.assertEqual(rows, data)

            await cursor.executemany("delete from t1 where a=? returning a", data)
            rows = await cursor.fetchall()
            self.assertEqual(rows, data)

            await cursor.execute("select a from t1")
            rows = await cursor.fetchall()
            self.assertEqual(rows, [])

            data = [(1, "foo"), (2, "bar"), (3, "hello")]
            await cursor.executemany("insert into t1 values (?,?) returning a,b", data)
            rows = await cursor.fetchall()
            self.assertEqual(rows, data)

            await cursor.executemany("replace into t1 values (?,?) returning a,b",
                               [(1, "xyz")])
            rows = await cursor.fetchall()
            self.assertEqual(rows, [(1, "xyz")])

            del cursor

    async def test_conpy178(self):
        if os.environ.get('RUN_LONG_TEST') != '1':
            self.skipTest("Skipping long-running test. Set RUN_LONG_TEST=1 to run.")            
        async with await mariadb.AsyncConnection.connect(**conf()) as conn:
            cursor = conn.cursor()
            await cursor.execute("DROP PROCEDURE IF EXISTS p2")
            await cursor.execute("CREATE PROCEDURE p2(IN s1 VARCHAR(20), "
                           "IN s2 VARCHAR(20), OUT o1 VARCHAR(40) )\n"
                           "BEGIN\nSET o1:=CAST(CONCAT(s1,s2) AS "
                           "char CHARACTER SET utf8mb4);\nEND")

            for i in range(0, 500):
                await cursor.callproc("p2", ("foo", "bar", 1))
                row = await cursor.fetchone()
                self.assertEqual(row[0], b"foobar" if is_mysql() else "foobar")

    async def test_conpy205(self):
        if is_native():
            self.skipTest("Native only support QMARK")
        async with await mariadb.AsyncConnection.connect(**conf()) as conn:
            cursor = conn.cursor()

            await cursor.execute("select %(name)s", {"name": "Marc"})
            row = await cursor.fetchone()
            self.assertEqual(row[0], "Marc")

            await cursor.execute("select %(name)s", {"name": "Marc",
                                               "noname": "unknown"})
            row = await cursor.fetchone()
            self.assertEqual(row[0], "Marc")

            try:
                await cursor.execute("select ?", {"noname": "unknown"})
            except (mariadb.ProgrammingError):
                pass

            try:
                await cursor.execute("select %(name)s", (1,))
            except (mariadb.ProgrammingError):
                pass

            try:
                await cursor.execute("select %(name)s", {"noname": "unknown"})
            except (mariadb.ProgrammingError):
                pass

            try:
                await cursor.execute("select ?")
            except (mariadb.ProgrammingError):
                pass

            try:
                await cursor.execute("select ?,?,?", (1, 2))
            except (mariadb.ProgrammingError):
                pass

            try:
                await cursor.execute("select ?,?,?", (1, 2, 3, 4))
            except (mariadb.ProgrammingError):
                pass

            await cursor.close()

    async def test_conpy203(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as conn:
            async with conn.cursor() as cursor:
                try:
                    await cursor.execute("SELECT")
                except mariadb.ProgrammingError as err:
                    self.assertEqual(err.errno, ERR.ER_PARSE_ERROR)

    async def test_unicode_parsing(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as conn:
            cursor = conn.cursor()

            await cursor.execute("create temporary table Unitéble2 ( 測試 int, méil int)")
            await cursor.execute("insert into Unitéble2 values (?, ?)", (1, 2))
            self.assertEqual(cursor.rowcount, 1)
            await cursor.execute("SELECT `Unitéble2`.`測試` AS `Unitéble2_測試`,"
                           " `Unitéble2`.`méil` AS `Unitéble2_méil` FROM "
                           "`Unitéble2` WHERE ? = `Unitéble2`.`測試`", (1, ))
            await cursor.fetchall()
            self.assertEqual(cursor.rowcount, 1)
            del cursor

    async def test_unicode_parsing_named(self):
        if is_native():
            self.skipTest("Skip (Native doesn't support named parameters)")
        async with await mariadb.AsyncConnection.connect(**conf()) as conn:
            cursor = conn.cursor()

            await cursor.execute("create temporary table Unitéble2 ( 測試 int, méil int)")
            await cursor.execute("insert into Unitéble2 values (%(測試)s, %(méil)s)",
                           {"測試": 1, "méil": 2})
            self.assertEqual(cursor.rowcount, 1)
            await cursor.execute("SELECT `Unitéble2`.`測試` AS `Unitéble2_測試`,"
                           " `Unitéble2`.`méil` AS `Unitéble2_méil` FROM "
                           "`Unitéble2` WHERE ? = `Unitéble2`.`測試`", (1, ))
            await cursor.fetchall()
            self.assertEqual(cursor.rowcount, 1)
            del cursor

    async def test_conpy209(self):
        if is_native():
            self.skipTest("Skip (Native)")

        async with await mariadb.AsyncConnection.connect(**conf()) as conn:
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
            await cursor.execute(sql, data)
            self.assertEqual(transformed, cursor._transformed_statement)
            del cursor

    async def test_conpy277(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as conn:
            cursor = conn.cursor()
            await cursor.execute("SET session sql_mode='TRADITIONAL,ANSI_QUOTES,ONLY_FULL_GROUP_BY,PIPES_AS_CONCAT'")
            await cursor.execute('select ? as x', ('hi',))
            row= await cursor.fetchone()
            self.assertEqual(row[0], 'hi')
            await cursor.close()

    async def test_conpy213(self):
        conversions = {**{FIELD_TYPE.NEWDECIMAL: float}}
        async with await mariadb.AsyncConnection.connect(**{**conf(), **{"converter": conversions}}) as conn:
            cursor = conn.cursor()
            await cursor.execute("SELECT 1.1")
            rows = await cursor.fetchall()
            self.assertEqual(rows[0][0], 1.1)
            await cursor.execute("SELECT 1.1")
            row = await cursor.fetchone()
            self.assertEqual(row[0], 1.1)
            del cursor

    async def test_conpy218(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as conn:
            cursor = conn.cursor()
            await cursor.execute("SELECT 1",  None)
            row = await cursor.fetchone()
            self.assertEqual(row[0], 1)
            await cursor.execute("SELECT 2",  ())
            row = await cursor.fetchone()
            self.assertEqual(row[0], 2)
            await cursor.execute("SELECT 3",  [])
            row = await cursor.fetchone()
            self.assertEqual(row[0], 3)
            await cursor.execute("SELECT 4",  {})
            row = await cursor.fetchone()
            self.assertEqual(row[0], 4)
            del cursor

    async def test_conpy222(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as conn:
            cursor = conn.cursor()
            await cursor.close()
            del cursor

            cursor = conn.cursor()
            del cursor
            try:
                await cursor.close()   # noqa: F821
            except Exception:
                pass

    async def test_conpy_224(self):

        if is_maxscale():
            self.skipTest("MAXSCALE doesn't support BULK yet")

        cursor = self.connection.cursor()

        await cursor.execute("CREATE TEMPORARY TABLE test_inserttuple ("
                       "id int, name varchar(64), "
                       "city varchar(64))")

        params = ((1, u"Jack", u"Boston"),
                  (2, u"Martin", u"Ohio"),
                  (3, u"James", u"Washington"),
                  (4, u"Rasmus", u"Helsinki"),
                  (5, u"Andrey", u"Sofia"))

        await cursor.executemany("INSERT INTO test_inserttuple VALUES (?,?,?)",
                           params)

        await cursor.executemany("INSERT INTO test_inserttuple VALUES (?,?,?)",
                           params)

        cursor = self.connection.cursor()

        await cursor.execute("SELECT name FROM test_inserttuple ORDER BY id DESC")

        row = await cursor.fetchone()

        self.assertEqual("Andrey", row[0])

        del cursor

    async def test_conpy225(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as conn:
            cursor = conn.cursor()

            await cursor.execute("CREATE TEMPORARY TABLE x01 (a int, b int)")
            params = ((1, 2), (2, 3), (3, 4), (4, 5))

            await cursor.executemany("INSERT INTO x01 VALUES (?,?)", params)
            self.assertEqual(cursor.rowcount, 4)
            if (not is_mysql()):
                self.assertEqual(cursor.affected_rows, 4)

            await cursor.execute("UPDATE x01 SET a=1 WHERE a=1")
            self.assertEqual(cursor.rowcount, 0)
            self.assertEqual(cursor.affected_rows, 0)

            await cursor.execute("UPDATE x01 SET a=1 WHERE a=4")
            self.assertEqual(cursor.affected_rows, 1)
            self.assertEqual(cursor.rowcount, 1)
            del cursor

    async def test_conpy270(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as connection:
            x = connection.server_version_info
            if x < (10, 7, 0) or is_mysql():
                self.skipTest("Skip (MySQL and MariaDB < 10.7)")

            cursor = connection.cursor()

            await cursor.execute("drop table if exists t1")
            await cursor.execute("create table t1 (a uuid)")
            await cursor.execute("insert into t1 values (uuid())")

            # text protocol
            await cursor.execute("select a from t1")
            self.assertEqual(cursor.description[0][1], mariadb.STRING);
            await cursor.fetchall()

            # binary protcol
            await cursor.execute("select a from t1 WHERE 1=?", (1,))
            self.assertEqual(cursor.description[0][1], mariadb.STRING);
            await cursor.fetchall()

            await cursor.close()
    
    async def test_conpy269(self):
        if is_mysql():
            self.skipTest("Skip (MySQL)")
        async with await mariadb.AsyncConnection.connect(**conf()) as connection:
            cursor = connection.cursor()
            await cursor.execute("SELECT 1 UNION SELECT 2")
            self.assertEqual(cursor.rowcount, 2)
            await cursor.close()
            self.assertEqual(cursor.rowcount, -1)

    async def test_conpy258(self):
        async with await mariadb.AsyncConnection.connect(**conf()) as connection:
            cursor = connection.cursor()
            await cursor.execute("CREATE TEMPORARY TABLE t1 (a INT(9) ZEROFILL)")
            await cursor.execute("INSERT INTO t1 VALUES(123)")
            await cursor.execute("SELECT a FROM t1")
            row = await cursor.fetchone()
            self.assertEqual(row[0], 123)
            await cursor.close()
            cursor = connection.cursor(binary=True)
            await cursor.execute("SELECT a FROM t1")
            row = await cursor.fetchone()
            self.assertEqual(row[0], 123)
            await cursor.close()

    async def test_conpy291(self):
        if is_mysql:
            self.skipTest("Skip (MySQL doesn't support batch/indicators)")
        async with await mariadb.AsyncConnection.connect(**conf()) as connection:
            cursor = connection.cursor()

            await cursor.execute("DROP TABLE IF EXISTS t1")
            await cursor.execute("CREATE TABLE t1 (a int, b int, c varchar(100), d int)")

            data= [(1, INDICATOR.NULL, "foo", INDICATOR.NULL),
                   (2, 3, "foo", 5)]
            await cursor.executemany("INSERT INTO t1 VALUES (?,?,?,?)", data)
            self.assertEqual(cursor.rowcount, 2)
            await cursor.execute("DROP TABLE IF EXISTS t1")
            del cursor

    async def test_conpy276(self):

        async with await mariadb.AsyncConnection.connect(**conf()) as conn:
            cursor = conn.cursor()

            await cursor.execute("SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4")

            row= await cursor.fetchone()
            self.assertEqual(row[0], 1)
            rows= await cursor.fetchall()
            self.assertEqual(rows, [(2,),(3,),(4,)])
            await cursor.scroll(0, "absolute")
            row= await cursor.fetchone()
            self.assertEqual(row[0], 1)
            self.assertEqual(cursor.rowcount, 4)
            del cursor

    async def test_conpy289(self):
        if is_mysql:
            self.skipTest("Skip (MySQL doesn't support batch)")
        async with await mariadb.AsyncConnection.connect(**conf()) as conn:
            cursor= conn.cursor()
            await cursor.execute("CREATE OR REPLACE TABLE t289 (a bigint unsigned,"\
                           "b bigint unsigned, c bigint unsigned,"\
                           "d bigint unsigned)")

            data= [(0, 9232974212090577672, 11529232914765115761, 58),
                   (0, 13837380911034793984, 11529233872889843812, 0),
                   (0, 0, 2351636844950589488, 9999)]

            await cursor.executemany("insert into t289 values (?,?,?,?)", data)

            await cursor.execute("SELECT * FROM t289")
            rows= await cursor.fetchall()
            self.assertEqual(rows, data)

    async def test_conpy91(self):
        if is_native():
            self.skipTest("Native only support QMARK")

        async with await mariadb.AsyncConnection.connect(**conf()) as connection:
            with connection.cursor() as cursor:
                for parameter_type in (int, decimal.Decimal):
                    with self.subTest(parameter_type=parameter_type):
                        with self.subTest(parameter_count=1):
                            with self.subTest(parameter_style='?'):
                                await cursor.execute('select ?',
                                               [parameter_type(1)])
                                [[value]] = await cursor.fetchall()
                                self.assertEqual(value, 1)
                            with self.subTest(parameter_style='%s'):
                                await cursor.execute('select %s',
                                               [parameter_type(1)])
                                [[value]] = await cursor.fetchall()
                                self.assertEqual(value, 1)
                            with self.subTest(parameter_style='%(name)s'):
                                await cursor.execute('select %(value)s',
                                               dict(value=parameter_type(1)))
                                [[value]] = await cursor.fetchall()
                                self.assertEqual(value, 1)
                        with self.subTest(parameter_count=2):
                            with self.subTest(parameter_style='?'):
                                await cursor.execute('select ?, ?',
                                               [parameter_type(1), 1])
                                [[value, _]] = await cursor.fetchall()
                                self.assertEqual(value, 1)
                            with self.subTest(parameter_style='%s'):
                                await cursor.execute('select %s, %s',
                                               [parameter_type(1), 1])
                                [[value, _]] = await cursor.fetchall()
                                self.assertEqual(value, 1)
                            with self.subTest(parameter_style='%(name)s'):
                                await cursor.execute('select %(value)s, %(dummy)s',
                                               dict(value=parameter_type(1),
                                                    dummy=1))
                                [[value, _]] = await cursor.fetchall()
                                self.assertEqual(value, 1)

    async def test_fetchone_states(self):
        """Test fetchone behavior in different cursor states"""
        cursor = self.connection.cursor()
        
        with self.assertRaises((mariadb.ProgrammingError, RuntimeError)):
            await cursor.fetchone()
        
        # Test 2: fetchone after closing cursor should raise an error
        await cursor.execute("SELECT 1")
        await cursor.fetchone()  # Consume the result
        await cursor.close()
        
        with self.assertRaises((mariadb.ProgrammingError, RuntimeError)):
            await cursor.fetchone()
        
        # Test 3: fetchone after closing connection should raise an error
        cursor2 = self.connection.cursor()
        await cursor2.execute("SELECT 1")
        await cursor2.fetchone()  # Consume the result
        
        # Create a new connection to close
        conn = await mariadb.AsyncConnection.connect(**conf())
        cursor3 = conn.cursor()
        await cursor3.execute("SELECT 1")
        await cursor3.fetchone()  # Consume the result
        
        await cursor3.close()
        
        cursor4 = conn.cursor()
        await cursor4.execute("SELECT 1")
        cursor5 = conn.cursor(buffered=False)
        await cursor5.execute("SELECT 1")

        await conn.close()

        await cursor4.fetchone()
        with self.assertRaises((mariadb.ProgrammingError, RuntimeError)):
            await cursor5.fetchone()

    def test_cursor_class(self):
        """Test cursor class"""
        if not is_native():
            self.skipTest("test only for Native")
        cursor = self.connection.cursor(cursor_class=mariadb.AsyncCursor)
        self.assertIsInstance(cursor, mariadb.AsyncCursor)

        cursor = self.connection.cursor(cursor_class=mariadb.AsyncCursor, buffered=False)
        self.assertIsInstance(cursor, mariadb.AsyncCursor)

    async def test_streaming_noconnection(self):
        conn = await mariadb.AsyncConnection.connect(**conf())
        cursor = conn.cursor(buffered=False)
        await cursor.execute("SELECT 1")
        
        # explicitly close connection before cursor
        await conn.close()
        await cursor.close()

    async def test_async_cursor_sync_iteration_error(self):
        """Test that sync iteration raises TypeError for AsyncCursor"""
        cursor = self.connection.cursor()
        await cursor.execute("SELECT 1 UNION SELECT 2 UNION SELECT 3")
        
        # Test __iter__ raises TypeError
        with self.assertRaises(TypeError) as cm:
            iter(cursor)
        self.assertIn("async for", str(cm.exception).lower())
        
        # Test __next__ raises TypeError
        with self.assertRaises(TypeError) as cm:
            next(cursor)
        self.assertIn("async for", str(cm.exception).lower())
        
        await cursor.close()

    async def test_async_cursor_sync_context_manager_error(self):
        """Test that sync context manager raises TypeError for AsyncCursor"""
        cursor = self.connection.cursor()
        
        # Test __enter__ raises TypeError
        with self.assertRaises(TypeError) as cm:
            cursor.__enter__()
        self.assertIn("async with", str(cm.exception).lower())
        
        # Test __exit__ raises TypeError
        with self.assertRaises(TypeError) as cm:
            cursor.__exit__(None, None, None)
        self.assertIn("async with", str(cm.exception).lower())
        
        await cursor.close()

    async def test_async_cursor_with_statement_error(self):
        """Test that using 'with' statement raises TypeError for AsyncCursor"""
        cursor = self.connection.cursor()
        
        # Attempting to use sync 'with' should raise TypeError
        with self.assertRaises(TypeError) as cm:
            with cursor:
                pass
        self.assertIn("async with", str(cm.exception).lower())
        
        await cursor.close()

    async def test_async_cursor_for_loop_error(self):
        """Test that using 'for' loop raises TypeError for AsyncCursor"""
        cursor = self.connection.cursor()
        await cursor.execute("SELECT 1 UNION SELECT 2 UNION SELECT 3")
        
        # Attempting to use sync 'for' should raise TypeError
        with self.assertRaises(TypeError) as cm:
            for row in cursor:
                pass
        self.assertIn("async for", str(cm.exception).lower())
        
        await cursor.close()


    async def test_xfield_types_binary(self):
        """Test field types with binary=True cursor"""
        if is_maxscale():
            self.skipTest("Test doesn't work with maxscale")
        cursor = self.connection.cursor(binary=True)
        fieldinfo = mariadb.fieldinfo()
        await cursor.execute("CREATE TEMPORARY TABLE test_xfield_types_binary ("
                       "a tinyint not null auto_increment primary "
                       "key, b smallint, c int, d bigint, e float, "
                       "f decimal, g double, h char(10), i varchar(255), "
                       "j blob, k json, index(b))")
        info = cursor.description
        self.assertEqual(info, None)
        await cursor.execute("SELECT * FROM test_xfield_types_binary WHERE 1=?", (1,))
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

    async def test_ext_field_types_binary(self):
        """Test extended field types with binary=True cursor"""
        x = self.connection.server_version_info
        if x < (10, 10, 0) or is_mysql():
            self.skipTest("Skip (MySQL and MariaDB < 10.10)")
        cursor = self.connection.cursor(binary=True)
        
        # Test all extended field types including all geometry types
        await cursor.execute("CREATE TEMPORARY TABLE t1_binary ("
                       "a json, "
                       "b uuid, "
                       "c inet4, "
                       "d inet6, "
                       "e point, "
                       "f multipoint, "
                       "g linestring, "
                       "h multilinestring, "
                       "i polygon, "
                       "j multipolygon, "
                       "k geometrycollection)")
        await cursor.execute("SELECT a,b,c,d,e,f,g,h,i,j,k FROM t1_binary WHERE 1=?", (1,))
        metadata = cursor.metadata
        
        # JSON
        self.assertEqual(metadata["ext_type_or_format"][0], EXT_FIELD_TYPE.JSON)
        self.assertEqual(metadata["type"][0], FIELD_TYPE.BLOB)
        
        # UUID
        self.assertEqual(metadata["ext_type_or_format"][1], EXT_FIELD_TYPE.UUID)
        self.assertEqual(metadata["type"][1], FIELD_TYPE.STRING)
        
        # INET4
        self.assertEqual(metadata["ext_type_or_format"][2], EXT_FIELD_TYPE.INET4)
        self.assertEqual(metadata["type"][2], FIELD_TYPE.STRING)
        
        # INET6
        self.assertEqual(metadata["ext_type_or_format"][3], EXT_FIELD_TYPE.INET6)
        self.assertEqual(metadata["type"][3], FIELD_TYPE.STRING)
        
        # POINT
        self.assertEqual(metadata["ext_type_or_format"][4], EXT_FIELD_TYPE.POINT)
        self.assertEqual(metadata["type"][4], FIELD_TYPE.GEOMETRY)
        
        # MULTIPOINT
        self.assertEqual(metadata["ext_type_or_format"][5], EXT_FIELD_TYPE.MULTIPOINT)
        self.assertEqual(metadata["type"][5], FIELD_TYPE.GEOMETRY)
        
        # LINESTRING
        self.assertEqual(metadata["ext_type_or_format"][6], EXT_FIELD_TYPE.LINESTRING)
        self.assertEqual(metadata["type"][6], FIELD_TYPE.GEOMETRY)
        
        # MULTILINESTRING
        self.assertEqual(metadata["ext_type_or_format"][7], EXT_FIELD_TYPE.MULTILINESTRING)
        self.assertEqual(metadata["type"][7], FIELD_TYPE.GEOMETRY)
        
        # POLYGON
        self.assertEqual(metadata["ext_type_or_format"][8], EXT_FIELD_TYPE.POLYGON)
        self.assertEqual(metadata["type"][8], FIELD_TYPE.GEOMETRY)
        
        # MULTIPOLYGON
        self.assertEqual(metadata["ext_type_or_format"][9], EXT_FIELD_TYPE.MULTIPOLYGON)
        self.assertEqual(metadata["type"][9], FIELD_TYPE.GEOMETRY)
        
        # GEOMETRYCOLLECTION
        self.assertEqual(metadata["ext_type_or_format"][10], EXT_FIELD_TYPE.GEOMETRYCOLLECTION)
        self.assertEqual(metadata["type"][10], FIELD_TYPE.GEOMETRY)

        await cursor.close()

    async def test_conpy270_binary(self):
        """Test UUID field type with binary=True cursor"""
        async with await mariadb.AsyncConnection.connect(**conf()) as connection:
            x = connection.server_version_info
            if x < (10, 7, 0) or is_mysql():
                self.skipTest("Skip (MySQL and MariaDB < 10.7)")

            cursor = connection.cursor(binary=True)

            await cursor.execute("drop table if exists t1_binary_270")
            await cursor.execute("create table t1_binary_270 (a uuid)")
            await cursor.execute("insert into t1_binary_270 values (uuid())")

            # binary protocol with parameters
            await cursor.execute("select a from t1_binary_270 WHERE 1=?", (1,))
            self.assertEqual(cursor.description[0][1], mariadb.STRING)
            await cursor.fetchall()

            await cursor.execute("drop table if exists t1_binary_270")
            await cursor.close()
        
if __name__ == '__main__':
    unittest.main()
