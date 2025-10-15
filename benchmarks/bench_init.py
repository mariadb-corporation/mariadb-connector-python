#!/usr/bin/env python3 -O
# -*- coding: utf-8 -*-

# requirement: pip install pyperf

import importlib

from test.conf_test import conf, glob
from benchmarks.setup_db import init_db

module = glob()
dbdrv = importlib.import_module(module["module"])


def main():
    default_conf = conf()
    conn = dbdrv.connect(**default_conf)
    init_db(conn, dbdrv.paramstyle)
    conn.close()


if __name__ == "__main__":
    main()
