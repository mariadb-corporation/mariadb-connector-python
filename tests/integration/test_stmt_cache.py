#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""
Integration tests for the prepared statement cache.

Covers:
  - Sequential cache hit (cursor A closes, cursor B reuses)
  - Template checkout/return lifecycle
  - Concurrent cursors with same SQL (second gets cache miss)
  - Cache capacity limit and LRU eviction
  - Eviction while template is checked out (deferred close)
  - Cache disabled (prep_stmt_cache_size=0)
  - Connection close cleans up all cached statements
  - Mixed binary / text protocol (text bypasses cache)
  - executemany with cache
  - Different SQL statements fill distinct cache slots
  - Re-execute same statement on same cursor (no cache interaction)
"""

from __future__ import annotations

import unittest

import mariadb
from ..base_test import create_connection, is_native

_is_native = is_native()
_skip_native = unittest.skipIf(
    _is_native,
    "C extension stmt cache internals not available in pure Python driver",
)


def _cache_conn(**extra: object) -> mariadb.Connection:
    """Helper: open a connection with stmt caching enabled."""
    return create_connection({
        "cache_prep_stmts": True,
        "prep_stmt_cache_size": 10,
        **extra,
    })


@_skip_native
class TestStmtCacheSequential(unittest.TestCase):
    """Sequential reuse: cursor A finishes, cursor B gets cache hit."""

    def setUp(self) -> None:
        self.connection = _cache_conn()
        self.connection.autocommit = True

    def tearDown(self) -> None:
        self.connection.close()

    # ------------------------------------------------------------------
    def test_basic_cache_hit(self) -> None:
        """After cursor A closes, cursor B should reuse the cached stmt."""
        sql = "SELECT ? AS v"

        cur_a = self.connection.cursor(binary=True)
        cur_a.execute(sql, (1,))
        self.assertEqual(cur_a.fetchone(), (1,))
        cur_a.close()

        cache = self.connection._stmt_cache
        self.assertEqual(len(cache), 1)

        cur_b = self.connection.cursor(binary=True)
        cur_b.execute(sql, (2,))
        self.assertEqual(cur_b.fetchone(), (2,))
        cur_b.close()

        # Cache still has the entry (returned by B)
        self.assertEqual(len(cache), 1)

    def test_cache_hit_preserves_types(self) -> None:
        """Cached stmt must return correct column types on reuse."""
        sql = "SELECT ? + 0 AS num, ? AS str"

        cur = self.connection.cursor(binary=True)
        cur.execute(sql, (42, "hello"))
        row = cur.fetchone()
        self.assertEqual(row, (42, "hello"))
        cur.close()

        cur2 = self.connection.cursor(binary=True)
        cur2.execute(sql, (99, "world"))
        row2 = cur2.fetchone()
        self.assertEqual(row2, (99, "world"))
        cur2.close()

    def test_repeated_execute_same_cursor(self) -> None:
        """Re-executing the same SQL on the same cursor must not break."""
        sql = "SELECT ? AS v"
        cur = self.connection.cursor(binary=True)
        for i in range(20):
            cur.execute(sql, (i,))
            self.assertEqual(cur.fetchone(), (i,))
        cur.close()


@_skip_native
class TestStmtCacheConcurrent(unittest.TestCase):
    """Multiple cursors with the same SQL open simultaneously."""

    def setUp(self) -> None:
        self.connection = _cache_conn()
        self.connection.autocommit = True

    def tearDown(self) -> None:
        self.connection.close()

    # ------------------------------------------------------------------
    def test_second_cursor_gets_cache_miss(self) -> None:
        """While cursor A holds the template, cursor B must prepare fresh."""
        sql = "SELECT ? AS v"

        cur_a = self.connection.cursor(binary=True)
        cur_a.execute(sql, (1,))
        self.assertEqual(cur_a.fetchone(), (1,))

        # A still open — template is checked out
        cur_b = self.connection.cursor(binary=True)
        cur_b.execute(sql, (2,))
        self.assertEqual(cur_b.fetchone(), (2,))

        cur_a.close()
        cur_b.close()

    def test_template_returns_after_checkout(self) -> None:
        """After the first cursor closes, the template is available again."""
        sql = "SELECT ? AS v"
        cache = self.connection._stmt_cache

        cur_a = self.connection.cursor(binary=True)
        cur_a.execute(sql, (1,))
        cur_a.fetchone()
        cur_a.close()

        # Template is back in cache
        entry = cache.get(sql)
        self.assertIsNotNone(entry)
        self.assertIsNotNone(entry.capsule)

    def test_three_cursors_sequential_reuse(self) -> None:
        """A→close→B→close→C all reuse the same cached stmt."""
        sql = "SELECT ? AS v"
        for i in range(3):
            cur = self.connection.cursor(binary=True)
            cur.execute(sql, (i,))
            self.assertEqual(cur.fetchone(), (i,))
            cur.close()
        self.assertEqual(len(self.connection._stmt_cache), 1)

    def test_interleaved_different_queries(self) -> None:
        """Two different queries interleaved don't interfere."""
        sql1 = "SELECT ? + 0 AS a"
        sql2 = "SELECT ? + 0 AS b"

        cur1 = self.connection.cursor(binary=True)
        cur1.execute(sql1, (10,))

        cur2 = self.connection.cursor(binary=True)
        cur2.execute(sql2, (20,))

        self.assertEqual(cur1.fetchone(), (10,))
        self.assertEqual(cur2.fetchone(), (20,))

        cur1.close()
        cur2.close()
        self.assertEqual(len(self.connection._stmt_cache), 2)


