# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Authentication Plugin Interface
"""

from abc import ABC, abstractmethod
from typing import Optional


from ..client.socket.stream import AsyncStream
from ..client.socket.stream import SyncStream
from ..client.context import Context


class Credential:
    """
    Credential container for authentication data
    """
    
    def __init__(self, password: Optional[str] = None, token: Optional[bytes] = None):
        """Initialize credential"""
        self._password = password
        self._token = token
    
    def get_password(self) -> Optional[str]:
        """Get password"""
        return self._password
    
    def get_token(self) -> Optional[bytes]:
        """Get token"""
        return self._token


class AuthenticationPlugin(ABC):
    """
    Authentication plugin interface
    """
    
    @abstractmethod
    async def processAsync(self, stream: AsyncStream, context: Context) -> bytearray:
        """Process plugin authentication"""
        ...

    @abstractmethod
    def processSync(self, stream: SyncStream, context: Context) -> bytearray:
        """Process plugin authentication"""
        ...
    
    
    def is_mitm_proof(self) -> bool:
        """Check if plugin is MitM-proof, permitting returning HASH"""
        return False
    
    def hash(self, credential: Credential) -> Optional[bytes]:
        """Return hash for credential"""
        return None

