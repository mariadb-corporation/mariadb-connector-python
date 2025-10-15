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
Configuration class for MariaDB connections

Equivalent to the Java Configuration class.
"""

from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field


@dataclass
class Configuration:
    """
    Configuration holder for MariaDB connection parameters
    
    Equivalent to the Java Configuration class.
    """
    
    # Connection parameters
    host: str = 'localhost'
    port: int = 3306
    user: Optional[str] = None
    password: Optional[str] = None
    database: Optional[str] = None
    
    # Socket parameters
    socket_path: Optional[str] = None
    socket_timeout: int = 30000  # 30 seconds
    connect_timeout: int = 10000  # 10 seconds
    
    # SSL parameters
    ssl: bool = False
    ssl_key: Optional[str] = None
    ssl_ca: Optional[str] = None
    ssl_cert: Optional[str] = None
    ssl_crl: Optional[str] = None
    ssl_cipher: Optional[str] = None
    ssl_capath: Optional[str] = None
    ssl_crlpath: Optional[str] = None
    ssl_verify_cert: bool = False
    tls_version: Optional[str] = None  # TLS version: 'TLSv1.2', 'TLSv1.3' or 'TLSv1.2,TLSv1.3' (automatically enables SSL)
    
    # Connection behavior
    autocommit: bool = False
    read_only: bool = False
    
    # Protocol parameters
    use_compression: bool = False  # Also accessible as 'compress'
    
    # Timeouts
    query_timeout: int = 0  # No timeout
    max_allowed_packet: int = 16777216  # 16MB
    
    # Character encoding
    character_encoding: str = 'utf8mb4'
    
    # Debug options
    debug: bool = False
    
    # Initialization command
    init_command: Optional[str] = None
    
    # Additional options
    non_mapped_options: Dict[str, Any] = field(default_factory=dict)
    
    @staticmethod
    def parse_hosts(host_string: str, default_port: int = 3306) -> List[Tuple[str, int]]:
        """
        Parse host string into list of (host, port) tuples
        
        Args:
            host_string: Host string like 'host1:3306,host2:3308' or 'localhost'
            default_port: Default port to use if not specified in host
            
        Returns:
            List of (host, port) tuples
        """
        hosts = []
        
        # Split by comma for multiple hosts
        host_parts = [h.strip() for h in host_string.split(',') if h.strip()]
        
        for host_part in host_parts:
            if ':' in host_part:
                # Host has port specified
                host, port_str = host_part.rsplit(':', 1)
                try:
                    port = int(port_str)
                except ValueError:
                    # Invalid port, use default
                    host = host_part
                    port = default_port
            else:
                # No port specified, use default
                host = host_part
                port = default_port
            
            hosts.append((host.strip(), port))
        
        return hosts
    
    def get_hosts(self) -> List[Tuple[str, int]]:
        """
        Get list of (host, port) tuples for connection attempts
        
        Returns:
            List of (host, port) tuples to try in order
        """
        return self.parse_hosts(self.host, self.port)
    
    @classmethod
    def from_dict(cls, params: Dict[str, Any]) -> 'Configuration':
        """
        Create Configuration from dictionary
        
        Args:
            params: Connection parameters dictionary
            
        Returns:
            Configuration instance
        """
        config = cls()
        
        # Map common parameters
        if 'host' in params:
            config.host = params['host']
        if 'port' in params:
            config.port = int(params['port'])
        if 'user' in params or 'username' in params:
            config.user = params.get('user') or params.get('username')
        if 'password' in params:
            config.password = params['password']
        if 'database' in params or 'db' in params:
            config.database = params.get('database') or params.get('db')
        
        # Socket parameters
        if 'socket_path' in params:
            config.socket_path = params['socket_path']
        if 'socket_timeout' in params:
            config.socket_timeout = int(params['socket_timeout'])
        if 'connect_timeout' in params:
            config.connect_timeout = int(params['connect_timeout'])
        
        # SSL parameters
        if 'ssl' in params or 'use_ssl' in params:
            config.ssl = bool(params.get('ssl', params.get('use_ssl', False)))
        if 'ssl_key' in params:
            config.ssl_key = params['ssl_key']
        if 'ssl_ca' in params:
            config.ssl_ca = params['ssl_ca']
        if 'ssl_cert' in params:
            config.ssl_cert = params['ssl_cert']
        if 'ssl_crl' in params:
            config.ssl_crl = params['ssl_crl']
        if 'ssl_cipher' in params:
            config.ssl_cipher = params['ssl_cipher']
        if 'ssl_capath' in params:
            config.ssl_capath = params['ssl_capath']
        if 'ssl_crlpath' in params:
            config.ssl_crlpath = params['ssl_crlpath']
        if 'ssl_verify_cert' in params:
            config.ssl_verify_cert = bool(params['ssl_verify_cert'])
        if 'tls_version' in params:
            config.tls_version = params['tls_version']
            # Automatically enable SSL if tls_version is specified
            if config.tls_version:
                config.ssl = True
        
        # Connection behavior
        if 'autocommit' in params:
            config.autocommit = bool(params['autocommit'])
        if 'read_only' in params:
            config.read_only = bool(params['read_only'])
        
        # Protocol parameters
        if 'use_compression' in params or 'compress' in params:
            config.use_compression = bool(params.get('use_compression', params.get('compress', False)))
        
        # Timeouts
        if 'query_timeout' in params:
            config.query_timeout = int(params['query_timeout'])
        if 'max_allowed_packet' in params:
            config.max_allowed_packet = int(params['max_allowed_packet'])
        
        # Character encoding
        if 'character_encoding' in params or 'charset' in params:
            config.character_encoding = params.get('character_encoding') or params.get('charset', 'utf8mb4')
        
        # Debug options
        if 'debug' in params:
            config.debug = bool(params['debug'])
        # Initialization command
        if 'init_command' in params:
            config.init_command = params['init_command']
        
        # Store any unmapped options
        valid_params = {
            'host', 'hostname', 'server', 'user', 'username', 'password', 'passwd',
            'database', 'db', 'schema', 'port',
            'unix_socket', 'socket', 'named_pipe', 'pipe_name',
            'ssl', 'use_ssl', 'ssl_key', 'ssl_ca', 'ssl_cert', 'ssl_crl',
            'ssl_cipher', 'ssl_capath', 'ssl_crlpath', 'ssl_verify_cert', 'tls_version',
            'autocommit', 'read_only',
            'use_compression', 'compress',
            'query_timeout', 'max_allowed_packet',
            'character_encoding', 'charset', 'debug', 'init_command'
        }
        
        for key, value in params.items():
            if key not in valid_params:
                config.non_mapped_options[key] = value
        
        return config
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert Configuration to dictionary
        
        Returns:
            Dictionary representation
        """
        result = {
            'host': self.host,
            'port': self.port,
            'user': self.user,
            'password': self.password,
            'database': self.database,
            'socket_path': self.socket_path,
            'socket_timeout': self.socket_timeout,
            'connect_timeout': self.connect_timeout,
            'ssl': self.ssl,
            'ssl_key': self.ssl_key,
            'ssl_ca': self.ssl_ca,
            'ssl_cert': self.ssl_cert,
            'ssl_crl': self.ssl_crl,
            'ssl_cipher': self.ssl_cipher,
            'ssl_capath': self.ssl_capath,
            'ssl_crlpath': self.ssl_crlpath,
            'ssl_verify_cert': self.ssl_verify_cert,
            'tls_version': self.tls_version,
            'autocommit': self.autocommit,
            'read_only': self.read_only,
            'use_compression': self.use_compression,
            'query_timeout': self.query_timeout,
            'max_allowed_packet': self.max_allowed_packet,
            'character_encoding': self.character_encoding,
            'debug': self.debug,
            'init_command': self.init_command
        }
        
        # Add non-mapped options
        result.update(self.non_mapped_options)
        
        return result
    
    def __str__(self) -> str:
        return f"Configuration(host={self.host}, port={self.port}, user={self.user}, database={self.database})"
    
    def __repr__(self) -> str:
        return self.__str__()
