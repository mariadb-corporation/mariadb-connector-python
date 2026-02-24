# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from __future__ import annotations

"""
Quit packet for graceful connection closure

Sends COM_QUIT command to the server before closing the connection.
"""

from typing import TYPE_CHECKING

from ...client.context import Context
from ..client_message import ClientMessage

if TYPE_CHECKING:
    from ..payload_writer import PayloadWriter

class QuitPacket(ClientMessage):
    """
    Quit packet for graceful connection closure
    
    Sends COM_QUIT command to notify the server that the client is closing.
    """
    __slots__ = ()
    
    COM_QUIT = 0x01
    
    def payload(self, context: Context, writer: 'PayloadWriter') -> bytearray:
        return bytearray(b'\0\0\0\0\x01')

    def is_binary(self) -> bool:
        return False
    
    def type(self) -> str:
        return "COM_QUIT"
