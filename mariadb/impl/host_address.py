# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from typing import Optional
from dataclasses import dataclass


@dataclass
class HostAddress:
    """
    Host address information for MariaDB connections
    """
    
    host: str = 'localhost'
    port: int = 3306
    primary: bool = True
    
    def __post_init__(self):
        """Validate host address after initialization"""
        if not self.host:
            self.host = 'localhost'
        
        if self.port <= 0 or self.port > 65535:
            self.port = 3306
    
    @classmethod
    def from_string(cls, address_string: str, default_port: int = 3306) -> 'HostAddress':
        """Create HostAddress from string representation"""
        if ':' in address_string:
            host, port_str = address_string.rsplit(':', 1)
            try:
                port = int(port_str)
            except ValueError:
                port = default_port
        else:
            host = address_string
            port = default_port
        
        return cls(host=host, port=port)
    
    def to_string(self) -> str:
        """Convert to string representation"""
        return f"{self.host}:{self.port}"
    
    def is_local(self) -> bool:
        """Check if this is a local address"""
        return self.host in ('localhost', '127.0.0.1', '::1')
    
    def __str__(self) -> str:
        return self.to_string()
    
    def __repr__(self) -> str:
        return f"HostAddress(host='{self.host}', port={self.port}, primary={self.primary})"
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, HostAddress):
            return False
        return self.host == other.host and self.port == other.port
    
    def __hash__(self) -> int:
        return hash((self.host, self.port))