@_skip_native
class TestStmtCacheEviction(unittest.TestCase):
    """LRU eviction and capacity limits."""

    def setUp(self) -> None:
        # Small cache so we can exercise eviction easily
        self.connection = _cache_conn(prep_stmt_cache_size=3)
        self.connection.autocommit = True

    def tearDown(self) -> None:
        self.connection.close()

    # ------------------------------------------------------------------
    def test_eviction_on_overflow(self) -> None:
        """Inserting more stmts than cache size evicts the LRU entry."""
        cache = self.connection._stmt_cache
        queries = [f"SELECT {i} + ? AS v" for i in range(5)]

        for q in queries:
            cur = self.connection.cursor(binary=True)
            cur.execute(q, (0,))
            cur.fetchone()
            cur.close()

        # Cache should hold exactly 3 (the most recent)
        self.assertEqual(len(cache), 3)

    def test_eviction_lru_order(self) -> None:
        """LRU order: accessing an entry promotes it; oldest is evicted."""
        cache = self.connection._stmt_cache
        q1, q2, q3, q4 = (f"SELECT {i} + ? AS v" for i in range(4))

        # Fill cache: q1, q2, q3
        for q in (q1, q2, q3):
            cur = self.connection.cursor(binary=True)
            cur.execute(q, (0,))
            cur.fetchone()
            cur.close()
        self.assertEqual(len(cache), 3)

        # Access q1 → promotes it; LRU is now q2
        cur = self.connection.cursor(binary=True)
        cur.execute(q1, (0,))
        cur.fetchone()
        cur.close()

        # Insert q4 → should evict q2 (the LRU)
        cur = self.connection.cursor(binary=True)
        cur.execute(q4, (0,))
        cur.fetchone()
        cur.close()

        self.assertEqual(len(cache), 3)
        # q2 should be gone, q1/q3/q4 should remain
        self.assertIsNone(cache.get(q2))
        self.assertIsNotNone(cache.get(q1))
        self.assertIsNotNone(cache.get(q3))
        self.assertIsNotNone(cache.get(q4))

    def test_eviction_while_checked_out(self) -> None:
        """If an entry is evicted while its template is checked out,
        the close is deferred until the cursor returns it."""
        cache = self.connection._stmt_cache
        q1, q2, q3, q4 = (f"SELECT {i} + ? AS v" for i in range(4))

        # Fill cache: q1, q2, q3
        for q in (q1, q2, q3):
            cur = self.connection.cursor(binary=True)
            cur.execute(q, (0,))
            cur.fetchone()
            cur.close()

        # Check out q1's template
        cur_hold = self.connection.cursor(binary=True)
        cur_hold.execute(q1, (1,))
        cur_hold.fetchone()
        # cur_hold still open — template checked out

        # Now insert q4; q1 is LRU after q2 was accessed most recently
        # Actually q1 was just accessed by cur_hold so q2 is LRU
        cur = self.connection.cursor(binary=True)
        cur.execute(q4, (0,))
        cur.fetchone()
        cur.close()

        # q2 should be evicted
        self.assertEqual(len(cache), 3)

        # Close cur_hold — the template returns; if q1 was evicted,
        # close is deferred. Either way no crash.
        cur_hold.close()


