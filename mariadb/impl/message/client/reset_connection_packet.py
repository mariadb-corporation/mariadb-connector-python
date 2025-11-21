# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Reset connection packet for MariaDB connection reset

Resets the connection state without re-authenticating.
"""
from typing import TYPE_CHECKING
from ...client.context import Context
from ..client_message import ClientMessage
if TYPE_CHECKING:
    from ...client.socket.stream import SyncStream

class ResetConnectionPacket(ClientMessage):
    """
    Reset connection packet
    
    Resets the current connection and clears session state and pending results.
    This is more efficient than reconnecting as it doesn't require re-authentication.
    """
    
    COM_RESET_CONNECTION = 0x1F
        
    def process(self, stream: 'SyncStream', context: Context) -> None:
        stream.write_byte(self.COM_RESET_CONNECTION)

    def is_binary(self) -> bool:
        return False
    
    def type(self) -> str:
        return "COM_RESET_CONNECTION"