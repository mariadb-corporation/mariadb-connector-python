#
# Copyright (C) 2020-2021 Georg Richter and MariaDB Corporation AB

# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Library General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.

# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Library General Public License for more details.

# You should have received a copy of the GNU Library General Public
# License along with this library; if not see <http://www.gnu.org/licenses>
# or write to the Free Software Foundation, Inc.,
# 51 Franklin St., Fifth Floor, Boston, MA 02110, USA
#

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
