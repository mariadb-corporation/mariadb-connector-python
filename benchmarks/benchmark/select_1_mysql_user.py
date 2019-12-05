#!/usr/bin/env python3 -O
# -*- coding: utf-8 -*-

import pyperf


def select_1_mysql_user(loops, conn):
    range_it = range(loops)
    t0 = pyperf.perf_counter()
    cursor = conn.cursor()
    for value in range_it:
        cursor.execute("select * from mysql.user LIMIT 1")
        row = cursor.fetchall()
    del cursor

    return pyperf.perf_counter() - t0
