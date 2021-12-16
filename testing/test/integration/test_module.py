#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

import os
import unittest

import mariadb

from test.base_test import create_connection
from test.conf_test import conf
import platform


class TestConnection(unittest.TestCase):

    def setUp(self):
        self.connection = create_connection()

    def tearDown(self):
        del self.connection

    def test_conpy_63(self):
        version = mariadb.__version__
        version_info = mariadb.__version_info__

        num_version = list(map(int, version.split('.')))

        self.assertEqual(num_version[0], version_info[0])
        self.assertEqual(num_version[1], version_info[1])
        self.assertEqual(num_version[2], version_info[2])
        self.assertEqual(0, version_info[4])


if __name__ == '__main__':
    unittest.main()
