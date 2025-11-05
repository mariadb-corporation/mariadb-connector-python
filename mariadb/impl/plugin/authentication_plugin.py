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
Authentication Plugin Interface
"""

from abc import ABC, abstractmethod
from typing import Optional


from ..client.socket.stream import AsyncStream
from ..client.socket.stream import SyncStream
from ..client.context import Context


class Credential:
    """
    Credential container for authentication data
    """
    
    def __init__(self, password: Optional[str] = None, token: Optional[bytes] = None):
        """Initialize credential"""
        self._password = password
        self._token = token
    
    def get_password(self) -> Optional[str]:
        """Get password"""
        return self._password
    
    def get_token(self) -> Optional[bytes]:
        """Get token"""
        return self._token


class AuthenticationPlugin(ABC):
    """
    Authentication plugin interface
    """
    
    @abstractmethod
    async def processAsync(self, stream: AsyncStream, context: Context) -> bytearray:
        """Process plugin authentication"""
        pass

    @abstractmethod
    def processSync(self, stream: SyncStream, context: Context) -> bytearray:
        """Process plugin authentication"""
        pass
    
    
    def is_mitm_proof(self) -> bool:
        """Check if plugin is MitM-proof, permitting returning HASH"""
        return False
    
    def hash(self, credential: Credential) -> Optional[bytes]:
        """Return hash for credential"""
        return None

