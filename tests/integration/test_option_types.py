#!/usr/bin/env python -O
# -*- coding: utf-8 -*-
"""
Regression tests for CONPY-331.

A wrong type on an integer connection option produced "'str' object cannot be
interpreted as an integer" from the C argument parser, naming neither the option
nor the expected type. Worse, the two implementations disagreed: the pure-Python
client coerced port='3306' and accepted it, while the C extension rejected it.

Integer options now go through mariadb_shared.validators.validate_int in both
implementations, mirroring what validate_bool already did for booleans: a digit
string is accepted, so an option read from a config file or an environment
variable works, and anything else raises ProgrammingError naming the option.

Both drivers are exercised through the same tests so they cannot drift apart.
"""
from __future__ import annotations

from typing import Any

import pytest

import mariadb

from ..conftest import get_test_config as conf

INT_OPTIONS = ("port", "connect_timeout", "read_timeout", "write_timeout",
               "client_flag")


def _connect(**overrides: Any) -> Any:
    args = conf().copy()
    args.update(overrides)
    return mariadb.connect(**args)


@pytest.mark.parametrize("option", INT_OPTIONS)
def test_non_numeric_string_names_the_option(option: str) -> None:
    with pytest.raises(mariadb.ProgrammingError) as excinfo:
        _connect(**{option: "not-a-number"})
    message = str(excinfo.value)
    assert option in message
    assert "not-a-number" in message


@pytest.mark.parametrize("option", INT_OPTIONS)
def test_none_names_the_option(option: str) -> None:
    with pytest.raises(mariadb.ProgrammingError) as excinfo:
        _connect(**{option: None})
    assert option in str(excinfo.value)


@pytest.mark.parametrize("value", [3306.5, ["3306"], {"port": 3306}, object()])
def test_other_wrong_types_are_refused(value: Any) -> None:
    with pytest.raises(mariadb.ProgrammingError) as excinfo:
        _connect(port=value)
    assert "port" in str(excinfo.value)


def test_digit_string_is_accepted() -> None:
    # the common case: a port read from a config file or an environment variable
    connection = _connect(port=str(conf()["port"]))
    connection.close()


def test_int_is_still_accepted() -> None:
    connection = _connect(port=int(conf()["port"]))
    connection.close()


@pytest.mark.parametrize("option,value", [("connect_timeout", "10"),
                                          ("client_flag", "0"),
                                          ("read_timeout", "30")])
def test_other_integer_options_accept_digit_strings(option: str, value: str) -> None:
    connection = _connect(**{option: value})
    connection.close()


def test_boolean_options_are_unaffected() -> None:
    # validate_bool already accepted strings on both drivers; guard against the
    # integer change altering that.
    for kwargs in ({"compress": "true"}, {"ssl_verify_cert": "0"},
                   {"local_infile": "1"}):
        connection = _connect(**kwargs)
        connection.close()


if __name__ == "__main__":
    pytest.main([__file__])
