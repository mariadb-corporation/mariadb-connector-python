#!/usr/bin/env python -O
# -*- coding: utf-8 -*-
import os

import mariadb

from .conf_test import conf


def is_skysql():
    if conf()["host"][-13:] == "db.skysql.net":
        return True
    return False


def is_maxscale():
    return os.environ.get('srv') == "maxscale" or os.environ.get('srv') == 'skysql-ha'

def is_mysql():
    mysql_server = 1
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute("select version()")
    row = cursor.fetchone()
    if "MARIADB" in row[0].upper():
        mysql_server = 0
    del cursor, conn
    return mysql_server

def create_connection(additional_conf=None):
    default_conf = conf()
    if additional_conf is None:
        c = {key: value for (key, value) in (default_conf.items())}
    else:
        c = {key: value for (key, value) in (list(default_conf.items()) + list(
            additional_conf.items()))}
    return mariadb.connect(**c)
