#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

import re
import unittest

import mariadb

from test.base_test import create_connection


class TestConnection(unittest.TestCase):

    def setUp(self):
        self.connection = create_connection()

    def tearDown(self):
        del self.connection

    def test_conpy_63(self):
        """__version__ and __version_info__ describe the same release.

        The string follows PEP 440: "1.1.15", or "1.1.15b1" for a
        pre-release, in which case __version_info__ carries the segment and
        its number as two extra members: (1, 1, 15, 'b', 1).
        """
        version = mariadb.__version__
        version_info = mariadb.__version_info__

        match = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)(?:([a-z]+)(\d+))?', version)
        self.assertIsNotNone(match, version)
        major, minor, patch, segment, number = match.groups()

        self.assertEqual(int(major), version_info[0])
        self.assertEqual(int(minor), version_info[1])
        self.assertEqual(int(patch), version_info[2])
        if segment is None:
            self.assertEqual(len(version_info), 3)
        else:
            self.assertEqual(segment, version_info[3])
            self.assertEqual(int(number), version_info[4])


if __name__ == '__main__':
    unittest.main()
