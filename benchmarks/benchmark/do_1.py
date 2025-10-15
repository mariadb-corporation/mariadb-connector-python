#!/usr/bin/env python3 -O
# -*- coding: utf-8 -*-

import pyperf


def do1(loops, conn, paramstyle):
    range_it = range(loops)

    t0 = pyperf.perf_counter()
    for value in range_it:
        cursor = conn.cursor()
        cursor.execute('do 1')
        del cursor
    return pyperf.perf_counter() - t0
