# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class ServerVersion:
    """Server version information"""
    raw: str = ""
    major: int = 0
    minor: int = 0
    patch: int = 0
    is_mariadb: bool = False
    
    def version_greater_or_equal(self, major: int, minor: int = 0, patch: int = 0) -> bool:
        """Check if version is greater or equal to specified version"""
        if self.major > major:
            return True
        if self.major == major:
            if self.minor > minor:
                return True
            if self.minor == minor:
                return self.patch >= patch
        return False


class Context:
    """
    Connection context holding server state and capabilities
    """
    
    def __init__(
        self,
        server_version: str = "",
        connection_id: int = -1,
        protocol_version: int = 10,
        server_capabilities: int = 0,
        server_status: int = 0,
        auth_plugin: Optional[str] = None,
        auth_data: Optional[bytes] = None,
        is_mariadb: bool = False
    ) -> None:
        """
        Initialize context
        
        Args:
            server_version: Server version string
            connection_id: Connection/thread ID
            protocol_version: Protocol version (default: 10)
            server_capabilities: Server capability flags
            server_status: Server status flags
            auth_plugin: Authentication plugin name
            auth_data: Authentication seed/data
            is_mariadb: Whether server is MariaDB
        """
        # Server information
        self.server_version: str = server_version
        self.version: ServerVersion = ServerVersion()
        self.connection_id: int = connection_id
        self.protocol_version: int = protocol_version
        
        # Capabilities
        self.server_capabilities: int = server_capabilities
        self.client_capabilities: int = 0
        self.eof_deprecated: bool = False
        self.extended_metadata: bool = False
        
        # Connection state
        self.database: str = ""
        self.charset: str = ""
        self.collation: str = ""
        
        # Server status
        self._server_status: int = server_status
        self.warning_count: int = 0
        
        # Authentication
        self.auth_plugin: Optional[str] = auth_plugin
        self.auth_data: Optional[bytes] = auth_data
        
        # Additional properties
        self.properties: Dict[str, Any] = {}
        
        self.parse_server_version(server_version, is_mariadb)
    
    # =========================================================================
    # Version Methods
    # =========================================================================
    
    def parse_server_version(self, version_string: str, is_mariadb: bool) -> None:
        """Parse server version string into major.minor.patch components"""
        self.server_version = version_string
        self.version.raw = version_string
        self.version.is_mariadb = is_mariadb
        
        # Extract version numbers
        import re
        version_match = re.search(r'(\d+)\.(\d+)\.(\d+)', version_string)
        if version_match:
            self.version.major = int(version_match.group(1))
            self.version.minor = int(version_match.group(2))
            self.version.patch = int(version_match.group(3))
    
    def get_version(self) -> ServerVersion:
        """Get server version object"""
        return self.version
    
    def is_mariadb_server(self) -> bool:
        """Check if connected to MariaDB server"""
        return self.version.is_mariadb
    
    # =========================================================================
    # Capability Methods
    # =========================================================================
    
    def has_capability(self, capability: int) -> bool:
        """Check if server has specific capability flag"""
        return (self.server_capabilities & capability) != 0
    
    def has_client_capability(self, capability: int) -> bool:
        """Check if client has specific capability flag"""
        return (self.client_capabilities & capability) != 0
    
    def isEofDeprecated(self) -> bool:
        """Check if EOF packets are deprecated (DEPRECATE_EOF capability)"""
        return self.eof_deprecated
    
    def hasExtendedMetadata(self) -> bool:
        """Check if extended metadata is enabled (EXTENDED_METADATA capability)"""
        return self.extended_metadata
    
    # =========================================================================
    # Database/Charset Methods
    # =========================================================================
       
    def set_charset(self, charset: str, collation: Optional[str] = None) -> None:
        """Set character set and optional collation"""
        self.charset = charset
        if collation:
            self.collation = collation
    
    def get_charset(self) -> str:
        """Get current character set"""
        return self.charset
    
    def get_collation(self) -> str:
        """Get current collation"""
        return self.collation
    
    def get_connection_id(self) -> int:
        """Get connection ID"""
        return self.connection_id
    
    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def server_status(self) -> int:
        """Get current server_status"""
        return self._server_status
    
    @server_status.setter
    def server_status(self, value: int) -> None:
        self._server_status = value
   
    def get_property(self, key: str, default: Any = None) -> Any:
        """Get context property by key with optional default"""
        return self.properties.get(key, default)
    
    def set_property(self, key: str, value: Any) -> None:
        """Set context property by key"""
        self.properties[key] = value
    
    def __str__(self) -> str:
        return (f"Context(server_version={self.server_version}, "
                f"connection_id={self.connection_id}, "
                f"database={self.database}, "
                f"charset={self.charset})")
    
    def __repr__(self) -> str:
        return self.__str__()
