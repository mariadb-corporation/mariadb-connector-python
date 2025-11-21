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

    @abstractmethod
    def process(self, stream: 'SyncStream', context: Context) -> None:
        """Encode message directly to stream buffer."""
        ...


    @abstractmethod
    def is_binary(self) -> bool:
        """indicate if message is binary"""
        return False

    @abstractmethod
    def type(self) -> str:
        """indicate message type"""
        return ""
