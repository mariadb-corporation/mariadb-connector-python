# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from __future__ import annotations

from typing import TYPE_CHECKING

from ...client.context import Context
from ..client_message import ClientMessage

if TYPE_CHECKING:
    from ..payload_writer import PayloadWriter

class PingPacket(ClientMessage):
    """
    Ping packet for connection testing
    """
    __slots__ = ()
        
    def payload(self, context: Context, writer: 'PayloadWriter') -> bytearray:
        return bytearray(b'\0\0\0\0\x0e')

    def is_binary(self) -> bool:
        return False

    def type(self) -> str:
        return "COM_PING"                   