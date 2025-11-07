# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from __future__ import annotations

import hashlib
from typing import Optional

from ...client.socket.stream import AsyncStream, SyncStream
from ...client.context import Context
from ..authentication_plugin import AuthenticationPlugin, Credential


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
    def encrypt_password(password: Optional[str], seed: bytes) -> bytes:
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
        result = bytes(a ^ b for a, b in zip(stage1, stage3))
        return result
    
    def _build_auth_payload(self) -> bytes:
        """Build authentication payload"""
        if self.authentication_data is None:
            return bytes()
        
        # Truncate seed to 20 bytes (remove null terminator if present)
        truncated_seed = self.seed[:20] if len(self.seed) > 20 else self.seed
        
        # Encrypt password
        return self.encrypt_password(self.authentication_data, truncated_seed)
    
    async def processAsync(self, stream: AsyncStream, context: Context) -> bytes:
        """Process native password plugin authentication (async)"""
        encrypted = self._build_auth_payload()
        await stream.send_payload(encrypted, "NATIVE_PASSWORD", reset_sequence=False)
        return await stream.read_payload()
    
    def processSync(self, stream: SyncStream, context: Context) -> bytes:
        """Process native password plugin authentication (sync)"""
        encrypted = self._build_auth_payload()
        stream.send_payload(encrypted, "NATIVE_PASSWORD", reset_sequence=False)
        return stream.read_payload()
    
    def is_mitm_proof(self) -> bool:
        """Native password plugin is MitM-proof"""
        return True
    
    def hash(self, credential: Credential) -> Optional[bytes]:
        """Return hash for credential (double SHA1)"""
        password = credential.get_password()
        if password is None:
            return None
        password_bytes = password.encode('utf-8')
        stage1 = hashlib.sha1(password_bytes).digest()
        stage2 = hashlib.sha1(stage1).digest()       
        return stage2
