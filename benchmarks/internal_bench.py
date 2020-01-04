#!/usr/bin/env python3 -O
# -*- coding: utf-8 -*-

import pyperf

from benchmarks.benchmark.do_1 import do1
from benchmarks.benchmark.select_1 import select_1
from benchmarks.benchmark.select_param import select_param
from benchmarks.benchmark.select_10_cols_from_seq_1_to_10000 import \
    select_10_cols_from_seq_1_to_10000
from benchmarks.benchmark.select_1_mysql_user import select_1_mysql_user
from benchmarks.benchmark.bulk import bulk


def run_test(tests, conn):
    runner = pyperf.Runner()
    for test in tests:
        runner.bench_time_func(test['label'], test['method'], conn)


def test_suite():
    return [
        {'label': 'do 1', 'method': do1},
        {'label': 'select 1', 'method': select_1},
        {'label': 'select param', 'method': select_param},
        {'label': 'select 1 mysql user', 'method': select_1_mysql_user},
        {'label': 'bulk: insert/update/delete', 'method': bulk},
        {'label': 'Select <10 cols of 100 chars> from_seq_1_to_100000', 'method':
            select_10_cols_from_seq_1_to_10000}
    ]
