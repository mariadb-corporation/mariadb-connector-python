# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from abc import ABC, abstractmethod

from ..client.context import Context

class ServerMessage(ABC):
    """
    Server message interface for MariaDB protocol
    """
    
    @abstractmethod
    def decode(self, data: bytearray, context: Context) -> bytearray:
        """Decode message from reader"""
        ...
