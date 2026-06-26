# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from .authentication_plugin import AuthenticationPlugin

if TYPE_CHECKING:
    from ..configuration import Configuration
    from ..host_address import HostAddress


class AuthenticationPluginFactory(ABC):
    """
    Authentication plugin factory interface
    """
    
    @abstractmethod
    def type(self) -> str:
        """Authentication plugin type"""
        ...
    
    @abstractmethod
    def initialize(self, authentication_data: str | None, seed: bytes,
                  conf: "Configuration", host_address: "HostAddress") -> AuthenticationPlugin:
        """Plugin initialization"""
        ...
    
    def require_ssl(self) -> bool:
        """Check if authentication plugin requires SSL to be used"""
        return False
