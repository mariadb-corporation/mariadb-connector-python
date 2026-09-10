#!/usr/bin/env python -O
# -*- coding: utf-8 -*-
"""
ConnectionParams (the typed keyword contract of asyncConnect() and of the
connection classes) must stay the union of what the implementations accept,
and ConnectParams (connect()) adds the pool options connect() still routes.
Three sources of truth are compared with them:

- the fields of the pure-Python ``Configuration`` dataclass,
- the keyword list of the C extension (``dsn_keys`` in mariadb_connection.c,
  read from the source tree when it is available),
- the pool options ``connect()`` still routes for 1.1 compatibility.

Every one of those names must be a ConnectionParams key, and every
ConnectionParams key must come from one of them or be a documented extra.
"""

import dataclasses
import pathlib
import re

import pytest

from mariadb_shared.connection_params import ConnectionParams, ConnectParams
from mariadb.impl.configuration import Configuration

CONNECTION = set(ConnectionParams.__annotations__)
PARAMS = set(ConnectParams.__annotations__) | CONNECTION  # connect() accepts both

# Accepted by the implementations without being a Configuration field nor a
# C keyword: aliases resolved by both, and options handled by the C wrapper.
DOCUMENTED_EXTRAS = {
    "username", "passwd", "db",  # aliases of user / password / database
    "reconnect",                 # C wrapper: auto-reconnect
    "socket_timeout",            # C wrapper and Configuration
    "pool_name",                 # connect() routes to a named pool
}

C_SOURCE = pathlib.Path(__file__).resolve().parents[2] / "mariadb-c" / "mariadb_c" / "mariadb_connection.c"


def c_keywords() -> set[str]:
    text = C_SOURCE.read_text()
    block = re.search(r"dsn_keys\[\]\s*=\s*\{(.*?)\};", text, re.S)
    assert block, "dsn_keys[] not found in mariadb_connection.c"
    return set(re.findall(r'"([a-z_]+)"', block.group(1)))


def pool_options() -> set[str]:
    mariadb_pool = pytest.importorskip("mariadb_pool")
    return set(mariadb_pool.POOL_OPTION_NAMES)


def test_configuration_fields_are_connection_params():
    fields = {f.name for f in dataclasses.fields(Configuration)} - {"non_mapped_options"}
    assert fields <= CONNECTION, fields - CONNECTION


@pytest.mark.skipif(not C_SOURCE.exists(), reason="C extension sources not available")
def test_c_extension_keywords_are_connection_params():
    assert c_keywords() <= CONNECTION, c_keywords() - CONNECTION


def test_pool_options_are_connect_params():
    assert pool_options() <= PARAMS, pool_options() - PARAMS


def test_pool_options_do_not_overlap_the_factories_parameters():
    """The pool factories name the canonical options as parameters, so only
    the 1.1 spellings may reach them through **connection_params."""
    assert pool_options() & CONNECTION == {"pool_size", "pool_reset_connection", "pool_validation_interval"}


def test_every_param_has_a_source():
    known = {f.name for f in dataclasses.fields(Configuration)} | DOCUMENTED_EXTRAS
    if C_SOURCE.exists():
        known |= c_keywords()
    try:
        known |= pool_options()
    except pytest.skip.Exception:
        known |= {"pool_size", "min_size", "max_size", "max_idle_time", "max_lifetime", "acquire_timeout",
                  "ping_threshold", "enable_health_check", "reset_connection", "pool_reset_connection",
                  "pool_validation_interval"}
    assert PARAMS <= known, PARAMS - known
