# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from __future__ import annotations

from typing import Optional, TYPE_CHECKING
from ..authentication_plugin_factory import AuthenticationPluginFactory
from ..authentication_plugin import AuthenticationPlugin
from .caching_sha2_password_plugin import CachingSha2PasswordPlugin

if TYPE_CHECKING:
    from ...configuration import Configuration
    from ...host_address import HostAddress


class CachingSha2PasswordPluginFactory(AuthenticationPluginFactory):
    """
    Caching SHA2 password authentication plugin factory
    """
    
    def type(self) -> str:
        return "caching_sha2_password"
    
    def initialize(self, authentication_data: Optional[str], seed: bytes,
                  conf: "Configuration", host_address: "HostAddress") -> AuthenticationPlugin:
        return CachingSha2PasswordPlugin(authentication_data, seed, conf, host_address)
    
    def require_ssl(self) -> bool:
        return False
