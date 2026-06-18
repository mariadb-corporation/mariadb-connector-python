#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""
Unit tests for local-connection TLS verification.

A local peer (loopback / unix socket) can't be MitM'd, so -- matching libmariadb
(plugins/auth/my_auth.c never sets MARIADB_TLS_VERIFY_HOST for a local
connection) -- the connector must skip the hostname check for local connections.
The certificate chain is still verified when a CA is configured; with no CA only
the validity period is enforced (via the fingerprint validator's period check).
Remote connections are unaffected (hostname still verified).
"""

import os
import ssl
import tempfile
import unittest

try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False

from mariadb.impl.configuration import Configuration
from mariadb.impl.client.ssl.ssl_utility import SSLUtility


class _Ver:
    # non-MariaDB so the MariaDB-only fingerprint path is never taken; this
    # isolates the local-connection branches under test.
    is_mariadb = False

    def version_greater_or_equal(self, *_a):
        return False


class _Ctx:
    version = _Ver()


def _write_ca_file():
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test-ca")])
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    fd, path = tempfile.mkstemp(suffix=".pem")
    with os.fdopen(fd, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    return path


@unittest.skipUnless(HAS_CRYPTOGRAPHY, "cryptography required to build a CA file")
class LocalVerifyTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.ca_path = _write_ca_file()

    @classmethod
    def tearDownClass(cls):
        try:
            os.unlink(cls.ca_path)
        except OSError:
            pass

    def _prepare(self, *, local, **conf_kw):
        conf = Configuration(ssl=True, **conf_kw)
        return SSLUtility.prepare_ssl_context(conf, _Ctx(), local)

    def test_remote_verifies_hostname(self):
        ctx, validator = self._prepare(local=False, ssl_verify_cert=True)
        self.assertTrue(ctx.check_hostname)
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
        self.assertIsNone(validator)

    def test_local_no_ca_period_only(self):
        # hostname skipped, chain dropped (no CA), period enforced via validator
        ctx, validator = self._prepare(local=True, ssl_verify_cert=True)
        self.assertFalse(ctx.check_hostname)
        self.assertEqual(ctx.verify_mode, ssl.CERT_NONE)
        self.assertIsNotNone(validator)

    def test_local_with_ca_keeps_chain_skips_hostname(self):
        ctx, validator = self._prepare(local=True, ssl_verify_cert=True,
                                       ssl_ca=self.ca_path)
        self.assertFalse(ctx.check_hostname)               # hostname skipped
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)  # chain still verified
        self.assertIsNone(validator)

    def test_local_verify_off_unchanged(self):
        # ssl_verify_cert=False already disables everything; nothing to skip
        ctx, validator = self._prepare(local=True, ssl_verify_cert=False)
        self.assertFalse(ctx.check_hostname)
        self.assertEqual(ctx.verify_mode, ssl.CERT_NONE)
        self.assertIsNone(validator)


if __name__ == "__main__":
    unittest.main()
