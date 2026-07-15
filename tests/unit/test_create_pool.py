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
            self.conn_kwargs = kwargs

    class AsyncConnectionPool:
        def __init__(self, connection_factory: object, config: PoolConfig, **kwargs: object) -> None:
            self.config = config
            self.conn_kwargs = kwargs

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


class TestCreatePoolUri(unittest.TestCase):
    """Verify create_pool accepts a connection URI as first positional argument."""

    def setUp(self) -> None:
        sys.modules["mariadb_pool"] = _POOL_MOD

    def tearDown(self) -> None:
        sys.modules.pop("mariadb_pool", None)

    def _create_pool(self, *args: object, **kwargs: object) -> object:
        import mariadb
        return mariadb.create_pool(*args, **kwargs)

    def test_uri_parsed_into_connection_params(self) -> None:
        """A URI first positional argument is parsed into connection params."""
        pool = self._create_pool("mariadb://root:secret@dbhost:3307/mydb")
        self.assertEqual(pool.conn_kwargs["user"], "root")
        self.assertEqual(pool.conn_kwargs["password"], "secret")
        self.assertEqual(pool.conn_kwargs["host"], "dbhost")
        self.assertEqual(pool.conn_kwargs["port"], 3307)
        self.assertEqual(pool.conn_kwargs["database"], "mydb")

    def test_kwargs_override_uri(self) -> None:
        """Explicit connection kwargs take priority over URI values."""
        pool = self._create_pool("mariadb://root:secret@dbhost/mydb", password="override")
        self.assertEqual(pool.conn_kwargs["password"], "override")
        self.assertEqual(pool.conn_kwargs["host"], "dbhost")

    def test_uri_and_pool_config_coexist(self) -> None:
        """Pool-config kwargs and a URI can be combined."""
        pool = self._create_pool("mariadb://root@dbhost/mydb", min_size=3, max_size=7)
        self.assertEqual(pool.config.kwargs["min_size"], 3)
        self.assertEqual(pool.config.kwargs["max_size"], 7)
        self.assertEqual(pool.conn_kwargs["host"], "dbhost")

    def test_no_uri_leaves_params_untouched(self) -> None:
        """Without a URI, keyword connection params pass through unchanged."""
        pool = self._create_pool(host="localhost", user="me")
        self.assertEqual(pool.conn_kwargs["host"], "localhost")
        self.assertEqual(pool.conn_kwargs["user"], "me")

    def test_pool_config_from_uri_query(self) -> None:
        """Pool-config keys in the URI query string configure the pool, not connect()."""
        pool = self._create_pool("mariadb://root@dbhost/mydb?min_size=5&max_size=20")
        self.assertEqual(pool.config.kwargs["min_size"], 5)
        self.assertEqual(pool.config.kwargs["max_size"], 20)
        # and they must NOT leak into the connection params
        self.assertNotIn("min_size", pool.conn_kwargs)
        self.assertNotIn("max_size", pool.conn_kwargs)
        self.assertEqual(pool.conn_kwargs["host"], "dbhost")

    def test_uri_query_types_coerced(self) -> None:
        """Query-string pool values are coerced to the correct types (parser can't be trusted)."""
        pool = self._create_pool(
            "mariadb://root@dbhost/mydb?ping_threshold=0.5&enable_health_check=false&min_size=0"
        )
        self.assertEqual(pool.config.kwargs["ping_threshold"], 0.5)
        self.assertIsInstance(pool.config.kwargs["ping_threshold"], float)
        self.assertIs(pool.config.kwargs["enable_health_check"], False)
        # min_size=0 must survive as int 0, not be mis-parsed as False
        self.assertEqual(pool.config.kwargs["min_size"], 0)
        self.assertIsInstance(pool.config.kwargs["min_size"], int)

    def test_kwarg_overrides_uri_pool_config(self) -> None:
        """Explicit pool-config kwarg wins over the URI query value."""
        pool = self._create_pool("mariadb://root@dbhost/mydb?max_size=20", max_size=99)
        self.assertEqual(pool.config.kwargs["max_size"], 99)

    def test_uri_min_size_defaults_to_uri_max_size(self) -> None:
        """min_size still defaults to max_size when only max_size is in the URI."""
        pool = self._create_pool("mariadb://root@dbhost/mydb?max_size=15")
        self.assertEqual(pool.config.kwargs["min_size"], 15)
        self.assertEqual(pool.config.kwargs["max_size"], 15)

    def test_mysql_scheme_accepted(self) -> None:
        """The mysql:// scheme is a connection URI too."""
        pool = self._create_pool("mysql://root@dbhost/mydb?max_size=4")
        self.assertEqual(pool.config.kwargs["max_size"], 4)
        self.assertEqual(pool.conn_kwargs["host"], "dbhost")

    def test_non_uri_positional_rejected(self) -> None:
        """A first positional argument that is not a URI must not be silently dropped."""
        with self.assertRaises(ValueError) as ctx:
            self._create_pool("mypool", host="dbhost")
        self.assertIn("mypool", str(ctx.exception))

    def test_unknown_scheme_rejected(self) -> None:
        """A URI-looking string with a foreign scheme is rejected, not ignored."""
        with self.assertRaises(ValueError):
            self._create_pool("postgres://root@dbhost/mydb")

    def test_non_string_positional_rejected(self) -> None:
        """The pre-2.0 positional style create_pool(5, ...) must fail loudly."""
        with self.assertRaises(ValueError):
            self._create_pool(5)

    def test_all_float_options_from_uri(self) -> None:
        """Every float-typed pool option is read and coerced from the query string."""
        pool = self._create_pool(
            "mariadb://root@dbhost/mydb"
            "?max_idle_time=90&max_lifetime=120&validation_interval=15&acquire_timeout=5"
        )
        for key, expected in (
            ("max_idle_time", 90.0),
            ("max_lifetime", 120.0),
            ("validation_interval", 15.0),
            ("acquire_timeout", 5.0),
        ):
            self.assertEqual(pool.config.kwargs[key], expected)
            self.assertIsInstance(pool.config.kwargs[key], float)
            self.assertNotIn(key, pool.conn_kwargs)

    def test_defaults_when_nothing_supplied(self) -> None:
        """With neither URI nor kwargs, the documented defaults apply."""
        pool = self._create_pool()
        self.assertEqual(pool.config.kwargs["max_size"], 10)
        self.assertEqual(pool.config.kwargs["min_size"], 10)
        self.assertEqual(pool.config.kwargs["max_idle_time"], 600.0)
        self.assertEqual(pool.config.kwargs["max_lifetime"], 3600.0)
        self.assertEqual(pool.config.kwargs["validation_interval"], 30.0)
        self.assertEqual(pool.config.kwargs["acquire_timeout"], 30.0)
        self.assertIs(pool.config.kwargs["enable_health_check"], True)
        self.assertIs(pool.config.kwargs["reset_connection"], False)
        self.assertEqual(pool.config.kwargs["ping_threshold"], 0.25)

    def test_invalid_numeric_uri_value_names_the_option(self) -> None:
        """A non-numeric pool value is rejected, and the error names the option."""
        with self.assertRaises(ValueError) as ctx:
            self._create_pool("mariadb://root@dbhost/mydb?max_size=abc")
        self.assertIn("max_size", str(ctx.exception))

    def test_invalid_bool_uri_value_rejected(self) -> None:
        """An unrecognised boolean must not silently read as False."""
        with self.assertRaises(ValueError) as ctx:
            self._create_pool("mariadb://root@dbhost/mydb?enable_health_check=maybe")
        self.assertIn("enable_health_check", str(ctx.exception))

    def test_blank_bool_uri_value_rejected(self) -> None:
        """A valueless flag is not a boolean either."""
        with self.assertRaises(ValueError):
            self._create_pool("mariadb://root@dbhost/mydb?reset_connection=")

    def test_pool_name_in_uri_rejected(self) -> None:
        """pool_name must not reach connect(), which would nest a second pool."""
        with self.assertRaises(ValueError) as ctx:
            self._create_pool("mariadb://root@dbhost/mydb?pool_name=mypool")
        self.assertIn("pool_name", str(ctx.exception))

    def test_pool_name_kwarg_rejected(self) -> None:
        """The same applies to pool_name passed as a keyword argument."""
        with self.assertRaises(ValueError):
            self._create_pool(host="dbhost", pool_name="mypool")


