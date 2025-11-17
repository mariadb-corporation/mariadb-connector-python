# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Connection attributes utility

Provides default connection attributes for authentication and COM_CHANGE_USER
"""

import sys
import platform
from typing import Dict, Optional


def get_default_connection_attributes(host: Optional[str] = None) -> Dict[str, str]:
    """Get default connection attributes"""
    attrs = {}
    
    import mariadb
    attrs["_client_name"] = "mariadb-connector-python"
    attrs["_client_version"] = mariadb.__version__
    if host:
        attrs["_server_host"] = host
    attrs["_os"] = platform.system()
    attrs["_python_vendor"] = platform.python_implementation()
    attrs["_python_version"] = platform.python_version()
    
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
