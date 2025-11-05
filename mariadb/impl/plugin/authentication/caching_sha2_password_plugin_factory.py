# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from typing import Optional, Any
from ..authentication_plugin_factory import AuthenticationPluginFactory
from ..authentication_plugin import AuthenticationPlugin
from .caching_sha2_password_plugin import CachingSha2PasswordPlugin


class CachingSha2PasswordPluginFactory(AuthenticationPluginFactory):
    """
    Caching SHA2 password authentication plugin factory
    """
    
    def type(self) -> str:
        """Get authentication plugin type"""
        return "caching_sha2_password"
    
    def initialize(self, authentication_data: Optional[str], seed: bytes, 
                  conf: Any, host_address: Any) -> AuthenticationPlugin:
        """Initialize caching SHA2 password plugin with authentication data and seed"""
        return CachingSha2PasswordPlugin(authentication_data, seed, conf, host_address)
    
    def require_ssl(self) -> bool:
        """Check if plugin requires SSL (False for caching_sha2_password)"""
        return False
