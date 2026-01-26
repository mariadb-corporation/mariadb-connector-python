#\!/usr/bin/env python
# -*- coding: utf-8 -*-

''' Python DB API 2.0 driver compliance unit test suite - Async version.

    This software is Public Domain and may be used without restrictions.
    
    Async adaptation for MariaDB Connector/Python AsyncConnection
'''

__rcs_id__ = '$Id$'
__version__ = '$Revision$'[11:-2]
__author__ = 'Stuart Bishop <zen@shangri-la.dropbear.id.au>'

import time
import unittest

import mariadb
import datetime

from ..conftest import get_test_config as conf
from ..base_test import is_maxscale

class AsyncDatabaseAPI20Test(unittest.IsolatedAsyncioTestCase):
    ''' Test a database driver for DB API 2.0 compatibility - Async version.
        Adapted from the standard DB-API 2.0 compliance test suite.
    '''

    driver = mariadb
    connect_args = ()
    connect_kw_args = conf()
    table_prefix = 'dbapi20test_'

    ddl1 = 'create table %sbooze (name varchar(20))' % table_prefix
    ddl2 = 'create table %sbarflys (name varchar(20))' % table_prefix
    xddl1 = 'drop table %sbooze' % table_prefix
    xddl2 = 'drop table %sbarflys' % table_prefix

    lowerfunc = 'lower'

    async def executeDDL1(self, cursor):
        await cursor.execute(self.ddl1)

    async def executeDDL2(self, cursor):
        await cursor.execute(self.ddl2)

    async def asyncSetUp(self):
        pass

    async def asyncTearDown(self):
        con = await self._connect()
        try:
            cur = con.cursor()
            for ddl in (self.xddl1, self.xddl2):
                try:
                    await cur.execute(ddl)
                    await con.commit()
                except self.driver.Error:
                    pass
        finally:
            await cur.close()
            await con.close()

    async def _connect(self):
        try:
            return await self.driver.AsyncConnection.connect(**self.connect_kw_args)
        except AttributeError:
            self.fail("No AsyncConnection.connect method found")

    async def test_connect(self):
        con = await self._connect()
        await con.close()

    async def test_apilevel(self):
        try:
            apilevel = self.driver.apilevel
            self.assertEqual(apilevel, '2.0')
        except AttributeError:
            self.fail("Driver doesn't define apilevel")

    async def test_threadsafety(self):
        try:
            threadsafety = self.driver.threadsafety
            self.assertTrue(threadsafety in (0, 1, 2, 3))
        except AttributeError:
            self.fail("Driver doesn't define threadsafety")

    async def test_paramstyle(self):
        try:
            paramstyle = self.driver.paramstyle
            self.assertTrue(paramstyle in (
                'qmark', 'numeric', 'named', 'format', 'pyformat'
            ))
        except AttributeError:
            self.fail("Driver doesn't define paramstyle")

    async def test_Exceptions(self):
        self.assertTrue(issubclass(self.driver.Warning, Exception))
        self.assertTrue(issubclass(self.driver.Error, Exception))
        self.assertTrue(issubclass(self.driver.InterfaceError, self.driver.Error))
        self.assertTrue(issubclass(self.driver.DatabaseError, self.driver.Error))
        self.assertTrue(issubclass(self.driver.OperationalError, self.driver.Error))
        self.assertTrue(issubclass(self.driver.IntegrityError, self.driver.Error))
        self.assertTrue(issubclass(self.driver.InternalError, self.driver.Error))
        self.assertTrue(issubclass(self.driver.ProgrammingError, self.driver.Error))
        self.assertTrue(issubclass(self.driver.NotSupportedError, self.driver.Error))

    async def test_ExceptionsAsConnectionAttributes(self):
        con = await self._connect()
        drv = self.driver
        self.assertTrue(con.Warning is drv.Warning)
        self.assertTrue(con.Error is drv.Error)
        self.assertTrue(con.InterfaceError is drv.InterfaceError)
        self.assertTrue(con.DatabaseError is drv.DatabaseError)
        self.assertTrue(con.OperationalError is drv.OperationalError)
        self.assertTrue(con.IntegrityError is drv.IntegrityError)
        self.assertTrue(con.InternalError is drv.InternalError)
        self.assertTrue(con.ProgrammingError is drv.ProgrammingError)
        self.assertTrue(con.NotSupportedError is drv.NotSupportedError)
        await con.close()

    async def test_commit(self):
        con = await self._connect()
        try:
            await con.commit()
        finally:
            await con.close()

    async def test_rollback(self):
        con = await self._connect()
        if hasattr(con, 'rollback'):
            try:
                await con.rollback()
            except self.driver.NotSupportedError:
                pass
        await con.close()

    async def test_cursor(self):
        con = await self._connect()
        try:
            cur = con.cursor()
        finally:
            await cur.close()
            await con.close()

    async def test_cursor_isolation(self):
        con = await self._connect()
        try:
            cur1 = con.cursor()
            cur2 = con.cursor()
            await self.executeDDL1(cur1)
            await cur1.execute("insert into %sbooze values ('Victoria Bitter')" % self.table_prefix)
            await cur2.execute("select name from %sbooze" % self.table_prefix)
            booze = await cur2.fetchall()
            self.assertEqual(len(booze), 1)
            self.assertEqual(len(booze[0]), 1)
            self.assertEqual(booze[0][0], 'Victoria Bitter')
        finally:
            await cur1.close()
            await cur2.close()
            await con.close()

    async def test_description(self):
        con = await self._connect()
        try:
            cur = con.cursor()
            await self.executeDDL1(cur)
            self.assertEqual(cur.description, None)
            await cur.execute('select name from %sbooze' % self.table_prefix)
            self.assertEqual(len(cur.description), 1)
            self.assertEqual(len(cur.description[0]), 11)
            self.assertEqual(cur.description[0][0].lower(), 'name')
            self.assertEqual(cur.description[0][8].lower(), 'dbapi20test_booze')
            self.assertEqual(cur.description[0][9].lower(), 'name')
            self.assertEqual(cur.description[0][10].lower(), 'dbapi20test_booze')
            self.assertEqual(cur.description[0][1], self.driver.STRING)
            await self.executeDDL2(cur)
            self.assertEqual(cur.description, None)
        finally:
            await cur.close()
            await con.close()

    async def test_rowcount(self):
        con = await self._connect()
        try:
            cur = con.cursor(buffered=True)
            await self.executeDDL1(cur)
            self.assertEqual(cur.rowcount, 0)
            await cur.execute("insert into %sbooze values ('Victoria Bitter')" % self.table_prefix)
            self.assertEqual(cur.rowcount, 1)
            await cur.execute("select name from %sbooze" % self.table_prefix)
            self.assertEqual(cur.rowcount, 1)
            await self.executeDDL2(cur)
            self.assertEqual(cur.rowcount, 0)
        finally:
            await cur.close()
            await con.close()

    lower_func = 'lower'

    async def test_close(self):
        con = await self._connect()
        try:
            cur = con.cursor()
        finally:
            await con.close()
        
        with self.assertRaises(self.driver.Error):
            await self.executeDDL1(cur)

        with self.assertRaises(self.driver.Error):
            await con.commit()

        await con.close()

    async def test_execute(self):
        con = await self._connect()
        try:
            cur = con.cursor()
            await self._paraminsert(cur)
        finally:
            await con.close()

    async def _paraminsert(self, cur):
        await self.executeDDL1(cur)
        await cur.execute("insert into %sbooze values ('Victoria Bitter')" % self.table_prefix)
        self.assertTrue(cur.rowcount in (-1, 1))

        if self.driver.paramstyle == 'qmark':
            await cur.execute('insert into %sbooze values (?)' % self.table_prefix, ("Cooper's",))
        elif self.driver.paramstyle == 'numeric':
            await cur.execute('insert into %sbooze values (:1)' % self.table_prefix, ("Cooper's",))
        elif self.driver.paramstyle == 'named':
            await cur.execute('insert into %sbooze values (:beer)' % self.table_prefix, {'beer': "Cooper's"})
        elif self.driver.paramstyle == 'format':
            await cur.execute('insert into %sbooze values (%%s)' % self.table_prefix, ("Cooper's",))
        elif self.driver.paramstyle == 'pyformat':
            await cur.execute('insert into %sbooze values (%%(beer)s)' % self.table_prefix, {'beer': "Cooper's"})
        else:
            self.fail('Invalid paramstyle')
        self.assertTrue(cur.rowcount in (-1, 1))

        await cur.execute('select name from %sbooze' % self.table_prefix)
        res = await cur.fetchall()
        self.assertEqual(len(res), 2)
        beers = [res[0][0], res[1][0]]
        beers.sort()
        self.assertEqual(beers[0], "Cooper's")
        self.assertEqual(beers[1], "Victoria Bitter")

    async def test_executemany(self):
        if is_maxscale():
            self.skipTest("MAXSCALE doesn't support BULK yet")
        con = await self._connect()
        try:
            cur = con.cursor()
            await self.executeDDL1(cur)
            largs = [("Cooper's",), ("Boag's",)]
            margs = [{'beer': "Cooper's"}, {'beer': "Boag's"}]
            if self.driver.paramstyle == 'qmark':
                await cur.executemany('insert into %sbooze values (?)' % self.table_prefix, largs)
            elif self.driver.paramstyle == 'numeric':
                await cur.executemany('insert into %sbooze values (:1)' % self.table_prefix, largs)
            elif self.driver.paramstyle == 'named':
                await cur.executemany('insert into %sbooze values (:beer)' % self.table_prefix, margs)
            elif self.driver.paramstyle == 'format':
                await cur.executemany('insert into %sbooze values (%%s)' % self.table_prefix, largs)
            elif self.driver.paramstyle == 'pyformat':
                await cur.executemany('insert into %sbooze values (%%(beer)s)' % self.table_prefix, margs)
            else:
                self.fail('Unknown paramstyle')
            self.assertTrue(cur.rowcount in (-1, 2))
            await cur.execute('select name from %sbooze' % self.table_prefix)
            res = await cur.fetchall()
            self.assertEqual(len(res), 2)
            beers = [res[0][0], res[1][0]]
            beers.sort()
            self.assertEqual(beers[0], "Boag's")
            self.assertEqual(beers[1], "Cooper's")
        finally:
            await con.close()

    async def test_fetchone(self):
        con = await self._connect()
        try:
            cur = con.cursor(buffered=True)

            with self.assertRaises(self.driver.Error):
                await cur.fetchone()

            await self.executeDDL1(cur)
            with self.assertRaises(self.driver.Error):
                await cur.fetchone()

            await cur.execute('select name from %sbooze' % self.table_prefix)
            self.assertEqual(await cur.fetchone(), None)
            self.assertTrue(cur.rowcount in (-1, 0))

            await cur.execute("insert into %sbooze values ('Victoria Bitter')" % self.table_prefix)
            with self.assertRaises(self.driver.Error):
                await cur.fetchone()

            await cur.execute('select name from %sbooze' % self.table_prefix)
            r = await cur.fetchone()
            self.assertEqual(len(r), 1)
            self.assertEqual(r[0], 'Victoria Bitter')
            self.assertEqual(await cur.fetchone(), None)
            self.assertTrue(cur.rowcount in (-1, 1))
        finally:
            await con.close()

    samples = ['Carlton Cold', 'Carlton Draft', 'Mountain Goat', 'Redback', 'Victoria Bitter', 'XXXX']

    def _populate(self):
        return ["insert into %sbooze values ('%s')" % (self.table_prefix, s) for s in self.samples]

    async def test_fetchmany(self):
        con = await self._connect()
        try:
            cur = con.cursor()

            with self.assertRaises(self.driver.Error):
                await cur.fetchmany(4)

            await self.executeDDL1(cur)
            for sql in self._populate():
                await cur.execute(sql)

            await cur.execute('select name from %sbooze' % self.table_prefix)
            r = await cur.fetchmany()
            self.assertEqual(len(r), 1)
            cur.arraysize = 10
            r = await cur.fetchmany(3)
            self.assertEqual(len(r), 3)
            r = await cur.fetchmany(4)
            self.assertEqual(len(r), 2)
            r = await cur.fetchmany(4)
            self.assertEqual(len(r), 0)
            self.assertTrue(cur.rowcount in (-1, 6))

            cur.arraysize = 4
            await cur.execute('select name from %sbooze' % self.table_prefix)
            r = await cur.fetchmany()
            self.assertEqual(len(r), 4)
            r = await cur.fetchmany()
            self.assertEqual(len(r), 2)
            r = await cur.fetchmany()
            self.assertEqual(len(r), 0)
            self.assertTrue(cur.rowcount in (-1, 6))

            cur.arraysize = 6
            await cur.execute('select name from %sbooze' % self.table_prefix)
            rows = await cur.fetchmany()
            self.assertTrue(cur.rowcount in (-1, 6))
            self.assertEqual(len(rows), 6)
            rows = [r[0] for r in rows]
            rows.sort()

            for i in range(0, 6):
                self.assertEqual(rows[i], self.samples[i])

            rows = await cur.fetchmany()
            self.assertEqual(len(rows), 0)
            self.assertTrue(cur.rowcount in (-1, 6))

            await self.executeDDL2(cur)
            await cur.execute('select name from %sbarflys' % self.table_prefix)
            r = await cur.fetchmany()
            self.assertEqual(len(r), 0)
            self.assertTrue(cur.rowcount in (-1, 0))

        finally:
            await con.close()

    async def test_fetchall(self):
        con = await self._connect()
        try:
            cur = con.cursor()
            with self.assertRaises(self.driver.Error):
                await cur.fetchall()

            await self.executeDDL1(cur)
            for sql in self._populate():
                await cur.execute(sql)

            with self.assertRaises(self.driver.Error):
                await cur.fetchall()

            await cur.execute('select name from %sbooze' % self.table_prefix)
            rows = await cur.fetchall()
            self.assertTrue(cur.rowcount in (-1, len(self.samples)))
            self.assertEqual(len(rows), len(self.samples))
            rows = [r[0] for r in rows]
            rows.sort()
            for i in range(0, len(self.samples)):
                self.assertEqual(rows[i], self.samples[i])
            rows = await cur.fetchall()
            self.assertEqual(len(rows), 0)
            self.assertTrue(cur.rowcount in (-1, len(self.samples)))

            await self.executeDDL2(cur)
            await cur.execute('select name from %sbarflys' % self.table_prefix)
            rows = await cur.fetchall()
            self.assertTrue(cur.rowcount in (-1, 0))
            self.assertEqual(len(rows), 0)

        finally:
            await con.close()

    async def test_mixedfetch(self):
        con = await self._connect()
        try:
            cur = con.cursor()
            await self.executeDDL1(cur)
            for sql in self._populate():
                await cur.execute(sql)

            await cur.execute('select name from %sbooze' % self.table_prefix)
            rows1 = await cur.fetchone()
            rows23 = await cur.fetchmany(2)
            rows4 = await cur.fetchone()
            rows56 = await cur.fetchall()
            self.assertTrue(cur.rowcount in (-1, 6))
            self.assertEqual(len(rows23), 2)
            self.assertEqual(len(rows56), 2)

            rows = [rows1[0]]
            rows.extend([rows23[0][0], rows23[1][0]])
            rows.append(rows4[0])
            rows.extend([rows56[0][0], rows56[1][0]])
            rows.sort()
            for i in range(0, len(self.samples)):
                self.assertEqual(rows[i], self.samples[i])
        finally:
            await con.close()

    async def test_arraysize(self):
        con = await self._connect()
        try:
            cur = con.cursor()
            self.assertTrue(hasattr(cur, 'arraysize'))
        finally:
            await con.close()

    async def test_setinputsizes(self):
        con = await self._connect()
        try:
            cur = con.cursor()
            cur.setinputsizes((25,))
            await self._paraminsert(cur)
        finally:
            await con.close()

    async def test_None(self):
        con = await self._connect()
        try:
            cur = con.cursor()
            await self.executeDDL1(cur)
            await cur.execute('insert into %sbooze values (NULL)' % self.table_prefix)
            await cur.execute('select name from %sbooze' % self.table_prefix)
            r = await cur.fetchall()
            self.assertEqual(len(r), 1)
            self.assertEqual(len(r[0]), 1)
            self.assertEqual(r[0][0], None)
        finally:
            await con.close()

    async def test_Date(self):
        d1 = self.driver.Date(2002, 12, 25)
        self.assertTrue(isinstance(d1, datetime.date))
        d2 = self.driver.DateFromTicks(time.mktime((2002, 12, 25, 0, 0, 0, 0, 0, 0)))
        self.assertEqual(str(d1), str(d2))

    async def test_Time(self):
        t1 = self.driver.Time(13, 45, 30)
        self.assertTrue(isinstance(t1, datetime.time))
        t2 = self.driver.TimeFromTicks(time.mktime((2001, 1, 1, 13, 45, 30, 0, 0, 0)))
        self.assertTrue(isinstance(t2, datetime.time))
        self.assertEqual(str(t1), str(t2))

    async def test_Timestamp(self):
        t1 = self.driver.Timestamp(2002, 12, 25, 13, 45, 30)
        self.assertTrue(isinstance(t1, datetime.datetime))
        t2 = self.driver.TimestampFromTicks(time.mktime((2002, 12, 25, 13, 45, 30, 0, 0, 0)))
        self.assertTrue(isinstance(t2, datetime.datetime))

    async def test_Binary(self):
        b = self.driver.Binary(b'Something')
        self.assertTrue(isinstance(b, bytes))
        b = self.driver.Binary(b'')
        self.assertTrue(isinstance(b, bytes))

    async def test_STRING(self):
        self.assertTrue(hasattr(self.driver, 'STRING'))

    async def test_BINARY(self):
        self.assertTrue(hasattr(self.driver, 'BINARY'))

    async def test_NUMBER(self):
        self.assertTrue(hasattr(self.driver, 'NUMBER'))

    async def test_DATETIME(self):
        self.assertTrue(hasattr(self.driver, 'DATETIME'))

    async def test_ROWID(self):
        self.assertTrue(hasattr(self.driver, 'ROWID'))


if __name__ == '__main__':
    unittest.main()
