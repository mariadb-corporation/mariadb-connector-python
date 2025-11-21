# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab


from typing import TYPE_CHECKING
from ...client.context import Context
from ..client_message import ClientMessage

if TYPE_CHECKING:
    from ...client.socket.stream import SyncStream

class PingPacket(ClientMessage):
    """
    Ping packet for connection testing
    """
    
    COM_PING = 0x0E
        
    def process(self, stream: 'SyncStream', context: Context) -> None:
        stream.write_byte(self.COM_PING)

    def is_binary(self) -> bool:
        return False

    def type(self) -> str:
        return "COM_PING"                   