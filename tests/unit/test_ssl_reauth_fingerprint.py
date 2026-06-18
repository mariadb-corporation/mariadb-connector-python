#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""
The self-signed (zero-config) fingerprint check must run only at the INITIAL
connect, not on a later re-authentication (change_user).

The cert is pinned at connect via the MitM-proof password auth; change_user
reuses that same, already-validated TLS session and the server does not resend
the binding hash, so re-validating would spuriously fail. The C extension
(libmariadb) likewise validates only at connect. Regression guard for the
change_user-under-zero-config-TLS failure.
"""

import unittest
from types import SimpleNamespace

import mariadb
from mariadb.impl.client.base_client import BaseClient


def _validator(fingerprint_ok, period_error=None):
    return SimpleNamespace(
        get_fingerprint=lambda: b"deadbeef",
        check_certificate_period=lambda: period_error,
        validate_fingerprint=lambda plugin_hash, seed, info: fingerprint_ok,
    )


def _client(connected, fingerprint_ok):
    # Duck-typed stand-in providing only what validate_ssl_fingerprint touches.
    return SimpleNamespace(
        connected=connected,
        cert_fingerprint_validator=_validator(fingerprint_ok),
        is_local_connection=lambda: False,
        auth_plugin=SimpleNamespace(is_mitm_proof=lambda: True,
                                    hash=lambda cfg: b"hash"),
        configuration=SimpleNamespace(password="secret"),
        context=SimpleNamespace(auth_data=b"seed"),
    )


class ReauthFingerprintTest(unittest.TestCase):

    def test_skipped_on_reauth_even_if_it_would_fail(self):
        # connected=True (change_user): skipped -> no raise, even though the
        # fingerprint would not validate. Fails without the connect-only guard.
        client = _client(connected=True, fingerprint_ok=False)
        BaseClient.validate_ssl_fingerprint(client, SimpleNamespace(info=b""))

    def test_validated_at_connect_raises_on_mismatch(self):
        # connected=False (initial connect): a failing fingerprint still raises.
        client = _client(connected=False, fingerprint_ok=False)
        with self.assertRaises(mariadb.OperationalError):
            BaseClient.validate_ssl_fingerprint(client, SimpleNamespace(info=b""))

    def test_validated_at_connect_passes_on_match(self):
        # connected=False + matching fingerprint: no raise.
        client = _client(connected=False, fingerprint_ok=True)
        BaseClient.validate_ssl_fingerprint(client, SimpleNamespace(info=b""))


if __name__ == "__main__":
    unittest.main()
