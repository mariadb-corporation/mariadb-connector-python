#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""
Unit tests for certificate validity-period enforcement on the fingerprint path.

The MariaDB self-signed / fingerprint TLS path runs over an unverified context
(CERT_NONE), so the TLS layer never checks the certificate's notBefore/notAfter
dates. libmariadb checks MARIADB_TLS_VERIFY_PERIOD on every path, so an expired
(or not-yet-valid) certificate is rejected even there. SSLFingerprintValidator
.check_certificate_period() must reproduce that.
"""

import datetime
import unittest

try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False

from mariadb.impl.client.ssl.ssl_fingerprint_validator import SSLFingerprintValidator


def _make_cert_der(not_before, not_after):
    """Build a self-signed cert DER valid over [not_before, not_after)."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.DER)


@unittest.skipUnless(HAS_CRYPTOGRAPHY, "cryptography required to build test certs")
class CertificatePeriodTest(unittest.TestCase):

    def setUp(self):
        # naive UTC datetimes are accepted by the builder on every cryptography version
        self.now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        self.day = datetime.timedelta(days=1)

    def _validator(self, der):
        v = SSLFingerprintValidator()
        v.cert_der = der
        return v

    def test_valid_certificate_passes(self):
        der = _make_cert_der(self.now - self.day, self.now + self.day)
        self.assertIsNone(self._validator(der).check_certificate_period())

    def test_expired_certificate_rejected(self):
        der = _make_cert_der(self.now - 2 * self.day, self.now - self.day)
        reason = self._validator(der).check_certificate_period()
        self.assertIsNotNone(reason)
        self.assertIn("expired", reason)

    def test_not_yet_valid_certificate_rejected(self):
        der = _make_cert_der(self.now + self.day, self.now + 2 * self.day)
        reason = self._validator(der).check_certificate_period()
        self.assertIsNotNone(reason)
        self.assertIn("not yet valid", reason)

    def test_no_certificate_is_noop(self):
        # nothing captured -> nothing to check (don't fail closed)
        self.assertIsNone(SSLFingerprintValidator().check_certificate_period())


if __name__ == "__main__":
    unittest.main()
