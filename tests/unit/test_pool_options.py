#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""
Pool options are named, typed and reconciled in exactly one place.

Every entry point -- create_pool()/create_async_pool(), the ConnectionPool
compatibility classes, and a URI query string -- feeds
PoolConfig.from_options(), so an option means the same thing however it arrives.
Before that was true the two paths disagreed: different accepted option sets,
opposite reset_connection defaults, a 64-connection cap on one side only, and
URI values left as strings on the other.
"""

from __future__ import annotations

import unittest
import warnings
from typing import Any, Dict
from unittest.mock import MagicMock

import mariadb

try:
    from mariadb_pool import PoolConfig, POOL_OPTION_NAMES
    from mariadb_pool import ConnectionPoolWrapper
    HAS_MARIADB_POOL = True
except ImportError:
    HAS_MARIADB_POOL = False


def _factory(**kwargs: Any) -> Any:
    """Connection factory standing in for mariadb.connect."""
    return MagicMock()


def _wrapper_config(**options: Any) -> Any:
    """The PoolConfig a ConnectionPool would build from these options."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        pool = ConnectionPoolWrapper(connection_factory=_factory, **options)
    try:
        return pool._pool.config
    finally:
        pool.close()


@unittest.skipIf(not HAS_MARIADB_POOL, "mariadb_pool package not installed")
class TestFromOptions(unittest.TestCase):
    """PoolConfig.from_options() is the one mapping."""

    def test_defaults(self) -> None:
        config = PoolConfig.from_options()
        self.assertEqual(config.min_size, 10)
        self.assertEqual(config.max_size, 10)
        self.assertEqual(config.max_idle_time, 600.0)
        self.assertEqual(config.max_lifetime, 3600.0)
        self.assertEqual(config.acquire_timeout, 30.0)
        self.assertIs(config.enable_health_check, True)
        self.assertIs(config.reset_connection, False)
        self.assertEqual(config.ping_threshold, 500.0)

    def test_ping_threshold_is_11s_pool_validation_interval(self) -> None:
        # 1.1's pool_validation_interval is the borrow-time ping threshold,
        # in milliseconds -- not the maintenance sweep period
        legacy = PoolConfig.from_options(pool_validation_interval=500)
        self.assertEqual(legacy.ping_threshold, 500.0)
        self.assertEqual(legacy.ping_threshold_seconds, 0.5)
    def test_sweep_period_is_not_an_option(self) -> None:
        # the background sweep period is the resolution at which max_idle_time
        # and max_lifetime are noticed, not something a caller expresses
        self.assertNotIn('maintenance_interval', POOL_OPTION_NAMES)
        self.assertNotIn('validation_interval', POOL_OPTION_NAMES)
        from mariadb_pool.pool import MAINTENANCE_INTERVAL_SECONDS
        self.assertEqual(MAINTENANCE_INTERVAL_SECONDS, 30.0)

    def test_11_spellings_are_accepted(self) -> None:
        canonical = PoolConfig.from_options(min_size=3, max_size=3,
                                           ping_threshold=500,
                                           reset_connection=True)
        legacy = PoolConfig.from_options(pool_size=3,
                                         pool_validation_interval=500,
                                         pool_reset_connection=True)
        self.assertEqual(canonical, legacy)

    def test_pool_size_sets_both_bounds(self) -> None:
        config = PoolConfig.from_options(pool_size=7)
        self.assertEqual((config.min_size, config.max_size), (7, 7))

    def test_explicit_bound_wins_over_pool_size(self) -> None:
        config = PoolConfig.from_options(pool_size=7, max_size=9)
        self.assertEqual((config.min_size, config.max_size), (7, 9))

    def test_single_bound_makes_a_fixed_size_pool(self) -> None:
        self.assertEqual(PoolConfig.from_options(min_size=4).max_size, 4)
        self.assertEqual(PoolConfig.from_options(max_size=4).min_size, 4)

    def test_no_size_cap(self) -> None:
        # pool sizes used to be silently clamped to 64 on the wrapper path
        config = PoolConfig.from_options(pool_size=1000)
        self.assertEqual((config.min_size, config.max_size), (1000, 1000))

    def test_string_values_are_converted(self) -> None:
        # a URI query string or an option file delivers everything as text
        config = PoolConfig.from_options(min_size='2', max_size='4',
                                         ping_threshold='0.5',
                                         reset_connection='false',
                                         enable_health_check='no')
        self.assertEqual((config.min_size, config.max_size), (2, 4))
        self.assertEqual(config.ping_threshold, 0.5)
        self.assertIsInstance(config.ping_threshold, float)
        self.assertIs(config.reset_connection, False)
        self.assertIs(config.enable_health_check, False)

    def test_none_means_not_supplied(self) -> None:
        self.assertEqual(PoolConfig.from_options(max_size=None).max_size, 10)

    def test_unknown_option_is_named(self) -> None:
        with self.assertRaises(mariadb.PoolError) as ctx:
            PoolConfig.from_options(pool_sise=5)
        self.assertIn("pool_sise", str(ctx.exception))

    def test_bad_value_names_the_option(self) -> None:
        for options in (dict(max_size='abc'), dict(ping_threshold='soon'),
                        dict(reset_connection='maybe')):
            with self.subTest(options=options):
                with self.assertRaises(mariadb.PoolError) as ctx:
                    PoolConfig.from_options(**options)
                self.assertIn(next(iter(options)), str(ctx.exception))


