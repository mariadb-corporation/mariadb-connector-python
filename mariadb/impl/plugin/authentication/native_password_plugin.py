# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from __future__ import annotations

import hashlib
from typing import Optional

from ...configuration import Configuration

from typing import Callable, Awaitable
from ...client.context import Context
from ..authentication_plugin import AuthenticationPlugin


class NativePasswordPlugin(AuthenticationPlugin):
    """
    Native password authentication plugin implementation
    See https://mariadb.com/kb/en/library/authentication-plugin-mysql_native_password/
    """
        
    def __init__(self, authentication_data: Optional[str], seed: bytes):
        """Initialize plugin with authentication data and seed"""
        self.authentication_data = authentication_data
        self.seed = seed

    @staticmethod
    def encrypt_password(password: Optional[str], seed: bytes) -> bytearray:
        """Encrypts a password using MySQL native password algorithm"""
        if password is None or password == "":
            return b''
        
        password_bytes = password.encode('utf-8')
        stage1 = hashlib.sha1(password_bytes).digest()
        stage2 = hashlib.sha1(stage1).digest()
        digest = hashlib.sha1()
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
    
    def hash(self, conf: Configuration) -> Optional[bytes]:
        """Return hash for credential (double SHA1)"""
        password = conf.password
        if password is None:
            return None
        password_bytes = password.encode('utf-8')
        stage1 = hashlib.sha1(password_bytes).digest()
        stage2 = hashlib.sha1(stage1).digest()       
        return stage2
