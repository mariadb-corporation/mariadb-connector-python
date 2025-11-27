# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
SSL Fingerprint Validator for MariaDB connections

Provides SSL certificate fingerprint validation for self-signed certificates.
This allows secure connections even with self-signed certificates by validating
the certificate fingerprint against a hash provided by the server.
"""

import ssl
import hashlib
from typing import Optional


class SSLFingerprintValidator:
    """
    SSL certificate fingerprint validator
    
    Captures the certificate fingerprint during SSL handshake when certificate
    validation fails, allowing later validation using server-provided hash.
    """
    
    def __init__(self):
        """Initialize fingerprint validator"""
        self.fingerprint: Optional[bytes] = None
        self.cert_der: Optional[bytes] = None
    
    def create_unverified_context(self, base_context: ssl.SSLContext) -> ssl.SSLContext:
        """
        Create an SSL context that doesn't verify certificates but captures fingerprint
        
        Args:
            base_context: Base SSL context with desired settings
            
        Returns:
            SSL context that captures certificate fingerprint
        """
        # Create a new context with same settings but no verification
        context = ssl.SSLContext(base_context.protocol)
        
        # Copy settings from base context
        context.minimum_version = base_context.minimum_version
        context.maximum_version = base_context.maximum_version
        
        # Disable certificate verification
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        # Copy cipher settings if available
        try:
            if hasattr(base_context, '_ciphers'):
                context.set_ciphers(base_context._ciphers)
        except:
            pass
        
        return context
    
    def capture_fingerprint(self, ssl_socket: ssl.SSLSocket) -> None:
        """
        Capture the certificate fingerprint from an SSL socket
        
        Args:
            ssl_socket: SSL socket after handshake
        """
        try:
            # Get the peer certificate in DER format
            cert_der = ssl_socket.getpeercert(binary_form=True)
            if cert_der:
                self.cert_der = cert_der
                # Calculate SHA-256 fingerprint
                self.fingerprint = hashlib.sha256(cert_der).digest()
        except Exception:
            # If we can't get the certificate, fingerprint remains None
            pass
    
    def get_fingerprint(self) -> Optional[bytes]:
        """
        Get the captured certificate fingerprint
        
        Returns:
            SHA-256 fingerprint of the certificate, or None if not captured
        """
        return self.fingerprint
    
    def validate_fingerprint(
        self,
        auth_plugin_hash: bytes,
        seed: bytes,
        server_validation_hash: bytes
    ) -> bool:
        """
        Validate the certificate fingerprint against server-provided hash
        
        This implements the validation formula:
        SHA256(hash(password) + seed + fingerprint) == server_validation_hash
        
        Args:
            auth_plugin_hash: Hash from authentication plugin's hash() method
            seed: Server seed/scramble from handshake
            server_validation_hash: Validation hash from server's OK packet info field
            
        Returns:
            True if fingerprint is valid, False otherwise
        """
        if not self.fingerprint or not server_validation_hash:
            return False
        
        # Server validation hash format: 0x01 (SHA256 marker) + hex_string
        if len(server_validation_hash) == 0 or server_validation_hash[0] != 0x01:
            return False
        
        # Rest is hex string of the expected hash
        server_hash_hex = server_validation_hash[1:].decode('ascii')
        
        # Calculate our hash: SHA256(auth_hash + seed + fingerprint)
        hasher = hashlib.sha256()
        hasher.update(auth_plugin_hash)
        hasher.update(seed)
        hasher.update(self.fingerprint)
        calculated_hash = hasher.digest()
        
        # Convert to hex for comparison
        calculated_hash_hex = calculated_hash.hex()
        
        # Compare (case-insensitive)
        return calculated_hash_hex.lower() == server_hash_hex.lower()
