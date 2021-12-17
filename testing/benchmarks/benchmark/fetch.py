#!/usr/bin/env python3 -O
# -*- coding: utf-8 -*-

import pyperf

def str_fetchall(loops, conn, paramstyle):
    cursor = conn.cursor()
    range_it = range(loops)
    t0 = pyperf.perf_counter()
    for value in range_it:
        cursor.execute('select col1,col2,col3 from str_test')
        row= cursor.fetchall()
        del row
    del cursor
    return pyperf.perf_counter() - t0

def str_fetchloop(loops, conn, paramstyle):
    cursor = conn.cursor()
    range_it = range(loops)
    t0 = pyperf.perf_counter()
    for value in range_it:
        cursor.execute('select col1,col2,col3 from str_test')
        row= cursor.fetchone()
        while row is not None:
            row= cursor.fetchone()
    del cursor
    return pyperf.perf_counter() - t0

def num_fetchall(loops, conn, paramstyle):
    cursor = conn.cursor()
    range_it = range(loops)
    t0 = pyperf.perf_counter()
    for value in range_it:
        cursor.execute('select col1,col2,col3,col4,col5 from num_test')
        row= cursor.fetchall()
        del row
    del cursor
    return pyperf.perf_counter() - t0

def num_fetchloop(loops, conn, paramstyle):
    cursor = conn.cursor()
    range_it = range(loops)
    t0 = pyperf.perf_counter()
    for value in range_it:
        cursor.execute('select col1,col2,col3,col4,col5 from num_test')
        row= cursor.fetchone()
        while row is not None:
            row= cursor.fetchone()
    del cursor
    return pyperf.perf_counter() - t0
