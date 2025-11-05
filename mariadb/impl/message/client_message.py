# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Client Message interface for MariaDB protocol

Equivalent to the Java ClientMessage interface.
"""

from abc import ABC, abstractmethod

from ..client.context import Context

class ClientMessage(ABC):
    """
    Client message interface for MariaDB protocol
    
    Equivalent to the Java ClientMessage interface.
    """
    
    @abstractmethod
    def encode(self, context: Context) -> bytearray:
        """Encode message to writer asynchronously"""
        pass


    @abstractmethod
    def is_binary(self) -> bool:
        """indicate if message is binary"""
        return False

    @abstractmethod
    def type(self) -> str:
        """indicate message type"""
        return ""
