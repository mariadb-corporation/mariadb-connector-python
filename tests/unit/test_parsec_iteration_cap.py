#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""
CONPY-372: the parsec iteration factor a server announces must be bounded by
the connection time budget rather than by a hardcoded constant.

The factor is an exponent -- the server asking for factor N means 1024 << N
PBKDF2-HMAC-SHA512 rounds -- so the two obvious implementations both fail:
hardcoding 3 rejects servers legitimately configured above it (MDEV-35254 makes
the count server-side configurable), while raising the constant to 20 as
Connector/C did lets a hostile or MitM server demand ~1.07 billion rounds
(~7.5 min) with one small response, uninterruptible by any timeout.

The cap is therefore derived from connect_timeout: the client declares its own
budget and a longer declared budget permits a larger factor.
"""

import asyncio
import hashlib
import unittest

import pytest

import cryptography
import mariadb
from mariadb.exceptions import OperationalError
from mariadb.impl.plugin.authentication.parsec_password_plugin import (
    HAS_CRYPTOGRAPHY,
    PBKDF2_ROUNDS_PER_MS,
    SERVER_CONNECT_TIMEOUT_DEFAULT,
    Ed25519PrivateKey,
    ParsecPasswordPlugin,
    serialization,
)
from tests.base_test import is_native
from tests.unit._fakeserver import (
    COM_QUIT, FakeServer, fake_conf, handshake_greeting, ok, pkt,
    recv_one_packet,
)

# 32-byte extended salt, as the server sends after the salt request.
_SALT = bytes(range(32))

# Seed the fake server hands out with the auth-switch request; parsec signs
# this concatenated with the client scramble.
_SEED = bytes(range(100, 132))

py_only = pytest.mark.skipif(
    not is_native(),
    reason="pure-Python parsec plugin; with the C extension the parsec "
           "handshake is performed by libmariadb")

# Well below any derived cap, and above the previously hardcoded ceiling of 3,
# so a successful derivation here is the MDEV-35254 compatibility regression.
_FACTOR_ABOVE_OLD_LIMIT = 4


class _Conf:
    """Stand-in for Configuration: the plugin only reads connect_timeout."""

    def __init__(self, connect_timeout):
        self.connect_timeout = connect_timeout


def _salt_response(iterations_exp, algorithm=0x50):
    """Server reply to PARSEC_REQUEST_SALT: algorithm, factor, extended salt."""
    return memoryview(bytes([algorithm, iterations_exp]) + _SALT)


class _Exchange:
    """Records what the plugin writes and feeds it the scripted salt response."""

    def __init__(self, response):
        self._response = response
        self.written = []
        self._reads = 0

    def read_sync(self):
        self._reads += 1
        return self._response

    def write_sync(self, payload, tag, compress):
        self.written.append(tag)

    async def read_async(self):
        return self.read_sync()

    async def write_async(self, payload, tag, compress):
        self.write_sync(payload, tag, compress)


def _run_sync(plugin, response):
    exchange = _Exchange(response)
    try:
        plugin.processSync(exchange.read_sync, exchange.write_sync, None)
    finally:
        _run_sync.last = exchange
    return exchange


def _run_async(plugin, response):
    exchange = _Exchange(response)
    try:
        asyncio.run(
            plugin.processAsync(exchange.read_async, exchange.write_async, None))
    finally:
        _run_async.last = exchange
    return exchange


class TestParsecIterationCap(unittest.TestCase):
    """The cap derivation itself, independent of any exchange."""

    def test_cap_scales_with_connect_timeout(self):
        # Values from CONPY-372: a 2s budget affords factor 11, the 10s default
        # affords 13, a 30s budget affords 15.
        for connect_timeout, expected in ((2, 11), (10, 13), (30, 15)):
            with self.subTest(connect_timeout=connect_timeout):
                plugin = ParsecPasswordPlugin("pwd", b"seed", _Conf(connect_timeout))
                self.assertEqual(expected, plugin._max_iteration_factor())

    def test_unset_or_non_positive_timeout_uses_default_budget(self):
        default = ParsecPasswordPlugin(
            "pwd", b"seed", _Conf(SERVER_CONNECT_TIMEOUT_DEFAULT))
        for connect_timeout in (0, None, -1):
            with self.subTest(connect_timeout=connect_timeout):
                plugin = ParsecPasswordPlugin("pwd", b"seed", _Conf(connect_timeout))
                self.assertEqual(SERVER_CONNECT_TIMEOUT_DEFAULT, plugin._time_budget())
                self.assertEqual(default._max_iteration_factor(),
                                 plugin._max_iteration_factor())

    def test_cap_stays_within_its_budget(self):
        # The cap must be the largest factor that fits, and the next one up
        # must not fit -- at the conservative throughput the constant declares.
        for connect_timeout in (1, 2, 5, 10, 30, 120):
            with self.subTest(connect_timeout=connect_timeout):
                plugin = ParsecPasswordPlugin("pwd", b"seed", _Conf(connect_timeout))
                budget_ms = connect_timeout * 1000
                at_cap = (1024 << plugin._max_iteration_factor()) / PBKDF2_ROUNDS_PER_MS
                above_cap = at_cap * 2
                self.assertLessEqual(at_cap, budget_ms)
                self.assertGreater(above_cap, budget_ms)

    def test_cap_is_far_below_the_connector_c_constant(self):
        # Connector/C raised its constant to 20 (~1.07 billion rounds, ~7.5 min
        # of uninterruptible work). No plausible budget may reach that here.
        plugin = ParsecPasswordPlugin("pwd", b"seed", _Conf(60))
        self.assertLess(plugin._max_iteration_factor(), 20)


@unittest.skipUnless(HAS_CRYPTOGRAPHY, "parsec requires the cryptography library")
class TestParsecIterationEnforcement(unittest.TestCase):
    """The cap as enforced on the wire, sync and async."""

    def _plugin(self, connect_timeout=10):
        return ParsecPasswordPlugin("password", bytes(32), _Conf(connect_timeout))

    def test_factor_above_cap_rejected_before_credentials_are_sent(self):
        for label, run in (("sync", _run_sync), ("async", _run_async)):
            with self.subTest(label):
                plugin = self._plugin()
                too_high = plugin._max_iteration_factor() + 1
                with self.assertRaises(OperationalError) as ctx:
                    run(plugin, _salt_response(too_high))
                message = str(ctx.exception)
                self.assertIn("Wrong parsec authentication format", message)
                self.assertIn(str(too_high), message)
                self.assertIn("connect_timeout", message)
                # Only the salt request went out: no scramble, no signature.
                self.assertEqual(["PARSEC_REQUEST_SALT"],
                                 getattr(run, "last").written)

    def test_factor_at_cap_is_accepted_by_the_format_check(self):
        # Deriving at the cap costs seconds by construction, so only the
        # validation is exercised here; the derivation is covered below at a
        # cheap factor.
        plugin = self._plugin()
        plugin._validate_format(0x50, plugin._max_iteration_factor())

    def test_factor_above_old_hardcoded_limit_authenticates(self):
        # The MDEV-35254 regression: factor 4 was rejected outright before.
        for label, run in (("sync", _run_sync), ("async", _run_async)):
            with self.subTest(label):
                plugin = self._plugin()
                exchange = run(plugin, _salt_response(_FACTOR_ABOVE_OLD_LIMIT))
                self.assertEqual(["PARSEC_REQUEST_SALT", "PARSEC_AUTH"],
                                 exchange.written)
                # 'P' + factor + salt + 32-byte Ed25519 public key
                self.assertEqual(bytes([0x50, _FACTOR_ABOVE_OLD_LIMIT]) + _SALT,
                                 plugin.hash(None)[:34])

    def test_non_pbkdf2_algorithm_still_rejected(self):
        plugin = self._plugin()
        with self.assertRaises(OperationalError) as ctx:
            _run_sync(plugin, _salt_response(0, algorithm=0x51))
        self.assertIn("expected 'P' for KDF algorithm", str(ctx.exception))

    def test_derivation_matches_the_reference_pbkdf2(self):
        # The plugin derives with cryptography's PBKDF2HMAC; a server derives
        # the same key by any other PBKDF2-HMAC-SHA512 implementation, so the
        # two must agree bit for bit or authentication fails.
        plugin = ParsecPasswordPlugin("password", bytes(32), _Conf(10))
        plugin._derive_key_and_sign(_SALT, _FACTOR_ABOVE_OLD_LIMIT)
        derived_public_key = plugin.hash(None)[34:]

        reference = hashlib.pbkdf2_hmac(
            'sha512', b"password", _SALT, 1024 << _FACTOR_ABOVE_OLD_LIMIT, dklen=32)
        expected_public_key = Ed25519PrivateKey.from_private_bytes(
            reference).public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw)
        self.assertEqual(expected_public_key, derived_public_key)

    def test_cryptography_meets_the_gil_releasing_floor(self):
        # Guards the >=50.0.0 floor in pyproject rather than measuring the GIL
        # itself, which would be a flaky wall-clock test on shared CI. Before
        # 50.0.0, PBKDF2HMAC held the GIL for the whole derivation, freezing
        # every other thread for as long as the server-chosen factor demanded.
        major = int(cryptography.__version__.split('.')[0])
        self.assertGreaterEqual(
            major, 50,
            "cryptography >= 50.0.0 is required: older releases hold the GIL "
            "for the duration of the PBKDF2 derivation")


def _parsec_server(iterations_exp, captured):
    """Fake server that switches the client to parsec and drives the exchange.

    Sequence ids continue the handshake: the auth-switch request is 2, the
    client's salt request 3, the salt response 4, its scramble/signature 5.
    """
    def handler(conn):
        conn.sendall(handshake_greeting())
        recv_one_packet(conn)                                  # handshake response
        conn.sendall(pkt(2, b"\xfe" + b"parsec\x00" + _SEED))  # auth switch
        recv_one_packet(conn)                                  # PARSEC_REQUEST_SALT
        # AuthMoreData: 0x01, then 'P', the iteration factor and the salt.
        conn.sendall(pkt(4, b"\x01" + bytes([0x50, iterations_exp]) + _SALT))

        _, auth = recv_one_packet(conn)
        captured['auth'] = auth
        if auth is None:            # client rejected the factor and hung up
            return
        conn.sendall(ok(start_seq=6))
        while True:                 # post-connect setup queries
            _, payload = recv_one_packet(conn)
            if not payload or payload[0] == COM_QUIT:
                return
            conn.sendall(ok(start_seq=1))
    return handler


def _verify_signature(auth, iterations_exp, password=b"p"):
    """Re-derive the key server-side and check the client's Ed25519 signature.

    Proves the whole pure-Python path ran: the derivation used the salt and
    factor the server sent, and the signature covers server seed + client
    scramble.
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    client_scramble, signature = bytes(auth[:32]), bytes(auth[32:])
    key = Ed25519PrivateKey.from_private_bytes(hashlib.pbkdf2_hmac(
        'sha512', password, _SALT, 1024 << iterations_exp, dklen=32))
    # Raises InvalidSignature if the client derived a different key.
    key.public_key().verify(signature, _SEED + client_scramble)


