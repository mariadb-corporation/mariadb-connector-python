#!/usr/bin/env python3 -O
# -*- coding: utf-8 -*-

import pyperf
import random

chars = [ "1", "2", "3", "4", "5", "6", "7", "8", "9", "a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m", "n", "o", "p", "\\Z", "😎", "🌶", "🎤", "🥂" ]

def randomString(length):
    result = "";
    for value in range(length):
        result = result + chars[random.randint(0, (len(chars) - 1))]
    return result;


def bulk(loops, conn, paramstyle):

#    conn.autocommit= False
    t0 = pyperf.perf_counter()
    s = randomString(100)
    vals = [(s,) for i in range(100)]

    range_it = range(loops)
    for value in range_it:
        cursor = conn.cursor()
        if paramstyle == 'qmark':
            cursor.executemany("INSERT INTO perfTestTextBatch(t0) VALUES (?)",
                               vals)
        else:
            cursor.executemany("INSERT INTO perfTestTextBatch(t0) VALUES (%s)",
                               vals)
        del cursor

    return pyperf.perf_counter() - t0
