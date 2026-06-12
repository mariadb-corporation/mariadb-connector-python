#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""
Regression test: a parameter whose type has no dedicated converter must be
escaped, not spliced into the SQL raw.

The text protocol substitutes parameters into the SQL string. Known types are
escaped/quoted by PARAM_CONVERT_TBL, but an unknown type used to fall back to
``str(param).encode('utf8')`` -- no quoting, no escaping. A value whose str()
contained a single quote could therefore break out of the literal and inject
SQL. The fallback must now escape the value as a quoted string literal (mirroring
how the binary protocol coerces unknown types to a VAR_STRING value), across
every placeholder style and under NO_BACKSLASH_ESCAPES.
"""

import unittest
from mariadb_shared.text_protocol import substitute_params


class _Evil:
    """Unknown parameter type whose string form is a SQL-injection payload."""
    def __str__(self):
        return "x' OR '1'='1"


class _Benign:
    """Unknown parameter type with a harmless string form (numpy-scalar-like)."""
    def __str__(self):
        return "5"


def _subst(sql, params, no_backslash_escapes=False):
    return b"".join(substitute_params(sql, params, no_backslash_escapes)).decode("utf-8")


class UnknownParamEscapingTest(unittest.TestCase):

    # The payload, once escaped with backslashes and wrapped in single quotes.
    ESCAPED = "'x\\' OR \\'1\\'=\\'1'"

    # --- the injection payload is neutralised in every placeholder style -------

    def test_fast_path_two_positional(self):
        # >= 2 positional params + simple SQL takes the bytes.split('?') fast path
        self.assertEqual(_subst("SELECT ?, ?", [_Evil(), _Evil()]),
                         "SELECT %s, %s" % (self.ESCAPED, self.ESCAPED))

    def test_single_qmark(self):
        self.assertEqual(_subst("SELECT ?", [_Evil()]), "SELECT " + self.ESCAPED)

    def test_format(self):
        self.assertEqual(_subst("SELECT %s", [_Evil()]), "SELECT " + self.ESCAPED)

    def test_pyformat_named(self):
        self.assertEqual(_subst("SELECT %(n)s", {"n": _Evil()}),
                         "SELECT " + self.ESCAPED)

    def test_colon_named(self):
        self.assertEqual(_subst("SELECT :n", {"n": _Evil()}), "SELECT " + self.ESCAPED)

    # --- NO_BACKSLASH_ESCAPES: quotes are doubled, still safe ------------------

    def test_no_backslash_escapes_doubles_quotes(self):
        self.assertEqual(_subst("SELECT ?", [_Evil()], no_backslash_escapes=True),
                         "SELECT 'x'' OR ''1''=''1'")

    # --- structural safety: every quote from the payload is escaped ------------

    def test_no_unescaped_quote_breaks_out(self):
        out = _subst("SELECT ?", [_Evil()])
        # strip the outer quotes; the inner text must not contain a bare quote
        self.assertTrue(out.startswith("SELECT '") and out.endswith("'"))
        inner = out[len("SELECT '"):-1]
        # a bare (unescaped) single quote would be one not preceded by a backslash
        for idx, ch in enumerate(inner):
            if ch == "'":
                self.assertEqual(inner[idx - 1], "\\",
                                 "unescaped quote at %d in %r" % (idx, out))

    # --- benign unknown type still renders a usable value ----------------------

    def test_benign_unknown_type_renders_quoted_value(self):
        # matches the binary protocol, which sends unknown types as a VAR_STRING
        self.assertEqual(_subst("SELECT ?", [_Benign()]), "SELECT '5'")

    # --- known types are unaffected by the change -----------------------------

    def test_known_types_unaffected(self):
        # int stays a bare numeric literal; str is escaped as before
        self.assertEqual(_subst("SELECT ?, ?", [5, "a'b"]), "SELECT 5, 'a\\'b'")


if __name__ == "__main__":
    unittest.main()