class TestCreateAsyncPoolUri(unittest.IsolatedAsyncioTestCase):
    """Verify create_async_pool accepts a connection URI as first positional argument."""

    def setUp(self) -> None:
        sys.modules["mariadb_pool"] = _POOL_MOD

    def tearDown(self) -> None:
        sys.modules.pop("mariadb_pool", None)

    async def _create_async_pool(self, *args: object, **kwargs: object) -> object:
        import mariadb
        return await mariadb.create_async_pool(*args, **kwargs)

    async def test_uri_parsed_into_connection_params(self) -> None:
        """A URI first positional argument is parsed into connection params."""
        pool = await self._create_async_pool("mariadb://root:secret@dbhost:3307/mydb")
        self.assertEqual(pool.conn_kwargs["user"], "root")
        self.assertEqual(pool.conn_kwargs["password"], "secret")
        self.assertEqual(pool.conn_kwargs["host"], "dbhost")
        self.assertEqual(pool.conn_kwargs["port"], 3307)
        self.assertEqual(pool.conn_kwargs["database"], "mydb")

    async def test_kwargs_override_uri(self) -> None:
        """Explicit connection kwargs take priority over URI values."""
        pool = await self._create_async_pool("mariadb://root:secret@dbhost/mydb", password="override")
        self.assertEqual(pool.conn_kwargs["password"], "override")
        self.assertEqual(pool.conn_kwargs["host"], "dbhost")

    async def test_uri_and_pool_config_coexist(self) -> None:
        """Pool-config kwargs and a URI can be combined."""
        pool = await self._create_async_pool("mariadb://root@dbhost/mydb", min_size=3, max_size=7)
        self.assertEqual(pool.config.kwargs["min_size"], 3)
        self.assertEqual(pool.config.kwargs["max_size"], 7)
        self.assertEqual(pool.conn_kwargs["host"], "dbhost")

    async def test_pool_config_from_uri_query(self) -> None:
        """Pool-config keys in the URI query string configure the pool, not connect()."""
        pool = await self._create_async_pool("mariadb://root@dbhost/mydb?min_size=5&max_size=20")
        self.assertEqual(pool.config.kwargs["min_size"], 5)
        self.assertEqual(pool.config.kwargs["max_size"], 20)
        self.assertNotIn("min_size", pool.conn_kwargs)
        self.assertNotIn("max_size", pool.conn_kwargs)

    async def test_uri_query_types_coerced(self) -> None:
        """Query-string pool values are coerced to the correct types."""
        pool = await self._create_async_pool(
            "mariadb://root@dbhost/mydb?ping_threshold=0.5&reset_connection=true&min_size=0"
        )
        self.assertEqual(pool.config.kwargs["ping_threshold"], 0.5)
        self.assertIs(pool.config.kwargs["reset_connection"], True)
        self.assertEqual(pool.config.kwargs["min_size"], 0)

    async def test_kwarg_overrides_uri_pool_config(self) -> None:
        """Explicit pool-config kwarg wins over the URI query value."""
        pool = await self._create_async_pool("mariadb://root@dbhost/mydb?max_size=20", max_size=99)
        self.assertEqual(pool.config.kwargs["max_size"], 99)

    async def test_no_uri_leaves_params_untouched(self) -> None:
        """Without a URI, keyword connection params pass through unchanged."""
        pool = await self._create_async_pool(host="localhost", user="me")
        self.assertEqual(pool.conn_kwargs["host"], "localhost")
        self.assertEqual(pool.conn_kwargs["user"], "me")

    async def test_uri_min_size_defaults_to_uri_max_size(self) -> None:
        """min_size still defaults to max_size when only max_size is in the URI."""
        pool = await self._create_async_pool("mariadb://root@dbhost/mydb?max_size=15")
        self.assertEqual(pool.config.kwargs["min_size"], 15)
        self.assertEqual(pool.config.kwargs["max_size"], 15)

    async def test_non_uri_positional_rejected(self) -> None:
        """A first positional argument that is not a URI must not be silently dropped."""
        with self.assertRaises(ValueError) as ctx:
            await self._create_async_pool("mypool", host="dbhost")
        self.assertIn("mypool", str(ctx.exception))

    async def test_unknown_scheme_rejected(self) -> None:
        """A URI-looking string with a foreign scheme is rejected, not ignored."""
        with self.assertRaises(ValueError):
            await self._create_async_pool("postgres://root@dbhost/mydb")

    async def test_invalid_bool_uri_value_rejected(self) -> None:
        """An unrecognised boolean must not silently read as False."""
        with self.assertRaises(ValueError) as ctx:
            await self._create_async_pool("mariadb://root@dbhost/mydb?reset_connection=maybe")
        self.assertIn("reset_connection", str(ctx.exception))

    async def test_invalid_numeric_uri_value_names_the_option(self) -> None:
        """A non-numeric pool value is rejected, and the error names the option."""
        with self.assertRaises(ValueError) as ctx:
            await self._create_async_pool("mariadb://root@dbhost/mydb?max_size=abc")
        self.assertIn("max_size", str(ctx.exception))

    async def test_pool_name_in_uri_rejected(self) -> None:
        """pool_name must not reach asyncConnect(), which would nest a second pool."""
        with self.assertRaises(ValueError) as ctx:
            await self._create_async_pool("mariadb://root@dbhost/mydb?pool_name=mypool")
        self.assertIn("pool_name", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
