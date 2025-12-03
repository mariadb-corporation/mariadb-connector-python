# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from .host_address import HostAddress


@dataclass
class Configuration:
    """
    Configuration holder for MariaDB connection parameters
    """
    
    # Connection parameters
    host: str = 'localhost'
    port: int = 3306
    user: Optional[str] = None
    password: Optional[str] = None
    database: Optional[str] = None
    
    # Socket parameters
    unix_socket: Optional[str] = None
    socket_timeout: float = 30  # 30 seconds
    connect_timeout: float = 10  # 10 seconds
    
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
    compress: bool = False
    local_infile: Optional[bool] = None  # Enable LOAD DATA LOCAL INFILE
    
    # Timeouts
    query_timeout: int = 0  # No timeout
    max_allowed_packet: int = 16777216  # 16MB
    
    # Character encoding
    character_encoding: str = 'utf8mb4'
    
    # Initialization command
    init_command: Optional[str] = None
    
    # Type conversion options
    converter: Optional[Dict[int, callable]] = None
    
    # Result format options
    named_tuple: bool = False
    dictionary: bool = False
    native_object: bool = False
    
    # Prepared statement caching
    cache_prep_stmts: bool = True  # Enable prepared statement caching
    prep_stmt_cache_size: int = 100  # Maximum number of cached prepared statements
    
    # Pipeline option
    pipeline: bool = True  # Enable pipelining for prepared statements
    
    # Additional options
    non_mapped_options: Dict[str, Any] = field(default_factory=dict)
    
    @staticmethod
    def parse_hosts(host_string: str, default_port: int = 3306) -> List[HostAddress]:
        """Parse host string into list of (host, port) tuples for failover"""
        hosts: List[HostAddress] = []
        
        # Split by comma for multiple hosts
        if (host_string is None):
            return hosts
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
            
            hosts.append(HostAddress(host.strip(), port))
        
        return hosts
    
    def get_hosts(self) -> List[HostAddress]:
        """Get list of (host, port) tuples for connection attempts"""
        return self.parse_hosts(self.host, self.port)
    
    @classmethod
    def from_dict(cls, params: Dict[str, Any]) -> 'Configuration':
        """Create Configuration instance from dictionary of parameters"""
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
        if 'unix_socket' in params:
            config.unix_socket = params['unix_socket']
        if 'socket_timeout' in params:
            config.socket_timeout = int(params['socket_timeout'])
        # read_timeout and write_timeout are aliases for socket_timeout
        if 'read_timeout' in params:
            config.socket_timeout = int(params['read_timeout'])
        if 'write_timeout' in params:
            config.socket_timeout = int(params['write_timeout'])
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
        if 'compress' in params:
            config.compress = bool(params['compress'])
        if 'local_infile' in params:
            config.local_infile = bool(params['local_infile']) if params['local_infile'] is not None else None
        
        # Timeouts
        if 'query_timeout' in params:
            config.query_timeout = int(params['query_timeout'])
        if 'max_allowed_packet' in params:
            config.max_allowed_packet = int(params['max_allowed_packet'])
        
        # Character encoding
        if 'character_encoding' in params or 'charset' in params:
            config.character_encoding = params.get('character_encoding') or params.get('charset', 'utf8mb4')
        
        # Initialization command
        if 'init_command' in params:
            config.init_command = params['init_command']
        
        # Type conversion options
        if 'converter' in params:
            config.converter = params['converter']
        
        # Result format options
        if 'named_tuple' in params:
            config.named_tuple = bool(params['named_tuple'])
        if 'dictionary' in params:
            config.dictionary = bool(params['dictionary'])
        if 'native_object' in params:
            config.native_object = bool(params['native_object'])
        
        # Prepared statement caching
        if 'cache_prep_stmts' in params:
            config.cache_prep_stmts = bool(params['cache_prep_stmts'])
        if 'prep_stmt_cache_size' in params:
            config.prep_stmt_cache_size = int(params['prep_stmt_cache_size'])
        
        # Pipeline option
        if 'pipeline' in params:
            config.pipeline = bool(params['pipeline'])
        
        # Store any unmapped options
        valid_params = {
            'host', 'hostname', 'server', 'user', 'username', 'password', 'passwd',
            'database', 'db', 'schema', 'port',
            'unix_socket', 'socket', 'named_pipe', 'pipe_name',
            'socket_timeout', 'read_timeout', 'write_timeout', 'connect_timeout',
            'ssl', 'use_ssl', 'ssl_key', 'ssl_ca', 'ssl_cert', 'ssl_crl',
            'ssl_cipher', 'ssl_capath', 'ssl_crlpath', 'ssl_verify_cert', 'tls_version',
            'autocommit', 'read_only',
            'compress', 'local_infile',
            'query_timeout', 'max_allowed_packet',
            'character_encoding', 'charset', 'init_command', 'converter', 'named_tuple', 'dictionary', 'native_object',
            'cache_prep_stmts', 'prep_stmt_cache_size', 'pipeline'
        }
        
        for key, value in params.items():
            if key not in valid_params:
                config.non_mapped_options[key] = value
        
        return config
    