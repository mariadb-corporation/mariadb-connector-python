#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""
Unit tests for authentication on a FIPS-enforcing crypto backend.

A Python linked against a FIPS-enforcing OpenSSL has no SHA-1, so the
mysql_native_password scramble every connector puts in its handshake response
cannot be computed. Before this handling the pure-Python client raised there and
could not connect at all -- not even for an account on the FIPS-compliant
parsec plugin, because reaching parsec requires completing the handshake first
and getting the server's authentication-switch request.

What must hold under FIPS:

  1. the native-password scramble is an all-zero placeholder instead of an
     exception, so the handshake stays well-formed and the switch happens;
  2. a plugin that is not FIPS-compliant is refused up front, with a message
     naming the cause, whenever the server switches to it;
  3. parsec (PBKDF2-HMAC-SHA512 + Ed25519) is accepted;
  4. an account that really is on mysql_native_password gets a server "access
     denied" annotated with the actual reason, not a bare one.

These tests force the mode with fips.set_fips_mode() so both branches run on a
build where SHA-1 works fine.
"""

import os
import unittest
from unittest import mock

import mariadb
from mariadb.impl import fips
from mariadb.impl.client.base_client import BaseClient
from mariadb.impl.client.context import Context
from mariadb.impl.client.exception_factory import ExceptionFactory
from mariadb.impl.configuration import Configuration
from mariadb.impl.message.client.handshake_response import HandshakeResponse
from mariadb.impl.message.payload_writer import PayloadWriter
from mariadb.impl.plugin.authentication_plugin_factory import AuthenticationPluginFactory
from mariadb.impl.plugin.authentication_plugin_loader import AuthenticationPluginLoader
from mariadb.impl.plugin.authentication.caching_sha2_password_plugin import (
    CachingSha2PasswordPlugin,
)
from mariadb.impl.plugin.authentication.native_password_plugin import NativePasswordPlugin
from mariadb_shared.constants import CAPABILITY

_SEED = b"\x01" * 20
_PASSWORD = "secret"  # nosec B105 - test fixture


class _FipsModeTestCase(unittest.TestCase):
    """Restores auto-detection after every test so no mode leaks between them."""

    def tearDown(self):
        fips.set_fips_mode(None)


class FipsDetectionTest(_FipsModeTestCase):

    def test_sha1_available_on_a_normal_build(self):
        # The probe must not report FIPS on the (non-FIPS) build running the suite,
        # otherwise every connection here would lose native-password support.
        self.assertTrue(fips._sha1_available())

    def test_env_var_forces_fips_on(self):
        with mock.patch.dict(os.environ, {fips.FIPS_MODE_ENV_VAR: "1"}):
            fips.set_fips_mode(None)
            self.assertTrue(fips.is_fips_mode())

    def test_env_var_forces_fips_off(self):
        with mock.patch.dict(os.environ, {fips.FIPS_MODE_ENV_VAR: "off"}):
            fips.set_fips_mode(None)
            self.assertFalse(fips.is_fips_mode())

    def test_unparsable_env_var_falls_back_to_detection(self):
        with mock.patch.dict(os.environ, {fips.FIPS_MODE_ENV_VAR: "maybe"}):
            fips.set_fips_mode(None)
            self.assertFalse(fips.is_fips_mode())

    def test_detection_result_is_cached(self):
        fips.set_fips_mode(None)
        with mock.patch.object(fips, "_sha1_available", return_value=False) as probe:
            self.assertTrue(fips.is_fips_mode())
            self.assertTrue(fips.is_fips_mode())
            self.assertEqual(1, probe.call_count)


class NativePasswordUnderFipsTest(_FipsModeTestCase):

    def test_scramble_is_zero_placeholder(self):
        fips.set_fips_mode(True)
        scramble = NativePasswordPlugin.encrypt_password(_PASSWORD, _SEED)
        self.assertEqual(bytearray(fips.SHA1_DIGEST_LENGTH), scramble)

    def test_empty_password_still_sends_nothing(self):
        # No hash is involved for a passwordless account, so the wire format must
        # not change: an empty response, not 20 zero bytes.
        fips.set_fips_mode(True)
        self.assertEqual(bytearray(b''), NativePasswordPlugin.encrypt_password("", _SEED))
        self.assertEqual(bytearray(b''), NativePasswordPlugin.encrypt_password(None, _SEED))

    def test_real_scramble_when_not_in_fips_mode(self):
        # Guards against the placeholder leaking onto normal builds.
        fips.set_fips_mode(False)
        scramble = NativePasswordPlugin.encrypt_password(_PASSWORD, _SEED)
        self.assertEqual(fips.SHA1_DIGEST_LENGTH, len(scramble))
        self.assertNotEqual(bytearray(fips.SHA1_DIGEST_LENGTH), scramble)

    def test_credential_hash_unavailable_under_fips(self):
        # hash() feeds self-signed-certificate fingerprint validation, which
        # treats a missing hash as a hard failure -> fails closed, not crashes.
        conf = Configuration()
        conf.password = _PASSWORD
        plugin = NativePasswordPlugin(_PASSWORD, _SEED)
        fips.set_fips_mode(True)
        self.assertIsNone(plugin.hash(conf))
        fips.set_fips_mode(False)
        self.assertEqual(fips.SHA1_DIGEST_LENGTH, len(plugin.hash(conf)))


class HandshakeResponseUnderFipsTest(_FipsModeTestCase):

    @staticmethod
    def _payload():
        conf = Configuration()
        conf.user = "someone"
        conf.password = _PASSWORD
        context = Context(auth_data=_SEED,
                          server_capabilities=CAPABILITY.SECURE_CONNECTION | CAPABILITY.PLUGIN_AUTH)
        context.client_capabilities = CAPABILITY.PLUGIN_AUTH
        return bytes(HandshakeResponse(conf, context).payload(context, PayloadWriter()))

    def test_handshake_carries_zero_placeholder_and_native_plugin_name(self):
        # The plugin name must stay mysql_native_password: it is what triggers the
        # server's authentication-switch request, which is the only way to reach
        # the account's real (FIPS-compliant) plugin.
        fips.set_fips_mode(True)
        payload = self._payload()
        self.assertIn(bytes([fips.SHA1_DIGEST_LENGTH]) + bytes(fips.SHA1_DIGEST_LENGTH), payload)
        self.assertIn(b"mysql_native_password\x00", payload)

    def test_handshake_carries_real_scramble_when_not_in_fips_mode(self):
        fips.set_fips_mode(False)
        payload = self._payload()
        self.assertNotIn(bytes([fips.SHA1_DIGEST_LENGTH]) + bytes(fips.SHA1_DIGEST_LENGTH), payload)


class _CustomPluginFactory(AuthenticationPluginFactory):
    """Third-party plugin that never declared itself FIPS-compliant."""

    def type(self):
        return "unit_test_custom_plugin"

    def initialize(self, authentication_data, seed, conf, host_address):
        raise AssertionError("must be refused before initialize()")


class PluginLoaderFipsGateTest(_FipsModeTestCase):

    def setUp(self):
        self.conf = Configuration()

    def _get(self, plugin_type):
        return AuthenticationPluginLoader.get(plugin_type, self.conf)

    def test_native_password_refused_under_fips(self):
        fips.set_fips_mode(True)
        with self.assertRaises(mariadb.OperationalError) as ctx:
            self._get("mysql_native_password")
        self.assertEqual(1251, ctx.exception.errno)
        self.assertIn("FIPS", str(ctx.exception))
        # the message must point at the way out, not just at the failure
        self.assertIn("parsec", str(ctx.exception))

    def test_native_password_allowed_when_not_in_fips_mode(self):
        fips.set_fips_mode(False)
        self.assertEqual("mysql_native_password", self._get("mysql_native_password").type())

    def test_parsec_allowed_under_fips(self):
        fips.set_fips_mode(True)
        self.assertEqual("parsec", self._get("parsec").type())

    def test_caching_sha2_allowed_under_fips(self):
        # SHA-256 based; only its RSA public-key branch is non-compliant, and that
        # is refused where it happens (see CachingSha2RsaUnderFipsTest).
        fips.set_fips_mode(True)
        self.assertEqual("caching_sha2_password", self._get("caching_sha2_password").type())

    def test_unknown_plugin_still_reports_unsupported_protocol(self):
        fips.set_fips_mode(True)
        with self.assertRaises(mariadb.OperationalError) as ctx:
            self._get("no_such_plugin")
        self.assertIn("does not support authentication protocol", str(ctx.exception))

    def test_custom_plugin_defaults_to_not_fips_compliant(self):
        self.assertFalse(_CustomPluginFactory().fips_compliant())
        AuthenticationPluginLoader.register_plugin(_CustomPluginFactory)
        try:
            fips.set_fips_mode(True)
            with self.assertRaises(mariadb.OperationalError):
                self._get("unit_test_custom_plugin")
            fips.set_fips_mode(False)
            self._get("unit_test_custom_plugin")
        finally:
            AuthenticationPluginLoader._plugin_factories.pop("unit_test_custom_plugin", None)


class CachingSha2RsaUnderFipsTest(_FipsModeTestCase):

    def test_rsa_public_key_exchange_refused_under_fips(self):
        # The exchange is defined with RSA-OAEP over SHA-1. Refuse it with an
        # actionable message rather than letting `cryptography` fail obscurely --
        # note no key material is needed to reach the check.
        conf = Configuration()
        conf.ssl = False
        plugin = CachingSha2PasswordPlugin(_PASSWORD, _SEED, conf, None)
        fips.set_fips_mode(True)
        with self.assertRaises(mariadb.OperationalError) as ctx:
            plugin._get_rsa_encrytped_pwd("not-a-key")
        self.assertIn("FIPS", str(ctx.exception))
        self.assertIn("ssl=True", str(ctx.exception))


class _ErrPacketClient:
    """Minimal object exercising the real BaseClient.build_auth_error."""

    build_auth_error = BaseClient.build_auth_error

    def __init__(self, password=_PASSWORD, plugin=None):
        self.configuration = Configuration()
        self.configuration.password = password
        self.auth_plugin = plugin if plugin is not None else NativePasswordPlugin(password, _SEED)
        self.context = Context()
        self.exception_factory = ExceptionFactory()


def _err_packet(errno, sql_state, message):
    return memoryview(b"\xff" + errno.to_bytes(2, "little")
                      + b"#" + sql_state.encode("ascii") + message.encode("utf-8"))


class AuthErrorAnnotationTest(_FipsModeTestCase):

    _ACCESS_DENIED = _err_packet(1045, "28000", "Access denied for user 'someone'@'host'")

    def test_access_denied_explains_fips(self):
        fips.set_fips_mode(True)
        error = _ErrPacketClient().build_auth_error(self._ACCESS_DENIED)
        self.assertIsInstance(error, mariadb.OperationalError)
        self.assertEqual(1045, error.errno)
        self.assertIn("Access denied", str(error))
        self.assertIn("FIPS", str(error))
        self.assertIn("parsec", str(error))

    def test_access_denied_untouched_when_not_in_fips_mode(self):
        fips.set_fips_mode(False)
        error = _ErrPacketClient().build_auth_error(self._ACCESS_DENIED)
        self.assertNotIn("FIPS", str(error))

    def test_access_denied_untouched_without_password(self):
        # No password means no scramble was expected in the first place, so FIPS
        # is not the explanation for the refusal.
        fips.set_fips_mode(True)
        error = _ErrPacketClient(password=None).build_auth_error(self._ACCESS_DENIED)
        self.assertNotIn("FIPS", str(error))

    def test_other_errors_untouched(self):
        fips.set_fips_mode(True)
        packet = _err_packet(1049, "42000", "Unknown database 'nope'")
        error = _ErrPacketClient().build_auth_error(packet)
        self.assertNotIn("FIPS", str(error))
        self.assertIn("Unknown database", str(error))


if __name__ == "__main__":
    unittest.main()
