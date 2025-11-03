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
Native Password Authentication Plugin Factory

Factory for creating NativePasswordPlugin instances.
Equivalent to the Java NativePasswordPluginFactory class.
"""

from typing import Optional, Any
from ..authentication_plugin_factory import AuthenticationPluginFactory
from ..authentication_plugin import AuthenticationPlugin
from .native_password_plugin import NativePasswordPlugin


class NativePasswordPluginFactory(AuthenticationPluginFactory):
    """
    Native password authentication plugin factory
    
    Equivalent to the Java NativePasswordPluginFactory class.
    """
    
    def type(self) -> str:
        """
        Get authentication plugin type
        
        Returns:
            Plugin type string
        """
        return "mysql_native_password"
    
    def initialize(self, authentication_data: Optional[str], seed: bytes, 
                  conf: Any, host_address: Any) -> AuthenticationPlugin:
        """
        Initialize native password plugin
        Returns:
            Initialized NativePasswordPlugin
        """
        return NativePasswordPlugin(authentication_data, seed)
