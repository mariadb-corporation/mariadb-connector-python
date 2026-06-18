#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""
Integration tests for secure-by-default (2.0): TLS and certificate verification
are ON unless explicitly disabled.

Whether TLS is actually in use is asserted through the server-side Ssl_cipher
status variable, so the checks are identical for the pure-Python and C
implementations. A small fake server is used to prove that, when TLS is required
(the default), a server that does not support SSL produces a hard error rather
than a silent plaintext fallback.
"""

import socket
import struct
import threading
import unittest

import mariadb
from tests.conftest import get_test_config
from tests.base_test import is_maxscale


def _base_conf(**overrides):
    """Test config with every ssl*/tls_version key stripped, so each test
    controls the TLS settings explicitly (and the connector default applies
    when a test sets nothing)."""
    conf = {k: v for k, v in get_test_config().items()
            if not (k == 'ssl' or k.startswith('ssl_') or k == 'tls_version')}
    conf.update(overrides)
    return conf


def _ssl_cipher(conn):
    """The cipher the server negotiated: a non-empty string under TLS, '' in clear."""
    cur = conn.cursor()
    cur.execute("SHOW STATUS LIKE 'Ssl_cipher'")
    row = cur.fetchone()
    return row[1] if row else ""


@unittest.skipIf(is_maxscale(), "MaxScale forwards SHOW STATUS Ssl_cipher from its "
                 "backend connection, so the client-side TLS state can't be verified")
class TestSslDefault(unittest.TestCase):
    """SSL is enabled by default; ssl=False truly disables it."""

    @classmethod
    def setUpClass(cls):
        # Detect TLS support robustly across MariaDB and MySQL: @@have_ssl is not
        # reliable (MySQL 8.4 removed it), so probe instead -- connect with TLS and
        # verification off (accepts a self-signed cert) and check for a cipher.
        cls._server_has_ssl = False
        try:
            c = mariadb.connect(**_base_conf(ssl=True, ssl_verify_cert=False))
            cls._server_has_ssl = (_ssl_cipher(c) != "")
            c.close()
        except mariadb.Error:
            pass
        cls._default_tls_ok = False
        if cls._server_has_ssl:
            try:
                c = mariadb.connect(**_base_conf())
                c.close()
                cls._default_tls_ok = True
            except mariadb.Error:
                pass

    def setUp(self):
        if not self._server_has_ssl:
            self.skipTest("server has no TLS support")

    def _require_verifiable_tls(self):
        if not self._default_tls_ok:
            self.skipTest("secure-by-default TLS not verifiable here (no zero-conf / no CA)")

    def test_default_connection_uses_tls(self):
        # No ssl option at all -> secure by default -> TLS is negotiated.
        self._require_verifiable_tls()
        conn = mariadb.connect(**_base_conf())
        try:
            self.assertNotEqual(_ssl_cipher(conn), "",
                                "a default connection must use TLS (secure by default)")
        finally:
            conn.close()

    def test_ssl_false_disables_tls(self):
        # Explicit opt-out -> no TLS at all (plaintext).
        conn = mariadb.connect(**_base_conf(ssl=False))
        try:
            self.assertEqual(_ssl_cipher(conn), "",
                             "ssl=False must disable TLS (plaintext)")
        finally:
            conn.close()

    def test_ssl_true_uses_tls(self):
        self._require_verifiable_tls()
        conn = mariadb.connect(**_base_conf(ssl=True))
        try:
            self.assertNotEqual(_ssl_cipher(conn), "")
        finally:
            conn.close()

    def test_ssl_verify_cert_false_still_uses_tls(self):
        # Turning verification off must NOT turn TLS off.
        conn = mariadb.connect(**_base_conf(ssl_verify_cert=False))
        try:
            self.assertNotEqual(_ssl_cipher(conn), "",
                                "ssl_verify_cert=False still encrypts")
        finally:
            conn.close()

    def test_ssl_false_overrides_verify_cert(self):
        # ssl=False wins even if ssl_verify_cert is left on -> still plaintext.
        conn = mariadb.connect(**_base_conf(ssl=False, ssl_verify_cert=True))
        try:
            self.assertEqual(_ssl_cipher(conn), "")
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Fake server that does NOT advertise the CLIENT_SSL capability.
# ---------------------------------------------------------------------------

_CLIENT_PROTOCOL_41 = 0x00000200
_CLIENT_SECURE_CONNECTION = 0x00008000
_CLIENT_PLUGIN_AUTH = 0x00080000
# NOTE: CLIENT_SSL (0x00000800) is deliberately omitted.


def _handshake_without_ssl():
    """A minimal protocol-10 initial handshake that does NOT advertise CLIENT_SSL."""
    caps = _CLIENT_PROTOCOL_41 | _CLIENT_SECURE_CONNECTION | _CLIENT_PLUGIN_AUTH
    body = b"\x0a"                                  # protocol version 10
    body += b"5.7.40-fake\x00"                      # server version
    body += struct.pack("<I", 1)                    # thread id
    body += b"\x01\x02\x03\x04\x05\x06\x07\x08"     # auth-plugin-data part 1
    body += b"\x00"                                 # filler
    body += struct.pack("<H", caps & 0xFFFF)        # capability flags (lower)
    body += b"\x21"                                 # charset
    body += struct.pack("<H", 0x0002)               # status flags
    body += struct.pack("<H", (caps >> 16) & 0xFFFF)  # capability flags (upper)
    body += b"\x15"                                 # length of auth-plugin-data (21)
    body += b"\x00" * 10                            # reserved
    body += b"\x09\x0a\x0b\x0c\x0d\x0e\x0f\x10\x11\x12\x13\x14\x00"  # auth part 2 (13)
    body += b"mysql_native_password\x00"            # auth plugin name
    header = struct.pack("<I", len(body))[:3] + b"\x00"  # 3-byte length + seq 0
    return header + body


def _start_fake_server_no_ssl():
    """One-shot TCP server that sends a no-SSL handshake then closes. Returns port."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def serve():
        try:
            srv.settimeout(10)
            conn, _ = srv.accept()
            conn.sendall(_handshake_without_ssl())
            # The client should reject SSL and close; drain briefly then close.
            try:
                conn.settimeout(2)
                conn.recv(1024)
            except OSError:
                pass
            conn.close()
        except OSError:
            pass
        finally:
            srv.close()

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    return port, t


class TestSslRequiredServerWithoutSsl(unittest.TestCase):

    def test_ssl_required_but_server_has_no_ssl_raises(self):
        # Secure-by-default REQUIRES TLS: a server that doesn't advertise the SSL
        # capability must cause a hard error, never a silent plaintext fallback.
        port, t = _start_fake_server_no_ssl()
        try:
            with self.assertRaises(mariadb.Error) as cm:
                mariadb.connect(user="u", password="p", host="127.0.0.1",
                                port=port, ssl=True, connect_timeout=5)
            msg = str(cm.exception).upper()
            self.assertIn("SSL", msg.replace("TLS", "SSL"),
                          "error should explain that the server lacks SSL, got: %s"
                          % cm.exception)
        finally:
            t.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
