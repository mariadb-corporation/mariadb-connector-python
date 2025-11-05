# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from typing import Optional, Any
from ..authentication_plugin_factory import AuthenticationPluginFactory
from ..authentication_plugin import AuthenticationPlugin
from .parsec_password_plugin import ParsecPasswordPlugin


class ParsecPasswordPluginFactory(AuthenticationPluginFactory):
    """
    Parsec password authentication plugin factory
    """
    
    def type(self) -> str:
        """Get authentication plugin type"""
        return "parsec"
    
    def initialize(self, authentication_data: Optional[str], seed: bytes, 
                  conf: Any, host_address: Any) -> AuthenticationPlugin:
        """Initialize PARSEC password plugin with authentication data and seed"""
        return ParsecPasswordPlugin(authentication_data, seed)
