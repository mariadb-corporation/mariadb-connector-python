#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
End-to-end authentication tests against a real server with FIPS mode forced on.

The pure-Python client used to be unusable on a FIPS-enforcing OpenSSL for
*every* account, parsec ones included: the handshake response always carries a
mysql_native_password scramble, that scramble is a SHA-1 construction, and SHA-1
raises there -- so the connection died before the server could send the
authentication-switch request that selects the account's real plugin.

These tests force the mode with fips.set_fips_mode() (the suite runs on a normal
build) and check the two outcomes that matter on the wire:

  - a parsec account authenticates normally, and
  - a mysql_native_password account is refused with the reason spelled out.
"""

import unittest
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import mariadb
from tests.base_test import create_connection, is_maxscale, is_native, get_host_suffix
from tests.conftest import get_test_config

_PASSWORD = "Fips_Test_Password_123!"  # nosec B105 - test fixture
_PARSEC_USER = "fips_parsec_user"
_NATIVE_USER = "fips_native_user"


@unittest.skipIf(not is_native(),
                 "FIPS handling lives in the pure-Python client; the C extension "
                 "delegates authentication to libmariadb")
@unittest.skipIf(is_maxscale(), "PARSEC authentication plugin not available through MaxScale")
class TestFipsAuthentication(unittest.TestCase):

    def setUp(self):
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # noqa: F401
                Ed25519PrivateKey,
            )
        except ImportError:
            self.skipTest("cryptography library required for PARSEC authentication")

        from mariadb.impl import fips
        self.fips = fips

        self.connection = create_connection()
        self.cursor = self.connection.cursor()
        try:
            self.cursor.execute("INSTALL SONAME 'auth_parsec'")
        except mariadb.Error:
            pass
        self.cursor.execute(
            "SELECT PLUGIN_NAME FROM information_schema.PLUGINS WHERE PLUGIN_NAME='parsec'")
        if not self.cursor.fetchone():
            self.skipTest("Server does not support PARSEC authentication plugin")

        suffix = get_host_suffix()
        for user, plugin in ((_PARSEC_USER, "parsec"),
                             (_NATIVE_USER, "mysql_native_password")):
            self.cursor.execute(f"DROP USER IF EXISTS '{user}'{suffix}")
            self.cursor.execute(f"CREATE USER '{user}'{suffix} IDENTIFIED VIA {plugin} "
                                f"USING PASSWORD('{_PASSWORD}')")
            self.cursor.execute(f"GRANT ALL PRIVILEGES ON *.* TO '{user}'{suffix}")
        self.connection.commit()

    def tearDown(self):
        # Restore auto-detection first: nothing below (and no later test) should
        # run with the forced mode still in place.
        self.fips.set_fips_mode(None)
        suffix = get_host_suffix()
        for user in (_PARSEC_USER, _NATIVE_USER):
            try:
                self.cursor.execute(f"DROP USER IF EXISTS '{user}'{suffix}")
            except mariadb.Error:
                pass
        self.cursor.close()
        self.connection.close()

    def _connect_as(self, user):
        config = get_test_config().copy()
        config['user'] = user
        config['password'] = _PASSWORD
        return mariadb.connect(**config)

    def test_parsec_connects_with_fips_enabled(self):
        self.fips.set_fips_mode(True)
        conn = self._connect_as(_PARSEC_USER)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT USER()")
            self.assertIn(_PARSEC_USER, cursor.fetchone()[0])
            cursor.close()
        finally:
            conn.close()

    def test_native_password_refused_with_fips_enabled(self):
        self.fips.set_fips_mode(True)
        with self.assertRaises(mariadb.OperationalError) as ctx:
            self._connect_as(_NATIVE_USER)
        message = str(ctx.exception)
        self.assertIn("FIPS", message)
        # the error has to name the way out, not just the failure
        self.assertIn("parsec", message)

    def test_both_accounts_work_without_fips(self):
        # Baseline: the FIPS handling must not change anything on a normal build.
        self.fips.set_fips_mode(False)
        for user in (_PARSEC_USER, _NATIVE_USER):
            conn = self._connect_as(user)
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT USER()")
                self.assertIn(user, cursor.fetchone()[0])
                cursor.close()
            finally:
                conn.close()


if __name__ == '__main__':
    unittest.main()
