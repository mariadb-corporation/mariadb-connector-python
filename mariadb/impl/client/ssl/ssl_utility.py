# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
SSL Utility for MariaDB connections

Provides SSL/TLS socket creation utilities for database connections.
"""

import ssl
from typing import Optional, Tuple
from ...configuration import Configuration
from ....exceptions import OperationalError


class SSLUtility:
    """
    SSL utility for MariaDB connections
    
    Provides static methods for creating SSL-wrapped sockets.
    """
    
    @staticmethod
    def create_ssl_context(configuration: Configuration) -> ssl.SSLContext:

        """
        Create SSL context based on configuration
        
        Returns:
            SSL context
            
        Raises:
            OperationalError: If SSL context creation fails
        """
        try:
            # Create SSL context
            context = ssl.create_default_context()
            
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.maximum_version = ssl.TLSVersion.TLSv1_3
            
            # Configure SSL context based on configuration
            if configuration.ssl_ca:
                context.load_verify_locations(cafile=configuration.ssl_ca)
            
            if configuration.ssl_capath:
                context.load_verify_locations(capath=configuration.ssl_capath)
            
            if configuration.ssl_cert and configuration.ssl_key:
                context.load_cert_chain(
                    certfile=configuration.ssl_cert,
                    keyfile=configuration.ssl_key
                )
            
            if configuration.ssl_crl:
                # Load CRL if specified
                context.load_verify_locations(crlfile=configuration.ssl_crl)
                context.verify_flags |= ssl.VERIFY_CRL_CHECK_LEAF
            
            if configuration.ssl_cipher:
                context.set_ciphers(configuration.ssl_cipher)
            
            # Configure TLS version if specified
            if configuration.tls_version:
                SSLUtility._configure_tls_versions(context, configuration)
            
            # Configure certificate verification
            if not configuration.ssl_verify_cert:
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            else:
                context.check_hostname = True
                context.verify_mode = ssl.CERT_REQUIRED
            
            return context
            
        except Exception as e:
            raise OperationalError(f"Failed to create SSL context: {e}")
    
    @staticmethod
    def _configure_tls_versions(context: ssl.SSLContext, configuration: Configuration) -> None:
        """
        Configure TLS versions from comma-separated string
        
        Args:
            context: SSL context to configure
            configuration: Connection configuration with TLS version settings
        """
        # Map TLS version strings to SSL constants
        tls_version_map = {
            'TLSv1_3': ssl.TLSVersion.TLSv1_3,
            'TLSV1_3': ssl.TLSVersion.TLSv1_3,
            'TLSv1.3': ssl.TLSVersion.TLSv1_3,
            'TLS1_3': ssl.TLSVersion.TLSv1_3,
            'TLSv1_2': ssl.TLSVersion.TLSv1_2,
            'TLSV1_2': ssl.TLSVersion.TLSv1_2,
            'TLSv1.2': ssl.TLSVersion.TLSv1_2,
            'TLS1_2': ssl.TLSVersion.TLSv1_2,
            'TLSv1_1': ssl.TLSVersion.TLSv1_1,
            'TLSV1_1': ssl.TLSVersion.TLSv1_1,
            'TLSv1.1': ssl.TLSVersion.TLSv1_1,
            'TLS1_1': ssl.TLSVersion.TLSv1_1,
            'TLSv1': ssl.TLSVersion.TLSv1,
            'TLSV1': ssl.TLSVersion.TLSv1,
            'TLS1': ssl.TLSVersion.TLSv1,
        }
        
        # Parse comma-separated TLS versions
        tls_versions_str = configuration.tls_version.strip()
        if ',' in tls_versions_str:
            # Multiple versions specified - find min and max
            version_list = [v.strip().upper().replace('.', '_') for v in tls_versions_str.split(',')]
            valid_versions = []
            
            for version in version_list:
                if version in tls_version_map:
                    valid_versions.append(tls_version_map[version])
                else:
                    import warnings
                    warnings.warn(f"Unsupported TLS version '{version}' in list, ignoring")
            
            if valid_versions:
                # Set minimum to lowest version, maximum to highest version
                context.minimum_version = min(valid_versions)
                context.maximum_version = max(valid_versions)
            else:
                import warnings
                warnings.warn(f"No valid TLS versions found in '{tls_versions_str}', using default")
        else:
            # Single version specified - set both min and max to same version
            tls_version = tls_versions_str.upper().replace('.', '_')
            
            if tls_version in tls_version_map:
                ssl_version = tls_version_map[tls_version]
                context.minimum_version = ssl_version
                context.maximum_version = ssl_version  # Force exact version
            else:
                import warnings
                warnings.warn(f"Unsupported TLS version '{configuration.tls_version}', using default")
    
    @staticmethod
    def prepare_ssl_context(
        configuration: Configuration,
        context
    ) -> Tuple[ssl.SSLContext, Optional['SSLFingerprintValidator']]:
        """
        Prepare SSL context with optional fingerprint validation support.
        
        This method handles:
        - Disabling SSL verification for local connections (matching C connector behavior)
        - Setting up fingerprint validation for MariaDB >= 11.4.1 when appropriate
        - Creating unverified context for fingerprint capture
        
        Args:
            configuration: Connection configuration
            context: Connection context with server version info
            is_local_connection: Whether connection is to localhost
            
        Returns:
            Tuple of (ssl_context, fingerprint_validator or None)
            
        Raises:
            OperationalError: If SSL context preparation fails
        """
        from .ssl_fingerprint_validator import SSLFingerprintValidator
        
        # Create SSL context
        ssl_context = SSLUtility.create_ssl_context(configuration)
        
        # Check if we need fingerprint validation (MariaDB-specific feature)
        # Only enable when: MariaDB server >= 11.4.1 + ssl_verify_cert enabled + no SSL CA configured + password provided
        use_fingerprint_validation = (
            context.is_mariadb_server() and
            context.get_version().version_greater_or_equal(11, 4, 1) and
            configuration.ssl_verify_cert and
            not configuration.ssl_ca and
            configuration.password is not None and 
            configuration.password != ""
        )
        
        cert_fingerprint_validator = None
        if use_fingerprint_validation:
            configuration.ssl_verify_cert = False
            # Create fingerprint validator
            cert_fingerprint_validator = SSLFingerprintValidator()
            # Create unverified context to capture fingerprint
            ssl_context = cert_fingerprint_validator.create_unverified_context(ssl_context)
        
        return ssl_context, cert_fingerprint_validator
