# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Authentication Plugin Interface
"""

from abc import ABC, abstractmethod
from typing import Optional

from ..configuration import Configuration


from ..client.socket.stream import AsyncStream
from ..client.socket.stream import SyncStream
from ..client.context import Context

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
    
    def hash(self, conf: Configuration) -> Optional[bytes]:
        """Return hash for credential"""
        return None

