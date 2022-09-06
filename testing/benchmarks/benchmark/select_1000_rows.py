#!/usr/bin/env python3 -O
# -*- coding: utf-8 -*-

import pyperf


def select_1000_rows(loops, conn, paramstyle):
    range_it = range(loops)
    t0 = pyperf.perf_counter()
    for value in range_it:
        cursor = conn.cursor()
        cursor.execute("select seq, 'abcdefghijabcdefghijabcdefghijaa' from seq_1_to_1000")
        rows = cursor.fetchall()
        del cursor, rows
    return pyperf.perf_counter() - t0
