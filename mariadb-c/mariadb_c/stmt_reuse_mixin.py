# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Prepared-statement cache helpers shared by the sync and async C cursors.

Both cursor classes detach/attach the underlying ``MYSQL_STMT`` (wrapped in a
PyCapsule) to reuse prepared statements. The reuse/save/restore logic is
identical for both, so it lives here as a mixin. The mixin relies on the host
cursor providing:

- ``self._connection`` — the owning connection (with ``_stmt_cache`` and the
  ``_close_stmt_capsule`` / ``_neutralize_stmt_capsule`` capsule helpers),
- ``self._local_stmt_cache`` — per-cursor cache slot (initialised to ``None``),
- ``self._cache_entry`` — currently checked-out template entry (or ``None``),
- ``super()._detach_stmt()`` / ``super()._attach_stmt()`` — from the C cursor
  base, so the mixin must precede that base in the MRO.
"""

from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .connections import StmtCache, StmtCacheEntry


class StmtReuseMixin:
    """Prepared-statement reuse (save/restore/close) behaviour for the C cursors.

    No ``__slots__`` here: the host cursor (a Python subclass of the C cursor)
    has a ``__dict__``, and these attributes are stored there.
    """

    # Provided by the host cursor (see module docstring).
    _connection: Any
    _local_stmt_cache: Optional[StmtCache]
    _cache_entry: Optional[StmtCacheEntry]
    _resolved_stmt_cache: Optional[StmtCache]

    def _resolve_stmt_cache(self) -> Optional[StmtCache]:
        """Return the statement cache to use for prepared-statement reuse.

        When the connection-level cache is enabled, returns it (statements are
        shared across all cursors). When it is disabled, lazily creates and
        returns a per-cursor size-1 cache, giving "keep the last prepared
        statement, reuse it while the SQL is unchanged, close it otherwise"
        semantics scoped to this cursor.

        The result is memoised: execute() resolves it twice per statement (save
        + restore), and the connection's cache object is stable for the cursor's
        lifetime (set once at connect, only nulled at connection close).
        """
        resolved = self._resolved_stmt_cache
        if resolved is not None:
            return resolved
        cache: Optional[StmtCache] = getattr(self._connection, '_stmt_cache', None)
        if cache is not None and cache.enabled:
            self._resolved_stmt_cache = cache
            return cache
        if self._local_stmt_cache is None:
            from .connections import StmtCache
            self._local_stmt_cache = StmtCache(self._connection, 1)
        self._resolved_stmt_cache = self._local_stmt_cache
        return self._local_stmt_cache

    def _save_stmt_to_cache(self, sql: Optional[str]) -> None:
        """Detach the current MYSQL_STMT and store/return it to the cache."""
        if not sql:
            return

        # If we checked out a template, return it to the entry
        if self._cache_entry is not None:
            capsule = super()._detach_stmt()  # type: ignore[misc]  # provided by C cursor base
            if capsule is not None:
                self._cache_entry.checkin(capsule, self._connection)
            self._cache_entry = None
            return

        cache = self._resolve_stmt_cache()
        if cache is None:
            return

        # First prepare for this SQL — detach and create a new cache entry
        capsule = super()._detach_stmt()  # type: ignore[misc]  # provided by C cursor base
        if capsule is None:
            return
        cache.put(sql, capsule)

    def _restore_stmt_from_cache(self, sql: str) -> bool:
        """Try to check out a cached template. Returns True on hit."""
        cache = self._resolve_stmt_cache()
        if cache is None:
            return False
        entry = cache.get(sql)
        if entry is None:
            return False
        capsule = entry.checkout()
        if capsule is None:
            return False
        super()._attach_stmt(capsule)  # type: ignore[misc]  # provided by C cursor base
        self._cache_entry = entry
        return True

    def _close_local_stmt_cache(self) -> None:
        """Close the per-cursor prepared statement, if any (connection cache off).

        Defensive: cursor close must not fail if the COM_STMT_CLOSE write errors
        on an already-broken connection (mirrors the pure-Python base cursor).
        """
        self._resolved_stmt_cache = None
        if self._local_stmt_cache is not None:
            try:
                self._local_stmt_cache.clear()
            except Exception:
                pass
            self._local_stmt_cache = None
