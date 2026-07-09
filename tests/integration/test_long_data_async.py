#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""
Integration tests for handling long data (>16MB) over the async client.

Async counterpart of test_long_data.py: exercises the async reader's multipart
(0xFFFFFF-fragment) reassembly and the writer's multipart splitting against a
real server, for both the text and binary (prepared) protocols. A payload above
16 MB is necessarily split into several protocol packets on the wire, so these
round-trips prove the reassembly path stays correct after the CONPY-367 changes.

Gated behind RUN_LONG_TEST=1 and a server max_allowed_packet of at least 32 MB.
"""

import os
import unittest

import mariadb
from ..base_test import varied_bytes, varied_text


class LongDataAsyncTest(unittest.IsolatedAsyncioTestCase):
    """Test handling of long (>16MB, multipart) data over async connections."""

    async def asyncSetUp(self):
        if os.environ.get('RUN_LONG_TEST') != '1':
            self.skipTest("Skipping long-running test. Set RUN_LONG_TEST=1 to run.")

        from ..conftest import get_test_config as conf
        self.connection = await mariadb.AsyncConnection.connect(**conf())
        self.cursor = self.connection.cursor()

        # A multipart payload must fit within the server's max_allowed_packet.
        await self.cursor.execute("SELECT @@max_allowed_packet")
        self.max_allowed_packet = (await self.cursor.fetchone())[0]
        self.min_required = 32 * 1024 * 1024
        if self.max_allowed_packet < self.min_required:
            self.skipTest(
                f"max_allowed_packet ({self.max_allowed_packet} bytes) is less than "
                f"required {self.min_required} bytes. "
                f"Set max_allowed_packet={self.min_required} in server config."
            )

    async def asyncTearDown(self):
        if getattr(self, 'cursor', None):
            await self.cursor.close()
        if getattr(self, 'connection', None):
            await self.connection.close()

    async def test_receive_long_varchar_text(self):
        """A >16MB LONGTEXT round-trips through the text cursor (multipart both
        directions: the INSERT payload and the SELECT row are each split)."""
        await self.cursor.execute(
            "CREATE TEMPORARY TABLE test_long_varchar_async ("
            "id INT PRIMARY KEY AUTO_INCREMENT, data LONGTEXT)")

        data_size = 17 * 1024 * 1024  # 17 MB -> 2 fragments on the wire
        test_data = varied_text(data_size)

        await self.cursor.execute(
            "INSERT INTO test_long_varchar_async (data) VALUES (?)", (test_data,))
        await self.connection.commit()

        await self.cursor.execute(
            "SELECT data FROM test_long_varchar_async WHERE id = ?", (1,))
        result = await self.cursor.fetchone()
        self.assertIsNotNone(result)
        self.assertEqual(len(result[0]), data_size)
        self.assertEqual(result[0], test_data)

    async def test_receive_long_blob_binary(self):
        """A >16MB LONGBLOB round-trips through the binary (prepared) cursor."""
        await self.cursor.execute(
            "CREATE TEMPORARY TABLE test_long_blob_async ("
            "id INT PRIMARY KEY AUTO_INCREMENT, data LONGBLOB)")

        data_size = 18 * 1024 * 1024  # 18 MB
        # Position-dependent bytes: a fragment header stamped over payload data
        # (or any misaligned copy) changes the content and fails the comparison.
        test_data = varied_bytes(data_size)

        async with self.connection.cursor(binary=True) as cursor:
            await cursor.execute(
                "INSERT INTO test_long_blob_async (data) VALUES (?)", (test_data,))
            await self.connection.commit()
            await cursor.execute(
                "SELECT data FROM test_long_blob_async WHERE id = ?", (1,))
            result = await cursor.fetchone()
        self.assertIsNotNone(result)
        self.assertEqual(len(result[0]), data_size)
        self.assertEqual(result[0], test_data)

    async def test_multiple_long_columns(self):
        """Several multi-MB columns in one row: the SELECT row aggregates well
        past 16 MB and must reassemble across fragment boundaries that fall in
        the middle of a column value."""
        await self.cursor.execute(
            "CREATE TEMPORARY TABLE test_multi_long_async ("
            "id INT PRIMARY KEY AUTO_INCREMENT, "
            "data1 LONGTEXT, data2 LONGTEXT, data3 LONGBLOB)")

        data_size = 7 * 1024 * 1024  # 3 x 7 MB row -> reassembled over 16 MB
        d1 = varied_text(data_size)
        d2 = varied_text(data_size)[::-1]
        d3 = varied_bytes(data_size)

        await self.cursor.execute(
            "INSERT INTO test_multi_long_async (data1, data2, data3) "
            "VALUES (?, ?, ?)", (d1, d2, d3))
        await self.connection.commit()

        await self.cursor.execute(
            "SELECT data1, data2, data3 FROM test_multi_long_async WHERE id = ?", (1,))
        result = await self.cursor.fetchone()
        self.assertIsNotNone(result)
        self.assertEqual(result[0], d1)
        self.assertEqual(result[1], d2)
        self.assertEqual(result[2], d3)

    async def test_long_data_with_unicode(self):
        """Multi-byte UTF-8 payload above 16 MB must survive fragment splitting
        without corrupting characters straddling a fragment boundary."""
        await self.cursor.execute(
            "CREATE TEMPORARY TABLE test_long_unicode_async ("
            "id INT PRIMARY KEY AUTO_INCREMENT, "
            "data LONGTEXT CHARACTER SET utf8mb4)")

        base = '🔥🌟💻🚀🎉' * 1000  # ~20 KB of 4-byte emoji
        reps = (17 * 1024 * 1024) // len(base.encode('utf-8'))
        test_data = base * reps

        await self.cursor.execute(
            "INSERT INTO test_long_unicode_async (data) VALUES (?)", (test_data,))
        await self.connection.commit()

        await self.cursor.execute(
            "SELECT data FROM test_long_unicode_async WHERE id = ?", (1,))
        result = await self.cursor.fetchone()
        self.assertIsNotNone(result)
        self.assertEqual(result[0], test_data)


if __name__ == '__main__':
    unittest.main()
