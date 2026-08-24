# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Authentication Plugin Loader

Permits loading authentication plugins with support for custom plugins.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Type
from .authentication_plugin_factory import AuthenticationPluginFactory
from ..fips import is_fips_mode
from ...exceptions import OperationalError

if TYPE_CHECKING:
    from ..configuration import Configuration


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
    def get(cls, plugin_type: str, conf: "Configuration") -> AuthenticationPluginFactory:
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
        factory_class = cls._plugin_factories.get(plugin_type)
        if factory_class is None:
            # Plugin not found
            raise OperationalError(
                f"Client does not support authentication protocol requested by server. "
                f"plugin type was = '{plugin_type}'",
                1251
            )

        factory = factory_class()

        # On a FIPS-enforcing crypto backend, refuse a plugin built on
        # primitives the FIPS provider does not offer (SHA-1, for
        # mysql_native_password) before it sends anything. Without this the
        # failure surfaces either as an opaque hashlib error or, worse, as a
        # bare "access denied" from the server. See mariadb.impl.fips.
        if is_fips_mode() and not factory.fips_compliant():
            raise OperationalError(
                f"Authentication plugin '{plugin_type}' cannot be used with a "
                f"FIPS-enabled crypto backend: it relies on primitives the FIPS "
                f"provider refuses (SHA-1, in the case of mysql_native_password). "
                f"Grant this account a FIPS-compliant authentication plugin such "
                f"as 'parsec'.",
                1251
            )

        return factory
    
