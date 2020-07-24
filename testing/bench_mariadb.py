#!/usr/bin/env python3 -O
# -*- coding: utf-8 -*-

# requirement: pip install pyperf

import importlib 

from benchmarks.internal_bench import test_suite
from benchmarks.internal_bench import run_test
from test.conf_test import conf

import os

module= os.environ.get('TEST_MODULE', 'mariadb'),
dbdrv = importlib.import_module(module[0])


def main():
    default_conf = conf()
    conn = dbdrv.connect(**default_conf)
    run_test(test_suite(), conn)
    conn.close()

if __name__ == "__main__":
    main()
