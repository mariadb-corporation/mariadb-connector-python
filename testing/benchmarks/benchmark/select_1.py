#!/usr/bin/env python3 -O
# -*- coding: utf-8 -*-

import pyperf


def select_1(loops, conn, paramstyle):
    cursor = conn.cursor()
    range_it = range(loops)
    t0 = pyperf.perf_counter()
    for value in range_it:
        cursor.execute("select 1")
        row = cursor.fetchall()
    cursor.close()

    return pyperf.perf_counter() - t0
