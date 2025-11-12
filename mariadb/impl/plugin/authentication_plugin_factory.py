# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from abc import ABC, abstractmethod
from typing import Optional, Any
from .authentication_plugin import AuthenticationPlugin


class AuthenticationPluginFactory(ABC):
    """
    Authentication plugin factory interface
    """
    
    @abstractmethod
    def type(self) -> str:
        """Authentication plugin type"""
        ...
    
    @abstractmethod
    def initialize(self, authentication_data: Optional[str], seed: bytes, 
                  conf: Any, host_address: Any) -> AuthenticationPlugin:
        """Plugin initialization"""
        ...
    
    def require_ssl(self) -> bool:
        """Check if authentication plugin requires SSL to be used"""
        return False
