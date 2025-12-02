# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Reset connection packet for MariaDB connection reset

Resets the connection state without re-authenticating.
"""
from ...client.context import Context
from ..client_message import ClientMessage

class ResetConnectionPacket(ClientMessage):
    """
    Reset connection packet
    
    Resets the current connection and clears session state and pending results.
    This is more efficient than reconnecting as it doesn't require re-authentication.
    """
    __slots__ = ()
    
    COM_RESET_CONNECTION = 0x1F
        
    def payload(self, context: Context) -> bytearray:
        return bytearray(b'\0\0\0\0\x1f')

    def is_binary(self) -> bool:
        return False
    
    def type(self) -> str:
        return "COM_RESET_CONNECTION"