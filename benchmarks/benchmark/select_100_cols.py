#!/usr/bin/env python3 -O
# -*- coding: utf-8 -*-

import pyperf


def select_100_cols(loops, conn, paramstyle):
    range_it = range(loops)
    t0 = pyperf.perf_counter()
    for value in range_it:
        cursor = conn.cursor()
        cursor.execute("select * FROM test100")
        rows = cursor.fetchall()
        del cursor, rows
    return pyperf.perf_counter() - t0

def select_100_cols_execute(loops, conn, paramstyle):
    range_it = range(loops)
    t0 = pyperf.perf_counter()
    for value in range_it:
        cursor = conn.cursor(binary=True)
        cursor.execute("select * FROM test100 WHERE 1 = ?", (1,))
        rows = cursor.fetchall()
        del cursor, rows
    return pyperf.perf_counter() - t0
