# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Connection attributes utility

Provides default connection attributes for authentication and COM_CHANGE_USER
"""

import sys
import platform
from typing import Dict, Optional


def get_default_connection_attributes(host: Optional[str] = None, version: Optional[str] = None) -> Dict[str, str]:
    """Get default connection attributes"""
    attrs = {}
    
    # Client name
    attrs["_client_name"] = "mariadb-connector-python"
    
    # Client version
    if version:
        attrs["_client_version"] = version
    else:
        # Try to get version from mariadb module
        try:
            import mariadb
            attrs["_client_version"] = mariadb.__version__
        except (ImportError, AttributeError):
            attrs["_client_version"] = "2.0.0.dev"
    
    # Server host
    if host:
        attrs["_server_host"] = host
    
    # Operating system
    try:
        attrs["_os"] = platform.system()
    except Exception:
        attrs["_os"] = "Unknown"
    
    # Python implementation (CPython, PyPy, Jython, etc.)
    try:
        attrs["_python_vendor"] = platform.python_implementation()
    except Exception:
        attrs["_python_vendor"] = "Unknown"
    
    # Python version
    try:
        attrs["_python_version"] = platform.python_version()
    except Exception:
        attrs["_python_version"] = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    
    return attrs


def encode_connection_attributes(attrs: Dict[str, str]) -> bytes:
    """Encode connection attributes to bytes"""
    import io
    
    attr_buffer = io.BytesIO()
    
    for key, value in attrs.items():
        key_bytes = key.encode('utf-8')
        value_bytes = str(value).encode('utf-8')
        
        # Write length-encoded strings
        # For small lengths (< 251), just write the length as a single byte
        attr_buffer.write(len(key_bytes).to_bytes(1, 'little'))
        attr_buffer.write(key_bytes)
        attr_buffer.write(len(value_bytes).to_bytes(1, 'little'))
        attr_buffer.write(value_bytes)
    
    return attr_buffer.getvalue()
