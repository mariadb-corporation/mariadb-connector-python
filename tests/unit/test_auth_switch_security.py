#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""
Unit tests for the authentication-switch security gates.

After an authentication-switch request the server fully controls the plugin
name, so a hostile/MitM server can request any registered plugin. BaseClient
.check_auth_switch_allowed must reject, *before any credential is sent*:

  1. a clear-text plugin (require_ssl) over an insecure (remote, non-TLS) transport, and
  2. a non-MitM-proof plugin (or empty password) on a connection whose server
     identity rests solely on self-signed-certificate fingerprint validation.

Local connections (loopback TCP or a unix socket) are exempt from both, matching
Connector/C (is_local_connection in my_auth.c). A unix_socket combined with
protocol=TCP actually runs over TCP and is therefore NOT local.
"""

import unittest
import mariadb
from mariadb.impl.client.base_client import BaseClient, PROTOCOL_TCP, PROTOCOL_DEFAULT

# Arbitrary non-empty placeholder. The checks never open the path, so the value
# is irrelevant and must NOT be a real system socket path.
_FAKE_SOCKET = "unix-socket-placeholder"
_REMOTE = "db.example.com"
_LOOPBACK = "127.0.0.1"


class _Cfg:
    def __init__(self, ssl=False, unix_socket=None, password="secret",
                 protocol=PROTOCOL_DEFAULT):
        self.ssl = ssl
        self.unix_socket = unix_socket
        self.password = password
        self.protocol = protocol


class _Host:
    def __init__(self, host):
        self.host = host


class _Validator:
    """Stand-in for SSLFingerprintValidator with a captured fingerprint."""
    def __init__(self, fingerprint=b"\xaa" * 32):
        self._fp = fingerprint

    def get_fingerprint(self):
        return self._fp


class _Factory:
    def __init__(self, require_ssl=False):
        self._require_ssl = require_ssl

    def require_ssl(self):
        return self._require_ssl


class _Plugin:
    def __init__(self, mitm_proof=True):
        self._mitm = mitm_proof

    def is_mitm_proof(self):
        return self._mitm


class _FakeClient:
    """Minimal object exercising the real (protocol-aware) is_local_connection /
    _uses_unix_socket logic alongside the gate."""
    check_auth_switch_allowed = BaseClient.check_auth_switch_allowed
    is_local_connection = BaseClient.is_local_connection
    _uses_unix_socket = BaseClient._uses_unix_socket

    def __init__(self, cfg, validator=None, host=_REMOTE):
        self.configuration = cfg
        self.cert_fingerprint_validator = validator
        self.host_address = _Host(host)


class AuthSwitchSecurityTest(unittest.TestCase):

    # --- check 1: clear-text plugin requires a secure transport ---------------

    def test_require_ssl_plugin_rejected_over_remote_plain_tcp(self):
        client = _FakeClient(_Cfg(ssl=False), host=_REMOTE)
        with self.assertRaises(mariadb.OperationalError):
            client.check_auth_switch_allowed("mysql_clear_password",
                                             _Factory(require_ssl=True), _Plugin())

    def test_require_ssl_plugin_allowed_over_tls(self):
        client = _FakeClient(_Cfg(ssl=True), host=_REMOTE)
        client.check_auth_switch_allowed("mysql_clear_password",
                                         _Factory(require_ssl=True), _Plugin())

    def test_require_ssl_plugin_allowed_over_unix_socket(self):
        client = _FakeClient(_Cfg(ssl=False, unix_socket=_FAKE_SOCKET))
        client.check_auth_switch_allowed("mysql_clear_password",
                                         _Factory(require_ssl=True), _Plugin())

    def test_require_ssl_plugin_allowed_over_loopback(self):
        # loopback is local -> exempt (matches Connector/C is_local_connection)
        client = _FakeClient(_Cfg(ssl=False), host=_LOOPBACK)
        client.check_auth_switch_allowed("mysql_clear_password",
                                         _Factory(require_ssl=True), _Plugin())

    def test_require_ssl_plugin_rejected_when_unix_socket_overridden_by_tcp(self):
        # unix_socket set but protocol=TCP -> actually a remote TCP connection,
        # so NOT a secure transport
        client = _FakeClient(_Cfg(ssl=False, unix_socket=_FAKE_SOCKET,
                                  protocol=PROTOCOL_TCP), host=_REMOTE)
        with self.assertRaises(mariadb.OperationalError):
            client.check_auth_switch_allowed("mysql_clear_password",
                                             _Factory(require_ssl=True), _Plugin())

    def test_non_require_ssl_plugin_allowed_over_plain_tcp(self):
        client = _FakeClient(_Cfg(ssl=False), host=_REMOTE)
        client.check_auth_switch_allowed("mysql_native_password",
                                         _Factory(require_ssl=False), _Plugin())

    # --- check 2: fingerprint-only connection requires a MitM-proof plugin -----

    def test_fingerprint_only_rejects_non_mitm_proof_plugin(self):
        # e.g. caching_sha2_password over a remote fingerprint connection
        client = _FakeClient(_Cfg(ssl=True), validator=_Validator(), host=_REMOTE)
        with self.assertRaises(mariadb.OperationalError):
            client.check_auth_switch_allowed("caching_sha2_password",
                                             _Factory(), _Plugin(mitm_proof=False))

    def test_fingerprint_only_rejects_empty_password(self):
        client = _FakeClient(_Cfg(ssl=True, password=""), validator=_Validator(),
                             host=_REMOTE)
        with self.assertRaises(mariadb.OperationalError):
            client.check_auth_switch_allowed("mysql_native_password",
                                             _Factory(), _Plugin(mitm_proof=True))

    def test_fingerprint_only_allows_mitm_proof_plugin_with_password(self):
        client = _FakeClient(_Cfg(ssl=True, password="secret"), validator=_Validator(),
                             host=_REMOTE)
        client.check_auth_switch_allowed("mysql_native_password",
                                         _Factory(), _Plugin(mitm_proof=True))

    def test_fingerprint_skipped_for_unix_socket(self):
        # unix socket is local -> exempt, so a non-MitM-proof plugin is fine
        client = _FakeClient(_Cfg(ssl=True, unix_socket=_FAKE_SOCKET),
                             validator=_Validator())
        client.check_auth_switch_allowed("caching_sha2_password",
                                         _Factory(), _Plugin(mitm_proof=False))

    def test_fingerprint_skipped_for_loopback(self):
        # loopback is local -> exempt (matches Connector/C)
        client = _FakeClient(_Cfg(ssl=True), validator=_Validator(), host=_LOOPBACK)
        client.check_auth_switch_allowed("caching_sha2_password",
                                         _Factory(), _Plugin(mitm_proof=False))

    def test_fingerprint_not_skipped_when_unix_socket_overridden_by_tcp(self):
        # unix_socket set but protocol=TCP -> remote TCP -> not exempt
        client = _FakeClient(_Cfg(ssl=True, unix_socket=_FAKE_SOCKET,
                                  protocol=PROTOCOL_TCP), validator=_Validator(),
                             host=_REMOTE)
        with self.assertRaises(mariadb.OperationalError):
            client.check_auth_switch_allowed("caching_sha2_password",
                                             _Factory(), _Plugin(mitm_proof=False))

    def test_no_fingerprint_allows_non_mitm_proof_plugin(self):
        # normal verified-TLS (or no TLS) connection: no fingerprint validator
        client = _FakeClient(_Cfg(ssl=True), validator=None, host=_REMOTE)
        client.check_auth_switch_allowed("caching_sha2_password",
                                         _Factory(), _Plugin(mitm_proof=False))


if __name__ == "__main__":
    unittest.main()
