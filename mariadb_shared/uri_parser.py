# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
URI parser for MariaDB connection strings

Supports URI format: mariadb://[user[:password]@][host][:port][/database][?option1=value1&option2=value2]
"""

from typing import Dict, Any, Optional
from urllib.parse import urlparse, parse_qs, unquote


def parse_connection_uri(uri: str) -> Dict[str, Any]:
    """
    Parse a MariaDB connection URI into connection parameters
    
    Args:
        uri: Connection URI in format mariadb://[user[:password]@][host][:port][/database][?options]
        
    Returns:
        Dictionary of connection parameters
        
    Examples:
        >>> parse_connection_uri("mariadb://root:secret@localhost:3306/mydb")
        {'user': 'root', 'password': 'secret', 'host': 'localhost', 'port': 3306, 'database': 'mydb'}
        
        >>> parse_connection_uri("mariadb://localhost/mydb?charset=utf8mb4&ssl=true")
        {'host': 'localhost', 'database': 'mydb', 'charset': 'utf8mb4', 'ssl': True}
    """
    # Parse the URI
    parsed = urlparse(uri)
    
    # Validate scheme
    if parsed.scheme not in ('mariadb', 'mysql'):
        raise ValueError(f"Invalid URI scheme: {parsed.scheme}. Expected 'mariadb' or 'mysql'")
    
    params = {}
    
    # Extract user and password
    if parsed.username:
        params['user'] = unquote(parsed.username)
    if parsed.password is not None:  # Allow empty password
        params['password'] = unquote(parsed.password)
    
    # Extract host
    if parsed.hostname:
        params['host'] = parsed.hostname
    
    # Extract port
    if parsed.port:
        params['port'] = parsed.port
    
    # Extract database
    if parsed.path and len(parsed.path) > 1:
        # Remove leading slash
        params['database'] = unquote(parsed.path[1:])
    
    # Extract query parameters
    if parsed.query:
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        for key, values in query_params.items():
            # Use the last value if multiple values are provided
            value = values[-1] if values else ''
            
            # Convert boolean strings
            if value.lower() in ('true', '1', 'yes', 'on'):
                params[key] = True
            elif value.lower() in ('false', '0', 'no', 'off'):
                params[key] = False
            # Convert numeric strings
            elif value.isdigit():
                params[key] = int(value)
            else:
                params[key] = unquote(value)
    
    return params


def is_connection_uri(value: str) -> bool:
    """
    Check if a string is a connection URI
    
    Args:
        value: String to check
        
    Returns:
        True if the string appears to be a connection URI
    """
    if not isinstance(value, str):
        return False
    
    return value.startswith('mariadb://') or value.startswith('mysql://')
