#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""
Unit tests for LOAD DATA LOCAL INFILE filename validation.

A server's LOCAL INFILE request must name exactly the file the client's own SQL
asked to load. The filename comparison is case-SENSITIVE: on a case-sensitive
filesystem a MitM server must not be able to substitute a name differing only in
case (e.g. 'File.txt' for 'file.txt') and have the client stream a different
file. SQL keywords (LOAD/DATA/LOCAL/INFILE) remain case-insensitive.
Mirrors mariadb-connector-j#225.
"""

import unittest
from mariadb.impl.client.sync_client import SyncClient
from mariadb.impl.client.async_client import AsyncClient


def _validate(sql, filename):
    # _validate_local_filename does not use `self`; call it unbound on both
    # implementations to confirm they behave identically.
    sync = SyncClient._validate_local_filename(None, sql, filename)
    asyncv = AsyncClient._validate_local_filename(None, sql, filename)
    assert sync == asyncv, f"sync/async disagree: {sync} vs {asyncv}"
    return sync


class LocalInfileFilenameTest(unittest.TestCase):

    SQL = "LOAD DATA LOCAL INFILE 'file.txt' INTO TABLE t"

    def test_exact_match_accepted(self):
        self.assertTrue(_validate(self.SQL, "file.txt"))

    def test_wrong_case_rejected(self):
        # the core fix: server asking a different-case name must be rejected
        self.assertFalse(_validate(self.SQL, "File.txt"))
        self.assertFalse(_validate(self.SQL, "FILE.TXT"))

    def test_keywords_remain_case_insensitive(self):
        self.assertTrue(_validate("load data local infile 'file.txt' into table t",
                                  "file.txt"))
        self.assertTrue(_validate("LoAd DaTa LoCaL InFiLe 'file.txt' into table t",
                                  "file.txt"))

    def test_unrelated_filename_rejected(self):
        self.assertFalse(_validate(self.SQL, "other.txt"))

    def test_path_with_directory_exact(self):
        sql = "LOAD DATA LOCAL INFILE '/tmp/Data/file.txt' INTO TABLE t"
        self.assertTrue(_validate(sql, "/tmp/Data/file.txt"))
        self.assertFalse(_validate(sql, "/tmp/data/file.txt"))  # case differs

    def test_double_quoted_filename(self):
        sql = 'LOAD DATA LOCAL INFILE "file.txt" INTO TABLE t'
        self.assertTrue(_validate(sql, "file.txt"))
        self.assertFalse(_validate(sql, "File.txt"))


if __name__ == "__main__":
    unittest.main()
