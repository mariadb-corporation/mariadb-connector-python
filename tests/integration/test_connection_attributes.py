#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

import unittest

import mariadb

from ..base_test import create_connection


class TestConnectionAttributes(unittest.TestCase):
    """Tests for connection attributes exposed on the connection object."""

    def setUp(self):
        self.connection = create_connection()

    def tearDown(self):
        self.connection.close()

    def test_connection_id(self):
        """connection_id must be a positive integer."""
        cid = self.connection.connection_id
        self.assertIsInstance(cid, int)
        self.assertGreater(cid, 0)

    def test_user(self):
        """user must be a non-empty string."""
        self.assertIsInstance(self.connection.user, str)
        self.assertTrue(len(self.connection.user) > 0)

    def test_database(self):
        """database must be a string or None."""
        db = self.connection.database
        self.assertTrue(db is None or isinstance(db, str))

    def test_server_info(self):
        """server_info must be a non-empty string."""
        info = self.connection.server_info
        self.assertIsInstance(info, str)
        self.assertTrue(len(info) > 0)

    def test_server_version(self):
        """server_version must be a positive integer in MMMMPP form."""
        sv = self.connection.server_version
        self.assertIsInstance(sv, int)
        self.assertGreater(sv, 0)

    def test_server_version_info(self):
        """server_version_info must be a 3-tuple of non-negative ints consistent with server_version."""
        svi = self.connection.server_version_info
        self.assertIsInstance(svi, tuple)
        self.assertEqual(len(svi), 3)
        for i, part in enumerate(svi):
            self.assertIsInstance(part, int, f"server_version_info[{i}] must be int")
            self.assertGreaterEqual(part, 0)

        expected_numeric = svi[0] * 10000 + svi[1] * 100 + svi[2]
        self.assertEqual(self.connection.server_version, expected_numeric)

    def test_server_mariadb(self):
        """server_mariadb must be a boolean."""
        self.assertIsInstance(self.connection.server_mariadb, bool)

    def test_server_status(self):
        """server_status must be a non-negative integer."""
        ss = self.connection.server_status
        self.assertIsInstance(ss, int)
        self.assertGreaterEqual(ss, 0)

    def test_character_set(self):
        """character_set must be a non-empty string."""
        cs = self.connection.character_set
        self.assertIsInstance(cs, str)
        self.assertTrue(len(cs) > 0)

    def test_collation(self):
        """collation must be a non-empty string."""
        col = self.connection.collation
        self.assertIsInstance(col, str)
        self.assertTrue(len(col) > 0)

    def test_warnings(self):
        """warnings must be a non-negative integer."""
        w = self.connection.warnings
        self.assertIsInstance(w, int)
        self.assertGreaterEqual(w, 0)

    def test_autocommit_default(self):
        """autocommit defaults to False on a fresh connection."""
        self.assertFalse(self.connection.autocommit)

    def test_autocommit_toggle(self):
        """Setting autocommit to True and back to False works correctly."""
        self.connection.autocommit = True
        self.assertTrue(self.connection.autocommit)
        self.connection.autocommit = False
        self.assertFalse(self.connection.autocommit)

    def test_server_name(self):
        """server_name is a non-empty string for TCP connections, None for unix socket."""
        name = self.connection.server_name
        if name is not None:
            self.assertIsInstance(name, str)
            self.assertTrue(len(name) > 0)

    def test_server_port(self):
        """server_port is a non-negative integer (0 for unix socket connections)."""
        port = self.connection.server_port
        self.assertIsInstance(port, int)
        self.assertGreaterEqual(port, 0)

    def test_client_capabilities(self):
        """client_capabilities must be a positive integer."""
        caps = self.connection.client_capabilities
        self.assertIsInstance(caps, int)
        self.assertTrue(caps != 0)

    def test_server_capabilities(self):
        """server_capabilities must be a positive integer."""
        caps = self.connection.server_capabilities
        self.assertIsInstance(caps, int)
        self.assertTrue(caps != 0)


if __name__ == '__main__':
    unittest.main()
