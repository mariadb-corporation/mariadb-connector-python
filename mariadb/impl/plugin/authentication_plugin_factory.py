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
Authentication Plugin Factory Interface

Equivalent to the Java AuthenticationPluginFactory interface.
"""

from abc import ABC, abstractmethod
from typing import Optional, Any
from .authentication_plugin import AuthenticationPlugin


class AuthenticationPluginFactory(ABC):
    """
    Authentication plugin factory interface
    
    Equivalent to the Java AuthenticationPluginFactory interface.
    """
    
    @abstractmethod
    def type(self) -> str:
        """
        Authentication plugin type
        
        Returns:
            Authentication plugin type (e.g., 'mysql_native_password')
        """
        pass
    
    @abstractmethod
    def initialize(self, authentication_data: Optional[str], seed: bytes, 
                  conf: Any, host_address: Any) -> AuthenticationPlugin:
        """
        Plugin initialization
        
        Args:
            authentication_data: Authentication data (password/token)
            seed: Server provided seed
            conf: Connection configuration
            host_address: Host address
            
        Returns:
            Initialized authentication plugin
        """
        pass
    
    def require_ssl(self) -> bool:
        """
        Check if authentication plugin requires SSL to be used
        
        Returns:
            True if SSL is required
        """
        return False
