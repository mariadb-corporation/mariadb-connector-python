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
import hmac


class SSLFingerprintValidator:
    """
    SSL certificate fingerprint validator
    
    Captures the certificate fingerprint during SSL handshake when certificate
    validation fails, allowing later validation using server-provided hash.
    """
    
    def __init__(self) -> None:
        """Initialize fingerprint validator"""
        self.fingerprint: bytes | None = None
        self.cert_der: bytes | None = None
    
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
    
    def get_fingerprint(self) -> bytes | None:
        """
        Get the captured certificate fingerprint
        
        Returns:
            SHA-256 fingerprint of the certificate, or None if not captured
        """
        return self.fingerprint

    def check_certificate_period(self) -> str | None:
        """Check the captured certificate's validity period (notBefore/notAfter).

        The fingerprint path runs over an unverified TLS context (CERT_NONE), so
        the TLS layer never checks the certificate dates. libmariadb checks
        MARIADB_TLS_VERIFY_PERIOD on *every* path -- including the self-signed /
        fingerprint one -- so an expired (or not-yet-valid) certificate is
        rejected even there. Mirror that so we are at least as strict.

        Returns a human-readable reason when the certificate is outside its
        validity window, or None when it is valid (or cannot be parsed / the
        cryptography library is unavailable, in which case we fall back to the
        fingerprint-hash check rather than failing closed on a parse quirk).
        """
        if not self.cert_der:
            return None
        try:
            from cryptography import x509
            cert = x509.load_der_x509_certificate(self.cert_der)
        except Exception:
            return None

        import datetime
        now = datetime.datetime.now(datetime.timezone.utc)
        # cryptography >= 42 exposes timezone-aware *_utc accessors; older
        # versions return naive UTC datetimes.
        not_before = getattr(cert, "not_valid_before_utc", None)
        not_after = getattr(cert, "not_valid_after_utc", None)
        if not_before is None or not_after is None:
            not_before = cert.not_valid_before.replace(tzinfo=datetime.timezone.utc)
            not_after = cert.not_valid_after.replace(tzinfo=datetime.timezone.utc)

        if now < not_before:
            return f"server certificate is not yet valid (not before {not_before.isoformat()})"
        if now > not_after:
            return f"server certificate has expired (not after {not_after.isoformat()})"
        return None

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

        # Compare in constant time
        return hmac.compare_digest(
            calculated_hash_hex.lower().encode('ascii'),
            server_hash_hex.lower().encode('ascii'),
        )