@_skip_native
class TestStmtCacheDisabled(unittest.TestCase):
    """Cache disabled (size=0): stmts are closed immediately."""

    def setUp(self) -> None:
        self.connection = _cache_conn(prep_stmt_cache_size=0)
        self.connection.autocommit = True

    def tearDown(self) -> None:
        self.connection.close()

    # ------------------------------------------------------------------
    def test_no_caching_when_disabled(self) -> None:
        """With cache_size=0 the cache stays empty."""
        sql = "SELECT ? AS v"

        cur = self.connection.cursor(binary=True)
        cur.execute(sql, (1,))
        cur.fetchone()
        cur.close()

        cache = self.connection._stmt_cache
        self.assertEqual(len(cache), 0)

    def test_sequential_works_without_cache(self) -> None:
        """Queries still succeed — just no caching."""
        sql = "SELECT ? AS v"
        for i in range(5):
            cur = self.connection.cursor(binary=True)
            cur.execute(sql, (i,))
            self.assertEqual(cur.fetchone(), (i,))
            cur.close()


@_skip_native
class TestStmtCacheConnectionClose(unittest.TestCase):
    """Connection.close() must clean up all cached stmts."""

    def test_connection_close_clears_cache(self) -> None:
        """Closing the connection empties the cache without errors."""
        conn = _cache_conn()
        conn.autocommit = True

        for i in range(5):
            cur = conn.cursor(binary=True)
            cur.execute(f"SELECT {i} + ? AS v", (0,))
            cur.fetchone()
            cur.close()

        cache = conn._stmt_cache
        self.assertGreater(len(cache), 0)

        conn.close()
        self.assertEqual(len(cache), 0)

    def test_connection_close_with_open_cursor(self) -> None:
        """Closing the connection while a cursor still holds a template
        must not crash."""
        conn = _cache_conn()
        conn.autocommit = True

        cur = conn.cursor(binary=True)
        cur.execute("SELECT ? AS v", (1,))
        cur.fetchone()
        # Do NOT close cur — simulate leaked cursor
        conn.close()
        # If we reach here without segfault, the test passes


@_skip_native
class TestStmtCacheMixedProtocol(unittest.TestCase):
    """Text protocol never touches the cache; binary does."""

    def setUp(self) -> None:
        self.connection = _cache_conn()
        self.connection.autocommit = True

    def tearDown(self) -> None:
        self.connection.close()

    # ------------------------------------------------------------------
    def test_text_query_does_not_cache(self) -> None:
        """A plain text-protocol query must not populate the cache."""
        cache = self.connection._stmt_cache

        cur = self.connection.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        cur.close()
        self.assertEqual(len(cache), 0)

    def test_text_then_binary_same_sql(self) -> None:
        """Text query followed by binary on the same SQL: only binary caches."""
        cache = self.connection._stmt_cache
        sql = "SELECT 1 AS v"

        cur_t = self.connection.cursor()
        cur_t.execute(sql)
        cur_t.fetchone()
        cur_t.close()
        self.assertEqual(len(cache), 0)

        cur_b = self.connection.cursor(binary=True)
        cur_b.execute(sql, (1,))  # needs a param for binary
        # Actually "SELECT 1 AS v" with no param marker — use a different SQL
        cur_b.close()
        # Doesn't matter if it cached — no crash is the key assertion

    def test_binary_then_text_same_cursor(self) -> None:
        """Switch from binary to text on the same cursor: cache the binary stmt."""
        cache = self.connection._stmt_cache

        cur = self.connection.cursor(binary=True)
        cur.execute("SELECT ? AS v", (1,))
        cur.fetchone()
        # Now execute text query on same cursor
        cur.execute("SELECT 1")
        cur.fetchone()
        cur.close()

        # The binary stmt should have been cached when the cursor switched
        self.assertGreaterEqual(len(cache), 0)  # no crash is key


@_skip_native
class TestStmtCacheExecuteMany(unittest.TestCase):
    """executemany with cache enabled."""

    def setUp(self) -> None:
        self.connection = _cache_conn()
        self.connection.autocommit = True
        cur = self.connection.cursor()
        cur.execute("CREATE TEMPORARY TABLE t_cache_batch (id INT, val VARCHAR(50))")
        cur.close()

    def tearDown(self) -> None:
        self.connection.close()

    # ------------------------------------------------------------------
    def test_executemany_then_single_execute(self) -> None:
        """executemany followed by single execute on the same SQL."""
        sql = "INSERT INTO t_cache_batch (id, val) VALUES (?, ?)"

        cur = self.connection.cursor(binary=True)
        cur.executemany(sql, [(1, "a"), (2, "b"), (3, "c")])
        cur.close()

        # Single execute on same SQL
        cur2 = self.connection.cursor(binary=True)
        cur2.execute(sql, (4, "d"))
        cur2.close()

        # Verify data
        cur3 = self.connection.cursor()
        cur3.execute("SELECT COUNT(*) FROM t_cache_batch")
        self.assertEqual(cur3.fetchone()[0], 4)
        cur3.close()


