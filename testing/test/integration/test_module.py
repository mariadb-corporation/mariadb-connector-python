#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

import unittest

import mariadb

from test.base_test import create_connection


class TestConnection(unittest.TestCase):

    def setUp(self):
        self.connection = create_connection()

    def tearDown(self):
        del self.connection

    def test_conpy_63(self):
        version = mariadb.__version__
        version_info = mariadb.__version_info__

        str_version = list(map(str, version.split('.')))

        self.assertEqual(int(str_version[0]), version_info[0])
        self.assertEqual(int(str_version[1]), version_info[1])

        # patch might contain letters
        try:
            self.assertEqual(int(str_version[2]), version_info[2])
        except Exception:
            self.assertEqual(str_version[2], version_info[2])


if __name__ == '__main__':
    unittest.main()
