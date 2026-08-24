# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
FIPS mode detection for the pure-Python client.

A Python linked against a FIPS-enforcing OpenSSL (OpenSSL 3.x with only the
FIPS provider available, the RHEL/Ubuntu FIPS system builds, ...) refuses to
hash with SHA-1: ``hashlib.sha1()`` raises instead of returning a digest.

For this connector that is an *authentication* problem and nothing else.
``mysql_native_password`` -- the plugin every connector names in its handshake
response, whatever the account actually uses -- is defined as a SHA-1
construction.  On a FIPS build the very first packet the client sends therefore
raised, before the server ever got the chance to answer with the
authentication-switch request that moves the connection onto the FIPS-compliant
plugin the account really is on (``parsec``).  The result was that the
pure-Python client could not connect at all under FIPS, for any account.

So SHA-1 availability is probed once and, when it is unavailable, the
authentication plugins substitute an all-zero placeholder for the digest they
cannot compute (see ``NativePasswordPlugin.encrypt_password``).  The handshake
stays well-formed, the server answers with an authentication-switch request,
and a ``parsec`` account authenticates normally.  An account that genuinely is
on ``mysql_native_password`` cannot work under FIPS by definition -- there the
placeholder is simply a wrong password, and
``AuthenticationPluginLoader.get()`` refuses the plugin outright should the
server switch to it.

Note what is deliberately *not* done: SHA-1 is never re-enabled by passing
``usedforsecurity=False``.  That flag exists to mark a hash that is not used as
a security primitive, which is not the case here -- the native-password
scramble authenticates the connection.  Using it would sidestep the host's FIPS
policy rather than comply with it.

Detection can be forced either way with the ``MARIADB_FIPS_MODE`` environment
variable (``1``/``true``/``yes``/``on`` or ``0``/``false``/``no``/``off``),
which is also how the test suite exercises both branches on a normal build.
"""

from __future__ import annotations

import hashlib
import os
from typing import Optional

# Length of a SHA-1 digest, and therefore also of the mysql_native_password
# scramble, which is built out of three of them.
SHA1_DIGEST_LENGTH = 20

FIPS_MODE_ENV_VAR = "MARIADB_FIPS_MODE"

_TRUE_VALUES = frozenset(("1", "true", "yes", "on"))
_FALSE_VALUES = frozenset(("0", "false", "no", "off"))

# None until the first is_fips_mode() call.  The result is cached because the
# set of loaded OpenSSL providers cannot change during the process lifetime,
# and the probe would otherwise run on every single connection attempt.
_fips_mode: Optional[bool] = None


def _forced_mode() -> Optional[bool]:
    """Read the MARIADB_FIPS_MODE override, or None when it is unset/unparsable."""
    raw = os.environ.get(FIPS_MODE_ENV_VAR)
    if raw is None:
        return None
    value = raw.strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    return None


def _sha1_available() -> bool:
    """True when hashlib can actually produce a SHA-1 digest.

    A full digest is computed rather than just constructing the object: some
    builds only fail on the final ``digest()`` call.  Any exception counts as
    "unavailable" -- the exception type is an OpenSSL/hashlib implementation
    detail (``ValueError`` on CPython today, not guaranteed).
    """
    try:
        # Availability probe only: the digest is thrown away, nothing is
        # authenticated with it.
        hashlib.sha1(b"").digest()  # nosec B324
    except Exception:
        return False
    return True


def is_fips_mode() -> bool:
    """True when this interpreter runs on a FIPS-enforcing crypto backend.

    Determined by whether SHA-1 hashing is available, which is exactly the
    capability the native-password authentication path needs.  Overridable
    through the ``MARIADB_FIPS_MODE`` environment variable.
    """
    global _fips_mode
    if _fips_mode is None:
        forced = _forced_mode()
        _fips_mode = forced if forced is not None else not _sha1_available()
    return _fips_mode


def set_fips_mode(enabled: Optional[bool]) -> None:
    """Override the detected mode; ``None`` restores auto-detection.

    Intended for tests, so that both branches can be exercised on a build where
    SHA-1 is perfectly usable.
    """
    global _fips_mode
    _fips_mode = enabled
