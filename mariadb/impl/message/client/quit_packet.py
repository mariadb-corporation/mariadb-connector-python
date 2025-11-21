# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Quit packet for graceful connection closure

Sends COM_QUIT command to the server before closing the connection.
"""

from typing import TYPE_CHECKING

from ...client.context import Context
from ..client_message import ClientMessage
if TYPE_CHECKING:
    from ...client.socket.stream import SyncStream

class QuitPacket(ClientMessage):
    """
    Quit packet for graceful connection closure
    
    Sends COM_QUIT command to notify the server that the client is closing.
    """
    
    COM_QUIT = 0x01
    
    def process(self, stream: 'SyncStream', context: Context) -> None:
        stream.write_byte(self.COM_QUIT)

    def is_binary(self) -> bool:
        return False
    
    def type(self) -> str:
        return "COM_QUIT"
