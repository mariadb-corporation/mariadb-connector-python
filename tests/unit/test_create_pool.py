"""
Unit tests for create_pool / create_async_pool min_size defaulting behaviour.

These tests mock mariadb_pool so no real database or pool package is required.
"""

from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import MagicMock, patch, AsyncMock


def _make_mariadb_pool_mock() -> types.ModuleType:
    """Build a minimal mariadb_pool stub that records PoolConfig construction args."""
    mod = types.ModuleType("mariadb_pool")

    class PoolConfig:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    class ConnectionPool:
        def __init__(self, connection_factory: object, config: PoolConfig, **kwargs: object) -> None:
            self.config = config

    class AsyncConnectionPool:
        def __init__(self, connection_factory: object, config: PoolConfig, **kwargs: object) -> None:
            self.config = config

        async def open(self) -> None:
            pass

    mod.PoolConfig = PoolConfig  # type: ignore[attr-defined]
    mod.ConnectionPool = ConnectionPool  # type: ignore[attr-defined]
    mod.AsyncConnectionPool = AsyncConnectionPool  # type: ignore[attr-defined]
    return mod


_POOL_MOD = _make_mariadb_pool_mock()


class TestCreatePoolMinSize(unittest.TestCase):
    """Verify create_pool min_size defaulting logic."""

    def setUp(self) -> None:
        sys.modules["mariadb_pool"] = _POOL_MOD

    def tearDown(self) -> None:
        sys.modules.pop("mariadb_pool", None)

    def _create_pool(self, **kwargs: object) -> object:
        import mariadb
        return mariadb.create_pool(**kwargs)

    def test_min_size_defaults_to_max_size(self) -> None:
        """When min_size is omitted, it must equal max_size."""
        pool = self._create_pool(max_size=15)
        self.assertEqual(pool.config.kwargs["min_size"], 15)
        self.assertEqual(pool.config.kwargs["max_size"], 15)

    def test_min_size_explicit_respected(self) -> None:
        """When min_size is provided explicitly it must not be overridden."""
        pool = self._create_pool(min_size=3, max_size=15)
        self.assertEqual(pool.config.kwargs["min_size"], 3)
        self.assertEqual(pool.config.kwargs["max_size"], 15)

    def test_min_size_equal_max_size_explicit(self) -> None:
        """Explicit min_size == max_size is fine and must be preserved."""
        pool = self._create_pool(min_size=10, max_size=10)
        self.assertEqual(pool.config.kwargs["min_size"], 10)

    def test_default_max_size_used_when_neither_given(self) -> None:
        """With no arguments, both default to the built-in max_size default (10)."""
        pool = self._create_pool()
        self.assertEqual(pool.config.kwargs["min_size"], pool.config.kwargs["max_size"])
        self.assertEqual(pool.config.kwargs["max_size"], 10)

    def test_min_size_zero_is_respected(self) -> None:
        """Explicit min_size=0 must not be treated as 'not set'."""
        pool = self._create_pool(min_size=0, max_size=5)
        self.assertEqual(pool.config.kwargs["min_size"], 0)


class TestCreateAsyncPoolMinSize(unittest.IsolatedAsyncioTestCase):
    """Verify create_async_pool min_size defaulting logic."""

    def setUp(self) -> None:
        sys.modules["mariadb_pool"] = _POOL_MOD

    def tearDown(self) -> None:
        sys.modules.pop("mariadb_pool", None)

    async def _create_async_pool(self, **kwargs: object) -> object:
        import mariadb
        return await mariadb.create_async_pool(**kwargs)

    async def test_min_size_defaults_to_max_size(self) -> None:
        """When min_size is omitted, it must equal max_size."""
        pool = await self._create_async_pool(max_size=20)
        self.assertEqual(pool.config.kwargs["min_size"], 20)
        self.assertEqual(pool.config.kwargs["max_size"], 20)

    async def test_min_size_explicit_respected(self) -> None:
        """When min_size is provided explicitly it must not be overridden."""
        pool = await self._create_async_pool(min_size=4, max_size=20)
        self.assertEqual(pool.config.kwargs["min_size"], 4)
        self.assertEqual(pool.config.kwargs["max_size"], 20)

    async def test_min_size_equal_max_size_explicit(self) -> None:
        """Explicit min_size == max_size is fine and must be preserved."""
        pool = await self._create_async_pool(min_size=8, max_size=8)
        self.assertEqual(pool.config.kwargs["min_size"], 8)

    async def test_default_max_size_used_when_neither_given(self) -> None:
        """With no arguments, both default to the built-in max_size default (10)."""
        pool = await self._create_async_pool()
        self.assertEqual(pool.config.kwargs["min_size"], pool.config.kwargs["max_size"])
        self.assertEqual(pool.config.kwargs["max_size"], 10)

    async def test_min_size_zero_is_respected(self) -> None:
        """Explicit min_size=0 must not be treated as 'not set'."""
        pool = await self._create_async_pool(min_size=0, max_size=5)
        self.assertEqual(pool.config.kwargs["min_size"], 0)


if __name__ == "__main__":
    unittest.main()
