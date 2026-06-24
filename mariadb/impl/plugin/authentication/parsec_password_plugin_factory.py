# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from __future__ import annotations

from typing import Optional, TYPE_CHECKING
from ..authentication_plugin_factory import AuthenticationPluginFactory
from ..authentication_plugin import AuthenticationPlugin
from .parsec_password_plugin import ParsecPasswordPlugin

if TYPE_CHECKING:
    from ...configuration import Configuration
    from ...host_address import HostAddress


class ParsecPasswordPluginFactory(AuthenticationPluginFactory):
    """
    Parsec password authentication plugin factory
    """
    
    def type(self) -> str:
        return "parsec"
    
    def initialize(self, authentication_data: Optional[str], seed: bytes,
                  conf: "Configuration", host_address: "HostAddress") -> AuthenticationPlugin:
        return ParsecPasswordPlugin(authentication_data, seed)
