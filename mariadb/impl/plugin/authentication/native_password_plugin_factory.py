# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab


from __future__ import annotations

from typing import TYPE_CHECKING
from ..authentication_plugin_factory import AuthenticationPluginFactory
from ..authentication_plugin import AuthenticationPlugin
from .native_password_plugin import NativePasswordPlugin

if TYPE_CHECKING:
    from ...configuration import Configuration
    from ...host_address import HostAddress


class NativePasswordPluginFactory(AuthenticationPluginFactory):
    """
    Native password authentication plugin factory
    """
    
    def type(self) -> str:
        return "mysql_native_password"
    
    def initialize(self, authentication_data: str | None, seed: bytes,
                  conf: Configuration, host_address: HostAddress) -> AuthenticationPlugin:
        return NativePasswordPlugin(authentication_data, seed)
