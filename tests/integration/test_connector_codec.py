#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""
Connector behaviors verified against a real server (integration).

* ``TestConnectorBehaviors`` -- behavior that must be identical on the pure-Python
  and C-extension clients: repr, the timedelta/TIME and array/VECTOR codecs,
  signed/unsigned/float/bytes/None binary parameters (incl. the unsigned-BIGINT
  and mixed-sign DECIMAL handling of CONPY-353), and BLOB decoding. Running it on
  both implementations guards parity -- it is what surfaced the pure-Python
  unsigned-BIGINT gap.
* ``TestCExtOnly`` -- libmariadb-only connection API (auto_reconnect,
  get_timeout_value, status_callback session tracking); skipped on pure-Python.

Fake-server (no-DB) protocol/codec tests live in
tests/unit/test_fakeserver_behaviors.py.
"""

import array
import datetime
import unittest

import mariadb
from tests.base_test import is_native

from ..conftest import get_test_config as conf


class _SharedConnectorCodecs:
    """Mixin of behaviors that must be identical on both implementations.
    Concrete TestCases provide ``self.conn`` via setUp."""

    def test_connection_repr(self):
        self.assertIsInstance(repr(self.conn), str)

    def test_cursor_repr(self):
        cur = self.conn.cursor()
        self.assertIsInstance(repr(cur), str)
        cur.close()

    def test_timedelta_time_param(self):
        cur = self.conn.cursor(binary=True)
        cur.execute("DROP TABLE IF EXISTS test_c_time")
        cur.execute("CREATE TABLE test_c_time (t TIME)")
        td = datetime.timedelta(hours=2, minutes=30, seconds=15)
        cur.execute("INSERT INTO test_c_time VALUES (?)", (td,))
        cur.execute("SELECT t FROM test_c_time")
        self.assertEqual(cur.fetchone()[0], td)
        cur.execute("DROP TABLE IF EXISTS test_c_time")
        cur.close()

    def test_negative_timedelta_time_param(self):
        cur = self.conn.cursor(binary=True)
        cur.execute("DROP TABLE IF EXISTS test_c_time_neg")
        cur.execute("CREATE TABLE test_c_time_neg (t TIME)")
        td = datetime.timedelta(hours=-1, minutes=-15)
        cur.execute("INSERT INTO test_c_time_neg VALUES (?)", (td,))
        cur.execute("SELECT t FROM test_c_time_neg")
        self.assertEqual(cur.fetchone()[0], td)
        cur.execute("DROP TABLE IF EXISTS test_c_time_neg")
        cur.close()

    def test_vector_param(self):
        cur = self.conn.cursor(binary=True)
        try:
            cur.execute("DROP TABLE IF EXISTS test_c_vec")
            cur.execute("CREATE TABLE test_c_vec (v VECTOR(3))")
        except mariadb.Error:
            cur.close()
            self.skipTest("server has no VECTOR type")
        vec = array.array('f', [1.0, 2.0, 3.0])
        try:
            cur.execute("INSERT INTO test_c_vec VALUES (?)", (vec,))
            cur.execute("SELECT v FROM test_c_vec")
            self.assertIsNotNone(cur.fetchone()[0])
        finally:
            try:
                cur.execute("DROP TABLE IF EXISTS test_c_vec")
            except mariadb.Error:
                pass
            cur.close()

    def test_binary_param_unsigned_bigint(self):
        # LONGLONG values above the signed-64 range must bind unsigned (protocol
        # parameter flag 0x80). C: mariadb_param_update is_unsigned branch;
        # pure-Python: ExecutePacket unsigned flag + '<Q' packing.
        cur = self.conn.cursor(binary=True)
        for val in (2 ** 63 - 1, 2 ** 63, 2 ** 64 - 1):
            cur.execute("SELECT ? AS x", (val,))
            self.assertEqual(cur.fetchone()[0], val)
        cur.close()

    def test_binary_param_unsigned_bigint_executemany(self):
        # Same unsigned-64 handling on the bulk/executemany path.
        cur = self.conn.cursor(binary=True)
        cur.execute("DROP TABLE IF EXISTS test_c_uint")
        cur.execute("CREATE TABLE test_c_uint (id INT, v BIGINT UNSIGNED)")
        rows = [(1, 2 ** 64 - 1), (2, 2 ** 63), (3, 100)]
        cur.executemany("INSERT INTO test_c_uint VALUES (?, ?)", rows)
        cur.execute("SELECT id, v FROM test_c_uint ORDER BY id")
        self.assertEqual(cur.fetchall(), rows)
        cur.execute("DROP TABLE IF EXISTS test_c_uint")
        cur.close()

    def test_unsigned_bigint_negative_mix_executemany(self):
        # A bulk column mixing a value > 2^63-1 (needs the unsigned flag) with a
        # negative value can't be a binary integer column; both clients promote it
        # to DECIMAL (text) so every value round-trips losslessly.
        cur = self.conn.cursor(binary=True)
        cur.execute("DROP TABLE IF EXISTS test_c_mix")
        cur.execute("CREATE TABLE test_c_mix (id INT, v DECIMAL(40,0))")
        rows = [(1, 2 ** 64 - 1), (2, -5), (3, 100), (4, 2 ** 63)]
        cur.executemany("INSERT INTO test_c_mix VALUES (?, ?)", rows)
        cur.execute("SELECT id, v FROM test_c_mix ORDER BY id")
        self.assertEqual([(i, int(v)) for i, v in cur.fetchall()], rows)
        cur.execute("DROP TABLE IF EXISTS test_c_mix")
        cur.close()

    def test_binary_param_float(self):
        # DOUBLE parameter packing (C: mariadb_param_update MYSQL_TYPE_DOUBLE)
        cur = self.conn.cursor(binary=True)
        cur.execute("SELECT ? AS x", (3.140625,))
        self.assertAlmostEqual(cur.fetchone()[0], 3.140625)
        cur.close()

    def test_binary_param_bytes(self):
        # bytes parameter packing (C: mariadb_param_update MYSQL_TYPE_LONG_BLOB)
        cur = self.conn.cursor(binary=True)
        cur.execute("SELECT ? AS x", (b"\x00\x01\xfe\xff",))
        self.assertEqual(bytes(cur.fetchone()[0]), b"\x00\x01\xfe\xff")
        cur.close()

    def test_binary_param_none(self):
        # NULL parameter (C: mariadb_param_update MYSQL_TYPE_NULL)
        cur = self.conn.cursor(binary=True)
        cur.execute("SELECT ? AS x", (None,))
        self.assertIsNone(cur.fetchone()[0])
        cur.close()

    def test_blob_text_decode(self):
        # text-protocol BLOB/binary decode -> bytes (C: field_to_python)
        cur = self.conn.cursor()
        cur.execute("SELECT 0xCAFEBABE")
        self.assertEqual(bytes(cur.fetchone()[0]), b"\xca\xfe\xba\xbe")
        cur.close()


class TestConnectorCodecs(_SharedConnectorCodecs, unittest.TestCase):
    """Parity tests -- run on whichever implementation is active."""

    def setUp(self):
        self.conn = mariadb.connect(**conf())

    def tearDown(self):
        try:
            self.conn.close()
        except Exception:
            pass


class TestCExtOnly(unittest.TestCase):
    """libmariadb-only API with no pure-Python equivalent."""

    def setUp(self):
        if is_native():
            self.skipTest("libmariadb C-extension only API")
        self.conn = mariadb.connect(**conf())

    def tearDown(self):
        try:
            self.conn.close()
        except Exception:
            pass

    def test_auto_reconnect_getter(self):
        # MrdbConnection_getreconnect
        self.assertIn(self.conn.auto_reconnect, (True, False))

    def test_get_timeout_value(self):
        # MrdbConnection_get_timeout_value -> mysql_get_timeout_value (float)
        self.assertIsInstance(self.conn.get_timeout_value(), float)

    def test_session_tracking(self):
        # MrdbConnection_process_status_info: the libmariadb status callback only
        # does work when a Python status_callback is registered. Register one,
        # enable every tracker, then trigger system-variable, schema and
        # transaction-state changes so the OK packets carry SESSION_TRACK info.
        db = conf().get("database") or "testp"
        received = []
        cfg = dict(conf())
        cfg["status_callback"] = lambda connection, data: received.append(data)
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")     # RuntimeWarning if C lib < 3.3.2
            con = mariadb.connect(**cfg)
        try:
            cur = con.cursor()
            for stmt in (
                "SET SESSION session_track_system_variables='*'",
                "SET SESSION session_track_schema=ON",
                "SET SESSION session_track_transaction_info='CHARACTERISTICS'",
                "SET SESSION session_track_state_change=ON",
            ):
                try:
                    cur.execute(stmt)
                except mariadb.Error:
                    pass
            cur.execute("SET @@autocommit=0")    # tracked system-variable change
            cur.execute(f"USE `{db}`")           # schema-change tracking
            con.begin()                          # transaction characteristics/state
            cur.execute("SELECT 1")
            cur.fetchall()
            con.commit()
            cur.execute("SET @@autocommit=1")
            cur.close()
        finally:
            con.close()
        # callback dicts carry the tracked changes (schema/state/variables/status)
        self.assertTrue(any(isinstance(d, dict) for d in received))


if __name__ == "__main__":
    unittest.main()
