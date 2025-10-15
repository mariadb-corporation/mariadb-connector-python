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
Host Address class for MariaDB connections

Equivalent to the Java HostAddress class.
"""

from typing import Optional
from dataclasses import dataclass


@dataclass
class HostAddress:
    """
    Host address information for MariaDB connections
    
    Equivalent to the Java HostAddress class.
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
        """
        Create HostAddress from string representation
        
        Args:
            address_string: Address in format "host:port" or "host"
            default_port: Default port if not specified
            
        Returns:
            HostAddress instance
        """
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
        """
        Convert to string representation
        
        Returns:
            String in format "host:port"
        """
        return f"{self.host}:{self.port}"
    
    def is_local(self) -> bool:
        """
        Check if this is a local address
        
        Returns:
            True if local address
        """
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
