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
Connection attributes utility

Provides default connection attributes for authentication and COM_CHANGE_USER
"""

import sys
import platform
from typing import Dict, Optional


def get_default_connection_attributes(host: Optional[str] = None, version: Optional[str] = None) -> Dict[str, str]:
    """
    Get default connection attributes
    
    Args:
        host: Server host address (optional)
        version: Connector version (optional, will try to get from mariadb module)
        
    Returns:
        Dictionary of connection attributes
    """
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
    """
    Encode connection attributes to bytes
    
    Args:
        attrs: Dictionary of connection attributes
        
    Returns:
        Encoded attributes as bytes (length-encoded key-value pairs)
    """
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
