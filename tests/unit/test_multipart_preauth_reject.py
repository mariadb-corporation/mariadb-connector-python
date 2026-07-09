#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""
CONPY-367: multipart (>16 MB) packets must be rejected before authentication.

Reader.read_payload() reassembles multipart packets by growing the receive
buffer for every 0xffffff-length fragment. Before authentication no legitimate
packet is anywhere near 16 MB, so a max-length (multipart) frame at that stage
can only be a rogue/MitM server streaming endless fragments to drive the client
to OutOfMemory. The client must refuse such a frame *before* allocating it,
rather than reassembling it.
"""

import struct
import unittest

import pytest

import mariadb
from tests.base_test import is_native
from tests.unit._fakeserver import FakeServer, fake_conf

# The guard lives in the pure-Python Reader.read_payload(); the C extension
# (libmariadb) has its own equivalent, so run these only on the native impl.
py_only = pytest.mark.skipif(not is_native(),
                             reason="pure-Python multipart pre-auth guard (CONPY-367)")


_MAX = 0xFFFFFF  # 16 MB - 1: the "more fragments follow" fragment length


def _rogue_multipart_handshake(conn):
    """Send, as the very first (handshake, seq 0) packet, a full max-length
    (0xFFFFFF) fragment -> the protocol's "more fragments follow" marker, plus the
    header of a second fragment. The client buffers the one 16 MB fragment, then
    on seeing the continuation refuses before reassembling any more; an unguarded
    client would keep growing its buffer with every further fragment."""
    conn.sendall(struct.pack("<I", _MAX))          # frag 1 header: len=0xFFFFFF, seq 0
    conn.sendall(b"\x00" * _MAX)                    # frag 1 payload: a full 16 MB
    # Header of frag 2 (the client pre-fetches these 4 bytes, then rejects). A
    # short/failed write past here is expected once it drops the connection.
    try:
        conn.sendall(struct.pack("<I", _MAX | (1 << 24)))
        conn.sendall(b"\x00" * 65536)
    except OSError:
        pass


@py_only
class MultipartPreAuthRejectTest(unittest.TestCase):
    def test_sync_rejects_multipart_before_auth(self):
        with FakeServer(_rogue_multipart_handshake) as s:
            with self.assertRaises(mariadb.OperationalError) as ctx:
                mariadb.connect(**fake_conf(s.port))
        self.assertIn("multipart", str(ctx.exception).lower())


@py_only
class MultipartPreAuthRejectAsyncTest(unittest.IsolatedAsyncioTestCase):
    async def test_async_rejects_multipart_before_auth(self):
        with FakeServer(_rogue_multipart_handshake) as s:
            with self.assertRaises(mariadb.OperationalError) as ctx:
                await mariadb.asyncConnect(**fake_conf(s.port))
        self.assertIn("multipart", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
