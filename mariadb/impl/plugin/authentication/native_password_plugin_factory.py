# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab


from typing import Optional, Any
from ..authentication_plugin_factory import AuthenticationPluginFactory
from ..authentication_plugin import AuthenticationPlugin
from .native_password_plugin import NativePasswordPlugin


class NativePasswordPluginFactory(AuthenticationPluginFactory):
    """
    Native password authentication plugin factory
    """
    
    def type(self) -> str:
        return "mysql_native_password"
    
    def initialize(self, authentication_data: Optional[str], seed: bytes, 
                  conf: Any, host_address: Any) -> AuthenticationPlugin:
        return NativePasswordPlugin(authentication_data, seed)
