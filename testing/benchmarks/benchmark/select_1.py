#!/usr/bin/env python3 -O
# -*- coding: utf-8 -*-

import pyperf


def select_1(loops, conn, paramstyle):
    cursor = conn.cursor()
    range_it = range(loops)
    t0 = pyperf.perf_counter()
    for value in range_it:
        cursor = conn.cursor()
        cursor.execute("select 1")
        rows = cursor.fetchall()
        del rows
        cursor.close()

    return pyperf.perf_counter() - t0
