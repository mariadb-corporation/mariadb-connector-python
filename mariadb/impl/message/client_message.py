# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ..client.context import Context

if TYPE_CHECKING:
    from ..client.socket.stream import SyncStream

class ClientMessage(ABC):
    """
    Client message interface for MariaDB protocol
    """
    __slots__ = ()

    @abstractmethod
    def payload(self, context: Context) -> bytearray:
        """Generate message payload as bytearray (without packet header)."""
        ...

    @abstractmethod
    def is_binary(self) -> bool:
        """indicate if message is binary"""
        return False

    @abstractmethod
    def type(self) -> str:
        """indicate message type"""
        return ""
    
    def get_sql(self) -> str:
        """Get SQL string for LOAD LOCAL INFILE validation (optional)"""
        return None
