# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

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
        # TODO: implement restricted_auth
        #restricted_auth = getattr(conf, 'restricted_auth', None)
        #if restricted_auth:
        #    auth_list = restricted_auth.split(',')
        #    if plugin_type not in auth_list:
        #        raise OperationalError(
        #            f"Client restrict authentication plugin to a limited set of authentication "
        #            f"plugin and doesn't permit requested plugin ('{plugin_type}'). "
        #            f"Current list is `restricted_auth={restricted_auth}`",
        #            1251
        #        )
        
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
    
