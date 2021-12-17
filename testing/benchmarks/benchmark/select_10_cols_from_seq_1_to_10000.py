#!/usr/bin/env python3 -O
# -*- coding: utf-8 -*-

import pyperf

request = "SELECT "

for i in range(0, 10):
    if i == 0:
        request += " REPEAT('a', 100)"
    else:
        request += ", REPEAT('a', 100)"

request += " from seq_1_to_10000"


def select_10_cols_from_seq_1_to_10000(loops, conn, paramstyle):
    cursor = conn.cursor()
    range_it = range(loops)
    t0 = pyperf.perf_counter()
    for value in range_it:
        cursor.execute(request)
        row = cursor.fetchall()
    cursor.close()

    return pyperf.perf_counter() - t0
