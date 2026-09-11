#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""
Session-tracking data in OK packets.

The block is one length-encoded total followed by repeated entries of
``type<1> length<lenenc> data``; the server sends one SYSTEM_VARIABLES entry
per changed variable, so the authentication OK and ``SET NAMES`` replies carry
several. The parser used to treat the block total as the first entry's length
and lost every entry after the first (character_set_client was never seen
after authentication, and a charset change hidden behind another variable
escaped the mismatch check).
"""

import unittest

from mariadb.impl.client.context import Context
from mariadb.impl.message.server.ok_packet import CharsetMismatchError, OkPacket
from mariadb_shared import constants


def _lenenc(n: int) -> bytes:
    if n < 251:
        return bytes((n,))
    if n < 65536:
        return b'\xfc' + n.to_bytes(2, 'little')
    return b'\xfd' + n.to_bytes(3, 'little')


def _lenenc_str(s: str) -> bytes:
    data = s.encode()
    return _lenenc(len(data)) + data


def _var(name: str, value: str) -> bytes:
    data = _lenenc_str(name) + _lenenc_str(value)
    return bytes((constants.SESSION_TRACK.SYSTEM_VARIABLES,)) + _lenenc(len(data)) + data


def _schema(name: str) -> bytes:
    data = _lenenc_str(name)
    return bytes((constants.SESSION_TRACK.SCHEMA,)) + _lenenc(len(data)) + data


def _entry(tracking_type: int, data: bytes) -> bytes:
    return bytes((tracking_type,)) + _lenenc(len(data)) + data


def _ok(*entries: bytes, status: int = 0) -> memoryview:
    """OK payload: header, affected rows, insert id, status, warnings, info, session block."""
    status |= constants.STATUS.SESSION_STATE_CHANGED
    block = b''.join(entries)
    return memoryview(b'\x00' + b'\x00' + b'\x00' + status.to_bytes(2, 'little')
                      + b'\x00\x00' + _lenenc(0) + _lenenc(len(block)) + block)


def _context() -> Context:
    return Context(server_capabilities=constants.CAPABILITY.SESSION_TRACKING)


class TestOkPacketSessionTracking(unittest.TestCase):

    def test_authentication_block_sets_charset_and_schema(self) -> None:
        # the entries MariaDB sends in the OK that completes authentication
        ctx = _context()
        packet = OkPacket.decode(_ok(
            _var('autocommit', 'ON'), _var('time_zone', 'SYSTEM'),
            _var('character_set_client', 'utf8mb4'), _var('character_set_connection', 'utf8mb4'),
            _var('character_set_results', 'utf8mb4'), _var('redirect_url', ''),
            _schema('testp'), status=constants.STATUS.AUTOCOMMIT), ctx)
        self.assertEqual(ctx.charset, 'utf8mb4')
        self.assertEqual(ctx.database, 'testp')
        self.assertTrue(packet.server_status & constants.STATUS.AUTOCOMMIT)
        self.assertTrue(ctx.server_status & constants.STATUS.AUTOCOMMIT)

    def test_charset_change_behind_another_variable_is_detected(self) -> None:
        ctx = _context()
        ctx.charset = 'utf8mb4'
        with self.assertRaises(CharsetMismatchError):
            OkPacket.decode(_ok(_var('autocommit', 'OFF'), _var('character_set_client', 'latin1')), ctx)

    def test_charset_change_to_null_is_detected(self) -> None:
        ctx = _context()
        ctx.charset = 'utf8mb4'
        null_value = _lenenc_str('character_set_client') + b'\xfb'
        with self.assertRaises(CharsetMismatchError):
            OkPacket.decode(_ok(_var('time_zone', 'UTC'),
                                _entry(constants.SESSION_TRACK.SYSTEM_VARIABLES, null_value)), ctx)

    def test_same_charset_reported_again_is_accepted(self) -> None:
        ctx = _context()
        ctx.charset = 'utf8mb4'
        OkPacket.decode(_ok(_var('autocommit', 'OFF'), _var('character_set_client', 'utf8mb4'),
                            _var('character_set_results', 'utf8mb4')), ctx)
        self.assertEqual(ctx.charset, 'utf8mb4')

    def test_schema_after_unknown_entry_type(self) -> None:
        ctx = _context()
        OkPacket.decode(_ok(_entry(0x7f, b'\x01\x02\x03'), _var('autocommit', 'ON'), _schema('other')), ctx)
        self.assertEqual(ctx.database, 'other')
        self.assertEqual(ctx.charset, '')

    def test_empty_block(self) -> None:
        ctx = _context()
        ctx.database = 'keep'
        OkPacket.decode(_ok(), ctx)
        self.assertEqual(ctx.database, 'keep')
        self.assertEqual(ctx.charset, '')


if __name__ == '__main__':
    unittest.main()
