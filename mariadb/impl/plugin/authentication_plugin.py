# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Authentication Plugin Interface
"""

from abc import ABC, abstractmethod
from typing import Optional, Callable, Awaitable

from ..configuration import Configuration
from ..client.socket.write_stream import AsyncWriteStream, SyncWriteStream
from ..client.context import Context

class AuthenticationPlugin(ABC):
    """
    Authentication plugin interface
    """
    
    @abstractmethod
    async def processAsync(self, read_payload_func: Callable[[], Awaitable[memoryview]], write_stream: AsyncWriteStream, context: Context) -> memoryview:
        """Process plugin authentication (async)"""
        ...

    @abstractmethod
    def processSync(self, read_payload_func: Callable[[], memoryview], write_stream: SyncWriteStream, context: Context) -> memoryview:
        """Process plugin authentication (sync)"""
        ...
    
    
    @abstractmethod
    def is_mitm_proof(self) -> bool:
        """Check if plugin is MitM-proof, permitting returning HASH"""
        ...
    
    @abstractmethod
    def hash(self, conf: Configuration) -> Optional[bytes]:
        """Return hash for credential"""
        ...

