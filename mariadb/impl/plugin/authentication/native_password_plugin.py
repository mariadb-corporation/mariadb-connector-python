# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from __future__ import annotations

import hashlib

from ...configuration import Configuration

from typing import Callable, Awaitable
from ...client.context import Context
from ...fips import SHA1_DIGEST_LENGTH, is_fips_mode
from ..authentication_plugin import AuthenticationPlugin


class NativePasswordPlugin(AuthenticationPlugin):
    """
    Native password authentication plugin implementation
    See https://mariadb.com/kb/en/library/authentication-plugin-mysql_native_password/
    """
        
    def __init__(self, authentication_data: str | None, seed: bytes):
        """Initialize plugin with authentication data and seed"""
        self.authentication_data = authentication_data
        self.seed = seed

    @staticmethod
    def encrypt_password(password: str | None, seed: bytes) -> bytearray:
        """Encrypts a password using MySQL native password algorithm"""
        if password is None or password == "":  # nosec B105
            return bytearray(b'')

        if is_fips_mode():
            # A FIPS-enforcing OpenSSL has no SHA-1, so this scramble cannot be
            # computed at all. Returning an all-zero placeholder instead of
            # raising keeps the handshake well-formed: the connector always
            # names mysql_native_password in its handshake response, and only a
            # complete handshake gets the authentication-switch request that
            # moves the connection onto the FIPS-compliant plugin (parsec) the
            # account actually uses. An account genuinely on
            # mysql_native_password fails authentication here, which is correct:
            # that plugin cannot be used under FIPS. See mariadb.impl.fips.
            return bytearray(SHA1_DIGEST_LENGTH)

        password_bytes = password.encode('utf-8')
        # SHA1 is mandated by the mysql_native_password wire protocol; it is a
        # protocol building block, not a security choice by the connector. It
        # stays under the default usedforsecurity=True: a FIPS build must not
        # compute it, which is what the is_fips_mode() branch above handles.
        stage1 = hashlib.sha1(password_bytes).digest()  # nosec B324
        stage2 = hashlib.sha1(stage1).digest()  # nosec B324
        digest = hashlib.sha1()  # nosec B324
        digest.update(seed)
        digest.update(stage2)
        stage3 = digest.digest()
        result = bytearray(20)
        for i in range(20):
            result[i] = stage1[i] ^ stage3[i]
        return result
    
    def _build_auth_payload(self) -> bytearray:
        """Build authentication payload"""
        if self.authentication_data is None:
            return bytearray()
        
        # Truncate seed to 20 bytes (remove null terminator if present)
        truncated_seed = self.seed[:20] if len(self.seed) > 20 else self.seed
        
        # Encrypt password
        return self.encrypt_password(self.authentication_data, truncated_seed)
    
    async def processAsync(
        self, 
        read_payload_func: Callable[[], Awaitable[memoryview]], 
        write_payload_func: Callable[[bytearray, str, bool], Awaitable[None]], 
        context: Context
    ) -> memoryview:
        """Process native password plugin authentication (async)"""
        encrypted = self._build_auth_payload()
        payload = bytearray(b'\0\0\0\0')
        payload.extend(encrypted)
        await write_payload_func(payload, "NATIVE_PASSWORD", False)
        return await read_payload_func()
    
    def processSync(
        self, 
        read_payload_func: Callable[[], memoryview], 
        write_payload_func: Callable[[bytearray, str, bool], None], 
        context: Context
    ) -> memoryview:
        """Process native password plugin authentication (sync)"""
        encrypted = self._build_auth_payload()
        payload = bytearray(b'\0\0\0\0')
        payload.extend(encrypted)
        write_payload_func(payload, "NATIVE_PASSWORD", False)
        return read_payload_func()
    
    def is_mitm_proof(self) -> bool:
        """Native password plugin is MitM-proof"""
        return True
    
    def hash(self, conf: Configuration) -> bytes | None:
        """Return hash for credential (double SHA1)"""
        password = conf.password
        if password is None:
            return None
        if is_fips_mode():
            # No SHA-1 available, so no credential hash can be produced. The
            # caller (self-signed-certificate fingerprint validation) treats a
            # missing hash as a hard failure, so this fails closed with an
            # explicit message instead of crashing. Unreachable in practice:
            # native-password authentication cannot succeed under FIPS anyway.
            return None
        password_bytes = password.encode('utf-8')
        # Protocol-mandated SHA1 (see encrypt_password); not a security choice.
        stage1 = hashlib.sha1(password_bytes).digest()  # nosec B324
        stage2 = hashlib.sha1(stage1).digest()  # nosec B324
        return stage2