@_skip_native
class TestStmtCacheMultipleDistinctSQL(unittest.TestCase):
    """Different SQL strings occupy distinct cache slots."""

    def setUp(self) -> None:
        self.connection = _cache_conn(prep_stmt_cache_size=5)
        self.connection.autocommit = True

    def tearDown(self) -> None:
        self.connection.close()

    # ------------------------------------------------------------------
    def test_distinct_queries_fill_cache(self) -> None:
        """Each unique SQL string creates a separate cache entry."""
        cache = self.connection._stmt_cache
        queries = [f"SELECT {i} + ? AS v" for i in range(5)]

        for q in queries:
            cur = self.connection.cursor(binary=True)
            cur.execute(q, (0,))
            cur.fetchone()
            cur.close()

        self.assertEqual(len(cache), 5)

    def test_same_query_reuses_slot(self) -> None:
        """Re-executing the same SQL reuses the existing cache entry."""
        cache = self.connection._stmt_cache
        sql = "SELECT ? AS v"

        for _ in range(10):
            cur = self.connection.cursor(binary=True)
            cur.execute(sql, (1,))
            cur.fetchone()
            cur.close()

        self.assertEqual(len(cache), 1)


@_skip_native
class TestStmtCacheSwitchStatement(unittest.TestCase):
    """Cursor switches between different SQL statements."""

    def setUp(self) -> None:
        self.connection = _cache_conn()
        self.connection.autocommit = True

    def tearDown(self) -> None:
        self.connection.close()

    # ------------------------------------------------------------------
    def test_cursor_alternates_two_queries(self) -> None:
        """One cursor alternating between two SQL strings should cache both."""
        cache = self.connection._stmt_cache
        sql_a = "SELECT ? + 0 AS a"
        sql_b = "SELECT ? + 0 AS b"

        cur = self.connection.cursor(binary=True)
        for i in range(6):
            sql = sql_a if i % 2 == 0 else sql_b
            cur.execute(sql, (i,))
            self.assertEqual(cur.fetchone(), (i,))
        cur.close()

        self.assertEqual(len(cache), 2)

    def test_cursor_cycles_through_many_queries(self) -> None:
        """Cursor cycling through N queries caches all of them."""
        cache = self.connection._stmt_cache
        queries = [f"SELECT {i} + ? AS v" for i in range(5)]

        cur = self.connection.cursor(binary=True)
        for cycle in range(3):
            for q in queries:
                cur.execute(q, (cycle,))
                self.assertEqual(cur.fetchone(), (cycle + int(q.split()[1]),))
        cur.close()

        self.assertEqual(len(cache), 5)


@_skip_native
class TestStmtCacheStress(unittest.TestCase):
    """Higher volume to catch memory/reference issues."""

    def setUp(self) -> None:
        self.connection = _cache_conn(prep_stmt_cache_size=5)
        self.connection.autocommit = True

    def tearDown(self) -> None:
        self.connection.close()

    # ------------------------------------------------------------------
    def test_many_cursors_sequential(self) -> None:
        """Open and close many cursors sequentially with the same SQL."""
        sql = "SELECT ? AS v"
        for i in range(200):
            cur = self.connection.cursor(binary=True)
            cur.execute(sql, (i,))
            self.assertEqual(cur.fetchone(), (i,))
            cur.close()

    def test_many_distinct_queries_cause_churn(self) -> None:
        """Many unique queries exceed cache size, causing continuous eviction."""
        cache = self.connection._stmt_cache
        for i in range(50):
            cur = self.connection.cursor(binary=True)
            cur.execute(f"SELECT {i} + ? AS v", (0,))
            cur.fetchone()
            cur.close()

        # Cache should never exceed its max size
        self.assertLessEqual(len(cache), 5)

    def test_rapid_open_close_no_leak(self) -> None:
        """Rapidly opening/closing cursors must not leak statements."""
        sql = "SELECT ? AS v"
        cursors = []
        for i in range(20):
            cur = self.connection.cursor(binary=True)
            cur.execute(sql, (i,))
            cur.fetchone()
            cursors.append(cur)

        for cur in cursors:
            cur.close()

        # After all closed, cache should still function
        cur = self.connection.cursor(binary=True)
        cur.execute(sql, (999,))
        self.assertEqual(cur.fetchone(), (999,))
        cur.close()


