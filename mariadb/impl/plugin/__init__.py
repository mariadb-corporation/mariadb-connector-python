# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
MariaDB Plugin System

This package contains the plugin system for MariaDB connector,
including authentication plugins and other extensible components.
"""

# Import and register authentication plugins
from .authentication.plugin_registry import register_builtin_plugins

# Auto-register built-in plugins when package is imported
register_builtin_plugins()
