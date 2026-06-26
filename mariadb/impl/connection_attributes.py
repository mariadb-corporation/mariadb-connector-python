# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Connection attributes utility

Provides default connection attributes for authentication and COM_CHANGE_USER
"""

import platform
from typing import Dict

# Process-constant connection attributes (client/OS/Python info). Computed once
# on first use and cached — only "_server_host" varies per connection.
_static_attrs: Dict[str, str] | None = None


def get_default_connection_attributes(host: str) -> Dict[str, str]:
    """Get default connection attributes."""
    global _static_attrs
    if _static_attrs is None:
        # Deferred import: this module is loaded while `import mariadb` is still
        # running, so mariadb can only be referenced at call time, not import time.
        import mariadb
        _static_attrs = {
            "_client_name": "mariadb-connector-python",
            "_client_version": mariadb.__version__,
            "_os": platform.system(),
            "_python_vendor": platform.python_implementation(),
            "_python_version": platform.python_version(),
        }
    return {**_static_attrs, "_server_host": host}


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