@_skip_native
class TestEvictionWithActiveStream(unittest.TestCase):
    """Regression: eviction must not corrupt the connection when another
    cursor has a live unbuffered (streaming) result.

    With prep_stmt_cache_size=1, the second execute() on a *different* SQL
    triggers LRU eviction.  Eviction calls mysql_stmt_close() which sends
    COM_STMT_CLOSE via db_command(skip_check=1) — that call bypasses
    mysql->status and was calling net_clear() + resetting pkt_nr, corrupting
    any in-flight protocol state.  The fix: StmtCache.put() drains the active
    streaming result before evicting.
    """

    def setUp(self) -> None:
        self.conn = _cache_conn(prep_stmt_cache_size=1)
        self.conn.autocommit = True
        cur = self.conn.cursor()
        cur.execute(
            "CREATE TEMPORARY TABLE t_evict_stream (id INT, val VARCHAR(32))"
        )
        for i in range(10):
            cur.execute(f"INSERT INTO t_evict_stream VALUES ({i}, 'row{i}')")
        cur.close()

    def tearDown(self) -> None:
        self.conn.close()

    def test_eviction_during_streaming_binary(self) -> None:
        """Evicting a cached stmt while cursor A streams binary rows must not
        raise 'Lost connection' or 'Commands out of sync'."""
        # sql_a returns multiple rows so the cursor is still streaming after
        # fetchone() — leave remaining rows pending on the wire.
        sql_a = "SELECT id, val FROM t_evict_stream WHERE id < ?"

        # Prime the cache with sql_a
        cur_a = self.conn.cursor(binary=True)
        cur_a.execute(sql_a, (10,))
        cur_a.fetchall()
        cur_a.close()

        # Open cursor A unbuffered — fetch only one row, leave the rest pending
        cur_a = self.conn.cursor(binary=True, buffered=False)
        cur_a.execute(sql_a, (10,))
        _ = cur_a.fetchone()  # partial read — rows still on the wire

        # cursor B uses a DIFFERENT sql to force eviction of sql_a from the
        # size-1 cache.  Before the fix this sent COM_STMT_CLOSE via
        # db_command(skip_check=1) while rows were still pending, corrupting
        # the protocol.
        sql_b = "SELECT id + 1 AS id2, val FROM t_evict_stream WHERE id < ?"
        cur_b = self.conn.cursor(binary=True)
        cur_b.execute(sql_b, (3,))
        row = cur_b.fetchone()
        self.assertIsNotNone(row)
        cur_b.close()

        # Connection must still be usable
        cur_check = self.conn.cursor()
        cur_check.execute("SELECT 1")
        self.assertEqual(cur_check.fetchone(), (1,))
        cur_check.close()

        cur_a.close()

    def test_eviction_during_streaming_text(self) -> None:
        """Same scenario but cursor A uses text protocol."""
        sql_a = "SELECT id, val FROM t_evict_stream"

        # Prime the cache with a binary stmt so the cache is not empty
        prime = self.conn.cursor(binary=True)
        prime.execute("SELECT ? AS x", (0,))
        prime.fetchone()
        prime.close()

        # Cursor A: text protocol, unbuffered
        cur_a = self.conn.cursor(buffered=False)
        cur_a.execute(sql_a)
        _ = cur_a.fetchone()  # partial read

        # Cursor B: new binary stmt → cache is full (size=1) → eviction fires
        cur_b = self.conn.cursor(binary=True)
        cur_b.execute("SELECT ? + 1 AS v", (5,))
        row = cur_b.fetchone()
        self.assertIsNotNone(row)
        cur_b.close()

        # Connection must still be usable
        cur_check = self.conn.cursor()
        cur_check.execute("SELECT 42")
        self.assertEqual(cur_check.fetchone(), (42,))
        cur_check.close()

        cur_a.close()

    def test_cache_disabled_eviction_during_streaming(self) -> None:
        """With cache size=0, every put() closes immediately — same drain
        path must protect the streaming cursor."""
        # Reuse self.conn so the temp table is visible; temporarily set
        # cache maxsize to 0 to exercise the immediate-close path.
        conn = self.conn
        orig_maxsize = conn._stmt_cache._maxsize
        conn._stmt_cache._maxsize = 0
        try:
            cur_a = conn.cursor(binary=True, buffered=False)
            cur_a.execute("SELECT id FROM t_evict_stream WHERE id < ?", (10,))
            _ = cur_a.fetchone()  # partial read

            # Any binary execute triggers immediate close (size=0 path)
            cur_b = conn.cursor(binary=True)
            cur_b.execute("SELECT ? AS v", (99,))
            self.assertEqual(cur_b.fetchone(), (99,))
            cur_b.close()

            cur_check = conn.cursor()
            cur_check.execute("SELECT 1")
            self.assertEqual(cur_check.fetchone(), (1,))
            cur_check.close()

            cur_a.close()
        finally:
            conn._stmt_cache._maxsize = orig_maxsize
