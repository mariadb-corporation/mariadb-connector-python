#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""
Regression test: the server-initiated LOAD DATA LOCAL INFILE handler must FAIL
CLOSED.

A 0xFB request is only honoured when the filename matches a LOAD ... LOCAL INFILE
in the client's *own* statement. The prepared-statement path used to call the
handler with sql=None, which short-circuited the check and let a malicious/MitM
server read an arbitrary client file. The handler must now reject when there is
no SQL to validate against (sql is None), and when the filename does not match.
"""

import unittest
import mariadb
from mariadb.impl.client.sync_client import SyncClient


class _Cfg:
    local_infile = None          # default: not explicitly disabled


class _FakeClient:
    """Minimal object exposing only what _handle_local_infile's reject path needs."""
    configuration = _Cfg()
    _handle_local_infile = SyncClient._handle_local_infile
    _validate_local_filename = SyncClient._validate_local_filename

    def __init__(self):
        self.sent = []

    def write_payload(self, *args, **kwargs):
        # the handler writes an empty packet to keep the stream sane before raising
        self.sent.append((args, kwargs))


def _request(filename):
    # 0xFB marker + NUL-terminated filename, as the server sends it
    return memoryview(bytearray([0xFB]) + filename.encode("utf-8") + b"\x00")


class LocalInfileFailClosedTest(unittest.TestCase):

    def test_rejects_when_no_sql_context(self):
        # prepared-statement path historically passed sql=None -> bypass. Must reject now.
        client = _FakeClient()
        with self.assertRaises(mariadb.OperationalError):
            client._handle_local_infile(_request("/etc/passwd"), None, None)

    def test_rejects_when_filename_does_not_match_sql(self):
        client = _FakeClient()
        sql = "LOAD DATA LOCAL INFILE 'wanted.csv' INTO TABLE t"
        with self.assertRaises(mariadb.OperationalError):
            client._handle_local_infile(_request("/etc/passwd"), sql, None)

    def test_rejects_for_non_loaddata_statement(self):
        # a plain SELECT must never trigger a file send even if the server asks
        client = _FakeClient()
        with self.assertRaises(mariadb.OperationalError):
            client._handle_local_infile(_request("/etc/passwd"), "SELECT 1", None)


if __name__ == "__main__":
    unittest.main()
