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


def is_xpand():
    if os.environ.get('srv') == "xpand":
        return True
    conn = create_connection()
    version = conn.get_server_version()
    del conn
    return "Xpand" in version

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
    conn = mariadb.connect(**c)
    version = conn.get_server_version()
    # https://jira.mariadb.org/browse/XPT-266
    if "Xpand" in version or os.environ.get('srv') == "xpand":
        cursor = conn.cursor()
        cursor.execute("SET NAMES UTF8")
        del cursor
    return conn
