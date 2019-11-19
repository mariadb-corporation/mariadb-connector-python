#!/usr/bin/env python3 -O
# -*- coding: utf-8 -*-

import pyperf


def select_param(loops, conn):
    cursor = conn.cursor()
    range_it = range(loops)
    t0 = pyperf.perf_counter()
    for value in range_it:
        cursor.execute("select %(val)s", {'val': 1})
        row = cursor.fetchall()
    cursor.close()
    return pyperf.perf_counter() - t0