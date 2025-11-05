# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Authentication Plugin Registry

Registers all built-in authentication plugins with the plugin loader.
"""

from ..authentication_plugin_loader import AuthenticationPluginLoader
from .native_password_plugin_factory import NativePasswordPluginFactory
from .caching_sha2_password_plugin_factory import CachingSha2PasswordPluginFactory
from .parsec_password_plugin_factory import ParsecPasswordPluginFactory


def register_builtin_plugins():
    """
    Register all built-in authentication plugins
    
    This function should be called during module initialization to ensure
    all standard authentication plugins are available.
    """
    AuthenticationPluginLoader.register_plugin(NativePasswordPluginFactory)
    AuthenticationPluginLoader.register_plugin(CachingSha2PasswordPluginFactory)
    AuthenticationPluginLoader.register_plugin(ParsecPasswordPluginFactory)


# Auto-register plugins when module is imported
register_builtin_plugins()
