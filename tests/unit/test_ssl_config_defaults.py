#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""
Unit guard for the secure-by-default (2.0) configuration: the pure-Python
Configuration must default to TLS on and certificate verification on, and must
honour an explicit opt-out. (The C extension's matching default lives in C and
is covered by the integration tests in test_ssl_default.py.)
"""

import unittest

from mariadb.impl.configuration import Configuration


class SslConfigDefaultsTest(unittest.TestCase):

    def test_ssl_on_by_default(self):
        self.assertTrue(Configuration().ssl)

    def test_verify_cert_on_by_default(self):
        self.assertTrue(Configuration().ssl_verify_cert)

    def test_from_dict_defaults_when_unspecified(self):
        c = Configuration.from_dict({"host": "db.example.com"})
        self.assertTrue(c.ssl)
        self.assertTrue(c.ssl_verify_cert)

    def test_from_dict_honours_explicit_opt_out(self):
        c = Configuration.from_dict({"ssl": False, "ssl_verify_cert": False})
        self.assertFalse(c.ssl)
        self.assertFalse(c.ssl_verify_cert)


if __name__ == "__main__":
    unittest.main()
