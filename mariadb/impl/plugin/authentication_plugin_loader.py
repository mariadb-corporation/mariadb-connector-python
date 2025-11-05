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
Authentication Plugin Loader

Permits loading authentication plugins with support for custom plugins.
"""

from typing import Dict, Type, Optional, Any
from .authentication_plugin_factory import AuthenticationPluginFactory
from ...exceptions import OperationalError


class AuthenticationPluginLoader:
    """
    Authentication plugin loader for discovering and loading authentication plugins
    """
    
    # Registry of built-in authentication plugin factories
    _plugin_factories: Dict[str, Type[AuthenticationPluginFactory]] = {}
    
    @classmethod
    def register_plugin(cls, plugin_factory_class: Type[AuthenticationPluginFactory]) -> None:
        """Register an authentication plugin factory"""
        # Create temporary instance to get the type
        temp_instance = plugin_factory_class()
        plugin_type = temp_instance.type()
        cls._plugin_factories[plugin_type] = plugin_factory_class
    
    @classmethod
    def get(cls, plugin_type: str, conf: Any) -> AuthenticationPluginFactory:
        """Get authentication plugin factory from type string"""
        # Check for restricted authentication list
        restricted_auth = getattr(conf, 'restricted_auth', None)
        if restricted_auth:
            auth_list = restricted_auth.split(',')
            if plugin_type not in auth_list:
                raise OperationalError(
                    f"Client restrict authentication plugin to a limited set of authentication "
                    f"plugin and doesn't permit requested plugin ('{plugin_type}'). "
                    f"Current list is `restricted_auth={restricted_auth}`",
                    1251
                )
        
        # Look for the plugin factory
        if plugin_type in cls._plugin_factories:
            factory_class = cls._plugin_factories[plugin_type]
            return factory_class()
        
        # Plugin not found
        raise OperationalError(
            f"Client does not support authentication protocol requested by server. "
            f"plugin type was = '{plugin_type}'",
            1251
        )
    
    @classmethod
    def get_available_plugins(cls) -> Dict[str, Type[AuthenticationPluginFactory]]:
        """Get all available authentication plugins"""
        return cls._plugin_factories.copy()
    
    @classmethod
    def is_plugin_available(cls, plugin_type: str) -> bool:
        """Check if a plugin type is available"""
        return plugin_type in cls._plugin_factories
