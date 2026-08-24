# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from __future__ import annotations

from typing import TYPE_CHECKING
from ..authentication_plugin_factory import AuthenticationPluginFactory
from ..authentication_plugin import AuthenticationPlugin
from .caching_sha2_password_plugin import CachingSha2PasswordPlugin

if TYPE_CHECKING:
    from ...configuration import Configuration
    from ...host_address import HostAddress


class CachingSha2PasswordPluginFactory(AuthenticationPluginFactory):
    """
    Caching SHA2 password authentication plugin factory
    """
    
    def type(self) -> str:
        return "caching_sha2_password"
    
    def initialize(self, authentication_data: str | None, seed: bytes,
                  conf: "Configuration", host_address: "HostAddress") -> AuthenticationPlugin:
        return CachingSha2PasswordPlugin(authentication_data, seed, conf, host_address)
    
    def require_ssl(self) -> bool:
        return False

    def fips_compliant(self) -> bool:
        # The scramble is SHA-256 based, and the clear-text-over-TLS follow-up
        # uses no hash at all, so the plugin itself is FIPS-usable. Its one
        # non-compliant branch is the RSA public-key exchange (defined with
        # RSA-OAEP over SHA-1), which is refused separately in
        # CachingSha2PasswordPlugin._get_rsa_encrytped_pwd rather than by
        # rejecting the plugin as a whole.
        return True
