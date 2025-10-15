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
SSL Socket wrapper for MariaDB connections

Provides SSL/TLS encryption for database connections.
"""

import ssl
import socket
from typing import Optional
from ...configuration import Configuration
from ....exceptions import OperationalError


class SSLSocketWrapper:
    """
    SSL socket wrapper for MariaDB connections
    
    Wraps a regular socket with SSL/TLS encryption.
    """
    
    def __init__(self, raw_socket: socket.socket, configuration: Configuration):
        """
        Initialize SSL socket wrapper
        
        Args:
            raw_socket: The underlying socket to wrap
            configuration: Connection configuration with SSL settings
        """
        self.raw_socket = raw_socket
        self.configuration = configuration
        self.ssl_socket: Optional[ssl.SSLSocket] = None
        self._create_ssl_context()
    
    def _create_ssl_context(self) -> ssl.SSLContext:
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
            
            # Configure SSL context based on configuration
            if self.configuration.ssl_ca:
                context.load_verify_locations(cafile=self.configuration.ssl_ca)
            
            if self.configuration.ssl_capath:
                context.load_verify_locations(capath=self.configuration.ssl_capath)
            
            if self.configuration.ssl_cert and self.configuration.ssl_key:
                context.load_cert_chain(
                    certfile=self.configuration.ssl_cert,
                    keyfile=self.configuration.ssl_key
                )
            
            if self.configuration.ssl_crl:
                # Load CRL if specified
                context.load_verify_locations(crlfile=self.configuration.ssl_crl)
                context.verify_flags |= ssl.VERIFY_CRL_CHECK_LEAF
            
            if self.configuration.ssl_cipher:
                context.set_ciphers(self.configuration.ssl_cipher)
            
            # Configure TLS version if specified
            if self.configuration.tls_version:
                self._configure_tls_versions(context)
            
            # Configure certificate verification
            if not self.configuration.ssl_verify_cert:
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            else:
                context.check_hostname = True
                context.verify_mode = ssl.CERT_REQUIRED
            
            self.ssl_context = context
            return context
            
        except Exception as e:
            raise OperationalError(f"Failed to create SSL context: {e}")
    
    def _configure_tls_versions(self, context: ssl.SSLContext) -> None:
        """
        Configure TLS versions from comma-separated string
        
        Args:
            context: SSL context to configure
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
        tls_versions_str = self.configuration.tls_version.strip()
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
                warnings.warn(f"Unsupported TLS version '{self.configuration.tls_version}', using default")
    
    def wrap_socket(self, server_hostname: Optional[str] = None) -> ssl.SSLSocket:
        """
        Wrap the raw socket with SSL
        
        Args:
            server_hostname: Server hostname for SNI
            
        Returns:
            SSL wrapped socket
            
        Raises:
            OperationalError: If SSL wrapping fails
        """
        try:
            # Wrap the socket with SSL
            self.ssl_socket = self.ssl_context.wrap_socket(
                self.raw_socket,
                server_side=False,
                do_handshake_on_connect=False,
                server_hostname=server_hostname
            )
            
            # Perform SSL handshake
            self.ssl_socket.do_handshake()
            
            return self.ssl_socket
            
        except Exception as e:
            raise OperationalError(f"SSL handshake failed: {e}")
    
    def get_ssl_socket(self) -> Optional[ssl.SSLSocket]:
        """
        Get the SSL socket if available
        
        Returns:
            SSL socket or None if not wrapped
        """
        return self.ssl_socket
    
    def get_peer_certificate(self) -> Optional[dict]:
        """
        Get peer certificate information
        
        Returns:
            Certificate information or None
        """
        if self.ssl_socket:
            try:
                return self.ssl_socket.getpeercert()
            except:
                return None
        return None
    
    def get_cipher(self) -> Optional[tuple]:
        """
        Get current cipher information
        
        Returns:
            Cipher information or None
        """
        if self.ssl_socket:
            try:
                return self.ssl_socket.cipher()
            except:
                return None
        return None
    
    def get_tls_version(self) -> Optional[str]:
        """
        Get current TLS version
        
        Returns:
            TLS version string or None if not available
        """
        if self.ssl_socket:
            try:
                return self.ssl_socket.version()
            except:
                return None
        return None
    
    def close(self):
        """Close the SSL socket"""
        if self.ssl_socket:
            try:
                self.ssl_socket.close()
            except:
                pass
            self.ssl_socket = None
