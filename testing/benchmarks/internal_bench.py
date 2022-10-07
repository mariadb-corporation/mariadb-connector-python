#!/usr/bin/env python3 -O
# -*- coding: utf-8 -*-

import pyperf
import os

from benchmarks.benchmark.bulk import bulk
from benchmarks.benchmark.do_1 import do1
from benchmarks.benchmark.select_1 import select_1
from benchmarks.benchmark.do_1000_param import do_1000_param
from benchmarks.benchmark.select_100_cols import select_100_cols, select_100_cols_execute
from benchmarks.benchmark.select_1000_rows import select_1000_rows


def run_test(tests, conn, paramstyle):
    runner = pyperf.Runner(warmups=1000, processes=1, min_time=10)
    for test in tests:
        runner.bench_time_func(test['label'], test['method'], conn, paramstyle)

def test_suite(paramstyle):
    ts = [
        {'label': 'BULK Insert',
                  'method': bulk},
        {'label': 'DO 1',
                  'method': do1},
        {'label': 'DO 1000 params',
                  'method': do_1000_param},
        {'label': 'select_100_cols',
                  'method': select_100_cols},
        {'label': 'select 1', 'method': select_1},
        {'label': 'select_1000_rows', 'method': select_1000_rows},
    ]
    if paramstyle == 'qmark':
        ts.append({'label': 'select_100_cols_execute', 'method': select_100_cols_execute})
    return ts