@py_only
@unittest.skipUnless(HAS_CRYPTOGRAPHY, "parsec requires the cryptography library")
class TestParsecOverPurePythonClient(unittest.TestCase):
    """The cap as the pure-Python client applies it, over a real socket.

    The unit tests above build the plugin directly, so they cannot catch the
    factory failing to hand the Configuration over -- which would silently pin
    every connection to the default budget. These connect for real.
    """

    def test_connect_succeeds_above_the_old_hardcoded_limit(self):
        captured = {}
        # connect_timeout 10 -> cap 13, so factor 4 is comfortably affordable
        # while staying cheap enough to derive in a unit test.
        with FakeServer(_parsec_server(_FACTOR_ABOVE_OLD_LIMIT, captured)) as server:
            con = mariadb.connect(**fake_conf(server.port, connect_timeout=10))
            con.close()
        self.assertIsNone(server.error)
        self.assertEqual(96, len(captured['auth']))  # 32-byte scramble + 64-byte signature
        _verify_signature(captured['auth'], _FACTOR_ABOVE_OLD_LIMIT)

    def test_connect_rejects_a_factor_above_the_budget(self):
        captured = {}
        # connect_timeout 2 -> cap 11, so the server demanding 12 is refused.
        with FakeServer(_parsec_server(12, captured)) as server:
            with self.assertRaises(OperationalError) as ctx:
                mariadb.connect(**fake_conf(server.port, connect_timeout=2))
        message = str(ctx.exception)
        self.assertIn("parsec iteration factor 12", message)
        self.assertIn("maximum factor 11", message)
        # Nothing derived from the password ever reached the server.
        self.assertIsNone(captured['auth'])

    def test_connect_timeout_governs_the_client_cap(self):
        # Same server, same factor: refused on a 2s budget, accepted on 10s.
        # This is what the plugin can only get from the Configuration, so it
        # fails if the factory stops passing conf through.
        captured = {}
        with FakeServer(_parsec_server(12, captured)) as server:
            with self.assertRaises(OperationalError):
                mariadb.connect(**fake_conf(server.port, connect_timeout=2))

        plugin = ParsecPasswordPlugin("p", _SEED, _Conf(10))
        self.assertGreaterEqual(plugin._max_iteration_factor(), 12)


if __name__ == '__main__':
    unittest.main()
