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
    # Register native password plugin (most common)
    AuthenticationPluginLoader.register_plugin(NativePasswordPluginFactory)
    
    # Register caching SHA2 password plugin (MySQL 8.0 default)
    AuthenticationPluginLoader.register_plugin(CachingSha2PasswordPluginFactory)
       
    # Register Parsec password plugin (MariaDB Enterprise)
    AuthenticationPluginLoader.register_plugin(ParsecPasswordPluginFactory)


# Auto-register plugins when module is imported
register_builtin_plugins()