@unittest.skipIf(not HAS_MARIADB_POOL, "mariadb_pool package not installed")
class TestEntryPointsAgree(unittest.TestCase):
    """The compatibility class and the factory must configure a pool alike."""

    CONN: Dict[str, Any] = {'host': '127.0.0.1', 'port': 1, 'user': 'u'}

    def _factory_config(self, *args: Any, **options: Any) -> Any:
        pool = mariadb.create_pool(*args, **options, **self.CONN)
        try:
            return pool.config
        finally:
            pool.close()

    def _both(self, *args: Any, **options: Any) -> tuple[Any, Any]:
        return (self._factory_config(*args, **options),
                _wrapper_config(*args, **options, **self.CONN))

    def test_defaults_agree(self) -> None:
        factory, wrapper = self._both()
        self.assertEqual(factory, wrapper)

    def test_pool_size_agrees(self) -> None:
        factory, wrapper = self._both(pool_size=5)
        self.assertEqual(factory, wrapper)
        self.assertEqual(factory.max_size, 5)

    def test_11_option_names_reach_the_factory(self) -> None:
        # pool_reset_connection/pool_validation_interval used to be silently
        # forwarded to the connection factory and dropped by create_pool()
        factory, wrapper = self._both(pool_reset_connection=False,
                                      pool_validation_interval=250)
        self.assertEqual(factory, wrapper)
        self.assertIs(factory.reset_connection, False)
        self.assertEqual(factory.ping_threshold, 250.0)

    def test_lifecycle_options_reach_the_compat_class(self) -> None:
        # max_lifetime/max_idle_time used to be unreachable through
        # ConnectionPool, silently keeping their defaults
        factory, wrapper = self._both(max_lifetime=60, max_idle_time=30)
        self.assertEqual(factory, wrapper)
        self.assertEqual(wrapper.max_lifetime, 60.0)
        self.assertEqual(wrapper.max_idle_time, 30.0)

    def test_uri_options_agree_and_are_typed(self) -> None:
        # on the compat path a URI value used to stay a string, so the first
        # ping comparison raised TypeError
        uri = ("mariadb://u@127.0.0.1:1/db"
               "?ping_threshold=0.5&min_size=0&max_size=2&reset_connection=false")
        factory = self._factory_config_uri(uri)
        wrapper = _wrapper_config_uri(uri)
        self.assertEqual(factory, wrapper)
        self.assertIsInstance(wrapper.ping_threshold, float)
        self.assertEqual(wrapper.ping_threshold, 0.5)
        self.assertEqual(wrapper.min_size, 0)
        self.assertIs(wrapper.reset_connection, False)

    def _factory_config_uri(self, uri: str) -> Any:
        pool = mariadb.create_pool(uri)
        try:
            return pool.config
        finally:
            pool.close()

    def test_option_set_is_shared(self) -> None:
        from mariadb_pool.connection_pool_wrapper import POOL_CONFIG_KEYS
        self.assertIs(POOL_CONFIG_KEYS, POOL_OPTION_NAMES)


def _wrapper_config_uri(uri: str) -> Any:
    """The PoolConfig a ConnectionPool builds from a URI."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        pool = mariadb.ConnectionPool(uri)
    try:
        return pool._pool.config
    finally:
        pool.close()


if __name__ == "__main__":
    unittest.main()
