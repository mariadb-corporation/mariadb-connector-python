#!/usr/bin/env python3 -O
# -*- coding: utf-8 -*-

# requirement: pip install MySQL-pythonmysql-connector-python pyperf

import mysql.connector

from benchmarks.internal_bench import test_suite
from benchmarks.internal_bench import run_test
from test.conf_test import conf


def main():
    default_conf = conf()
    conn = mysql.connector.connect(**default_conf)
    run_test(test_suite(), conn)
    conn.close()

if __name__ == "__main__":
    main()