# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab


from ...client.context import Context
from ..client_message import ClientMessage

class PingPacket(ClientMessage):
    """
    Ping packet for connection testing
    """
    __slots__ = ()
        
    def payload(self, context: Context) -> bytearray:
        return bytearray(b'\0\0\0\0\x0e')

    def is_binary(self) -> bool:
        return False

    def type(self) -> str:
        return "COM_PING"                   