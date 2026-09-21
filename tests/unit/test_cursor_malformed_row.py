#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""Regression test: a malformed binary-protocol row must raise, not crash.

A hostile (or compromised) server can answer COM_STMT_EXECUTE with a row whose
length-encoded field length is larger than the bytes the packet actually
carries.  A bounds-checking Connector/C (CONC-820, released in 3.4.10 / 3.3.20)
refuses such a row and makes mysql_stmt_fetch() return an error.

MrdbCursor_fetchinternal() (C extension) used to special-case only
MYSQL_NO_DATA and report every other return value -- including the error
return -- as a good row.  The connector then built a tuple from self->values[],
which the refused row never filled, and PyTuple_SET_ITEM() dereferenced a NULL
PyObject*, crashing the interpreter.  The fetch error must surface as a Python
exception instead.

Only the C extension walks the raw binary row through mysql_stmt_fetch(); the
pure-Python client slices a bounded buffer and is unaffected, so this test runs
on the C extension only.  Against a Connector/C without the CONC-820 sentinel
the library does not reject the row (it over-reads instead), so the fetch-error
path is unreachable and the test is skipped.
"""

from __future__ import annotations

import struct
import unittest

import mariadb
from tests.base_test import is_native
from tests.unit._fakeserver import (
    MYSQL_TYPE_BLOB, FakeServer, column_def, eof_body, fake_conf, lenenc_int,
    pkt, prepare_ok, scripted_handler,
)

CHARSET_BINARY = 63

# The field header claims DECLARED bytes; the packet only supplies ACTUAL.
DECLARED = 4096
ACTUAL = 4

QUERY = "SELECT c FROM t WHERE d=?"


def _has_conc820_sentinel() -> bool:
    """True when the linked Connector/C rejects an over-long field length."""
    version = getattr(mariadb, "mariadbapi_version", None)
    if not version:
        return False
    try:
        parts = tuple(int(x) for x in version.split(".")[:3])
    except ValueError:
        return False
    if parts[:2] == (3, 3):
        return parts >= (3, 3, 20)
    return parts >= (3, 4, 10)


def _evil_row() -> bytes:
    """A binary row for one column: status byte, null bitmap, then a
    length-encoded field that lies about its size."""
    # null bitmap for 1 field is (1 + 7 + 2) // 8 == 1 byte, none set
    return b"\x00" + b"\x00" + lenenc_int(DECLARED) + (b"A" * ACTUAL)


def _handler():
    def on_prepare(payload: bytes) -> bytes:
        return prepare_ok(
            stmt_id=1, num_params=1,
            columns=[("c", MYSQL_TYPE_BLOB, CHARSET_BINARY)])

    def on_execute(payload: bytes) -> bytes:
        return (pkt(1, lenenc_int(1))
                + pkt(2, column_def("c", MYSQL_TYPE_BLOB,
                                    charset=CHARSET_BINARY, length=DECLARED))
                + pkt(3, eof_body())
                + pkt(4, _evil_row())
                + pkt(5, eof_body()))

    return scripted_handler(on_prepare=on_prepare, on_execute=on_execute)


@unittest.skipIf(is_native(), "C extension walks the raw binary row; pure "
                              "Python slices a bounded buffer")
@unittest.skipUnless(
    _has_conc820_sentinel(),
    "linked Connector/C predates CONC-820; it does not reject the row")
class TestCursorMalformedRow(unittest.TestCase):

    def test_malformed_row_raises_not_crash(self) -> None:
        """A refused row must raise a mariadb error, not segfault, and not the
        SystemError CPython reports for 'a result with an exception set'."""
        with FakeServer(_handler()) as server:
            connection = mariadb.connect(**fake_conf(server.port))
            try:
                cursor = connection.cursor(binary=True)
                cursor.execute(QUERY, (b"x",))
                with self.assertRaises(mariadb.Error) as ctx:
                    cursor.fetchall()
                self.assertNotIsInstance(ctx.exception, SystemError)
                cursor.close()
            finally:
                connection.close()

    def test_malformed_row_fetchone_raises(self) -> None:
        """Same on the fetchone() path."""
        with FakeServer(_handler()) as server:
            connection = mariadb.connect(**fake_conf(server.port))
            try:
                cursor = connection.cursor(binary=True)
                cursor.execute(QUERY, (b"x",))
                with self.assertRaises(mariadb.Error) as ctx:
                    cursor.fetchone()
                self.assertNotIsInstance(ctx.exception, SystemError)
                cursor.close()
            finally:
                connection.close()


if __name__ == '__main__':
    unittest.main()
