#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""
CONPY-377: a server (or a proxy in the middle) announcing an oversized column
count for a result set must be rejected before the column metadata is
allocated, so it can't drive the client into an out-of-memory condition.

The enforcement tests drive the pure-Python client against the in-process wire
fake server. With the C extension the limit is enforced by libmariadb through
MARIADB_OPT_MAX_COLUMNS (Connector/C 3.3.20 / 3.4.10 or newer), so only the option
plumbing is
checked there.
"""

import unittest

import pytest

import mariadb
from mariadb.impl.configuration import Configuration
from tests.base_test import is_native
from tests.unit._fakeserver import (
    FakeServer, scripted_handler, query_text, fake_conf, lenenc_int, pkt,
    text_resultset, ok, MYSQL_TYPE_VAR_STRING,
)

_MARKER = "fake_table_marker"

py_only = pytest.mark.skipif(
    not is_native(),
    reason="pure-Python enforcement; the C extension relies on "
           "MARIADB_OPT_MAX_COLUMNS in libmariadb")


def _announce_columns(column_count):
    """Reply to the marker query with a column count only, no column packets.

    A client that trusts the count allocates the metadata of column_count
    columns before reading a single column definition packet.
    """
    def on_query(payload):
        if _MARKER in query_text(payload):
            return pkt(1, lenenc_int(column_count))
        return ok()
    return on_query


# Highest count a server can actually announce: a length encoded integer of
# 2**24 or more starts with 0xFE, which is read as an EOF packet instead of a
# result-set header. 2**23 columns would still allocate over a GB of metadata.
_HUGE = (1 << 23) - 1


@py_only
def test_oversized_column_count_rejected():
    with FakeServer(scripted_handler(on_query=_announce_columns(_HUGE))) as s:
        con = mariadb.connect(**fake_conf(s.port))
        cur = con.cursor()
        with pytest.raises(mariadb.OperationalError) as exc:
            cur.execute(f"SELECT * FROM {_MARKER}")
        assert "max_allowed_columns" in str(exc.value)
        assert str(_HUGE) in str(exc.value)
        # the announced column packets were never read, so the connection is
        # desynchronized and must not be reused
        with pytest.raises(mariadb.Error):
            cur.execute("SELECT 1")


@py_only
def test_default_limit_is_64k():
    assert Configuration().max_allowed_columns == 65535
    with FakeServer(scripted_handler(on_query=_announce_columns(65536))) as s:
        con = mariadb.connect(**fake_conf(s.port))
        with pytest.raises(mariadb.OperationalError) as exc:
            con.cursor().execute(f"SELECT * FROM {_MARKER}")
        assert "65535" in str(exc.value)


@py_only
def test_limit_can_be_lowered():
    with FakeServer(scripted_handler(on_query=_announce_columns(11))) as s:
        con = mariadb.connect(**fake_conf(s.port, max_allowed_columns=10))
        with pytest.raises(mariadb.OperationalError) as exc:
            con.cursor().execute(f"SELECT * FROM {_MARKER}")
        assert "(11)" in str(exc.value) and "(10)" in str(exc.value)


@py_only
def test_column_count_within_limit_is_accepted():
    columns = [("a", MYSQL_TYPE_VAR_STRING), ("b", MYSQL_TYPE_VAR_STRING)]

    def on_query(payload):
        if _MARKER in query_text(payload):
            return text_resultset(columns, [("1", "x")])
        return ok()

    with FakeServer(scripted_handler(on_query=on_query)) as s:
        con = mariadb.connect(**fake_conf(s.port, max_allowed_columns=2))
        cur = con.cursor()
        cur.execute(f"SELECT * FROM {_MARKER}")
        assert cur.fetchall() == [("1", "x")]
        con.close()


@unittest.skipIf(not is_native(),
                 "pure-Python enforcement; the C extension relies on "
                 "MARIADB_OPT_MAX_COLUMNS in libmariadb")
class TestMaxAllowedColumnsAsync(unittest.IsolatedAsyncioTestCase):
    async def test_oversized_column_count_rejected_async(self):
        with FakeServer(scripted_handler(on_query=_announce_columns(_HUGE))) as s:
            con = await mariadb.asyncConnect(**fake_conf(s.port))
            cur = con.cursor()
            with self.assertRaises(mariadb.OperationalError) as ctx:
                await cur.execute(f"SELECT * FROM {_MARKER}")
            self.assertIn("max_allowed_columns", str(ctx.exception))

    async def test_column_count_within_limit_is_accepted_async(self):
        columns = [("a", MYSQL_TYPE_VAR_STRING)]

        def on_query(payload):
            if _MARKER in query_text(payload):
                return text_resultset(columns, [("1",)])
            return ok()

        with FakeServer(scripted_handler(on_query=on_query)) as s:
            con = await mariadb.asyncConnect(
                **fake_conf(s.port, max_allowed_columns=1))
            cur = con.cursor()
            await cur.execute(f"SELECT * FROM {_MARKER}")
            self.assertEqual(await cur.fetchall(), [("1",)])
            await con.close()


class TestMaxAllowedColumnsOption(unittest.TestCase):
    """Option plumbing (no server involved)."""

    def test_option_is_parsed(self):
        # string form, as an option file or a connection URI provides it
        self.assertEqual(
            Configuration.from_dict({'max_allowed_columns': '100'}
                                    ).max_allowed_columns, 100)
        self.assertEqual(
            Configuration.from_dict({'max_allowed_columns': 100}
                                    ).max_allowed_columns, 100)

    @unittest.skipIf(is_native(), "C extension only: PyArg 'I'/'i' conversion")
    def test_non_positive_limit_rejected_by_c_extension(self):
        # a negative value must not be converted to 4294967295, which would
        # disable the limit in libmariadb; rejected before connecting
        for invalid in (0, -1):
            with self.assertRaises(mariadb.ProgrammingError):
                mariadb.connect(host="127.0.0.1", port=1, user="u",
                                max_allowed_columns=invalid)
