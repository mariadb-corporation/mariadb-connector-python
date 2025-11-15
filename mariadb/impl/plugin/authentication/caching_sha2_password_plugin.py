# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from __future__ import annotations

import hashlib
from typing import Optional

from ...configuration import Configuration
from ...host_address import HostAddress

from ...client.socket.stream import AsyncStream, SyncStream
from ...client.context import Context

from ...client.socket.payload_writer import PayloadWriter
from ..authentication_plugin import AuthenticationPlugin
from ....exceptions import OperationalError

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa, padding
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False


class CachingSha2PasswordPlugin(AuthenticationPlugin):
    """
    Caching SHA2 password authentication plugin implementation
    """
    
    TYPE = "caching_sha2_password"
    
    def __init__(self, authentication_data: Optional[str], seed: bytes, conf: Configuration, host_address: HostAddress):
        """Initialize plugin with authentication data and seed"""
        self.authentication_data: Optional[str] = authentication_data
        self.seed: bytes = seed
        self.conf: Configuration = conf
        self.host_address: HostAddress = host_address
    
    @staticmethod
    def encrypt_password(password: Optional[str], seed: bytes) -> bytes:
        """Send an SHA-2 encrypted password: XOR(SHA256(password), SHA256(seed, SHA256(SHA256(password))))"""
        if password is None:
            return b''
        
        # Convert password to bytes
        password_bytes = password.encode('utf-8')
        
        # SHA256(password)
        stage1 = hashlib.sha256(password_bytes).digest()
        
        # SHA256(SHA256(password))
        stage2 = hashlib.sha256(stage1).digest()
        
        # SHA256(seed, SHA256(SHA256(password)))
        digest = hashlib.sha256()
        digest.update(seed)
        digest.update(stage2)
        stage3 = digest.digest()
        
        # XOR stage1 and stage3
        result = bytes(a ^ b for a, b in zip(stage1, stage3))
        return result
    
    def _build_initial_payload(self) -> bytearray:
        """Build initial authentication payload"""
        writer = PayloadWriter()
        
        if self.authentication_data is None:
            # Empty payload for no password
            pass
        else:
            # Truncate seed to 20 bytes (remove null terminator if present)
            truncated_seed = self.seed[:20] if len(self.seed) > 20 else self.seed
            
            # Encrypt password and write to payload
            encrypted = self.encrypt_password(self.authentication_data, truncated_seed)
            writer.write_bytes(encrypted)
        
        return writer.get_payload()
    
    def _build_cleartext_password_payload(self) -> bytearray:
        """Build cleartext password payload for SSL connections"""
        writer = PayloadWriter()
        if self.authentication_data:
            password_bytes = self.authentication_data.encode('utf-8')
            writer.write_bytes(password_bytes)
            writer.write_byte(0)  # Null terminator
        else:
            writer.write_byte(0)  # Null terminator
        
        return writer.get_payload()
    
    
    def _encrypt_password_with_rsa(self, public_key_pem: str) -> bytearray:
        """Encrypt password using RSA public key """
        try:
            # Load the public key
            public_key = serialization.load_pem_public_key(public_key_pem.encode('utf-8'))
            
            if not isinstance(public_key, rsa.RSAPublicKey):
                raise OperationalError("Server provided non-RSA public key")
            
            # Encrypt password with RSA public key
            if self.authentication_data:
                password_bytes = self.authentication_data.encode('utf-8')
                password_bytes += b'\x00'  # Null terminator
                
                # XOR with seed for additional security
                if len(self.seed) > 0:
                    seed_cycle = (self.seed * ((len(password_bytes) // len(self.seed)) + 1))[:len(password_bytes)]
                    password_bytes = bytes(a ^ b for a, b in zip(password_bytes, seed_cycle))
                
                # Encrypt with RSA OAEP padding
                encrypted = public_key.encrypt(
                    password_bytes,
                    padding.OAEP(
                        mgf=padding.MGF1(algorithm=hashes.SHA1()),
                        algorithm=hashes.SHA1(),
                        label=None
                    )
                )
                writer = PayloadWriter()
                writer.write_bytes(encrypted)
                return writer.get_payload()
            else:
                writer = PayloadWriter()
                writer.write_byte(0)  # Empty password
                return writer.get_payload()
                
        except Exception as e:
            raise OperationalError(f"RSA authentication failed: {e}")
    
    async def processAsync(self, stream: AsyncStream, context: Context) -> bytearray:
        """Process caching SHA2 password plugin authentication (async)"""
        # Build and send initial payload
        payload = self._build_initial_payload()
        await stream.send_payload(payload, "CACHING_SHA2_PASSWORD", reset_sequence=False)
        
        # Read response packet
        response: bytes = await stream.read_payload()
        
        # Check if server requests more authentication data
        if len(response) > 0 and response[0] == 0x01:
            # Server requests more authentication data
            if len(response) > 1:
                auth_method = response[1]
                if auth_method == 0x03:
                    # Fast authentication successful
                    return response
                elif auth_method == 0x04:
                    # Perform full authentication
                    if self.conf.ssl:
                        # Send password in clear text over SSL
                        payload = self._build_cleartext_password_payload()
                        await stream.send_payload(payload, "CACHING_SHA2_CLEAR_PWD", reset_sequence=False)
                        return await stream.read_payload()
                    else:
                        # SSL not available - try RSA public key encryption
                        if not HAS_CRYPTOGRAPHY:
                            raise OperationalError(
                                "Authentication plugin 'caching_sha2_password' requires SSL connection "
                                "or cryptography library for RSA encryption when not cached"
                            )
                        
                        # Request RSA public key from server
                        await stream.send_payload(bytearray([0x02]), "CACHING_SHA2_REQUEST_KEY", reset_sequence=False)
                        
                        # Read public key response
                        key_response: bytes = await stream.read_payload()
                        
                        if len(key_response) == 0 or key_response[0] == 0xFF:
                            raise OperationalError("Failed to get RSA public key from server")
                        
                        # Parse public key (skip first byte which is packet type)
                        public_key_pem = key_response[1:].decode('utf-8')
                        
                        # Encrypt password using shared logic
                        encrypted_payload = self._encrypt_password_with_rsa(public_key_pem)
                        
                        # Send encrypted password
                        await stream.send_payload(encrypted_payload, "CACHING_SHA2_RSA_PWD", reset_sequence=False)
                        
                        return await stream.read_payload()
                else:
                    raise OperationalError(f"Unknown authentication method: {auth_method}")
        
        return response
    
    def processSync(self, stream: SyncStream, context: Context) -> bytearray:
        """Process caching SHA2 password plugin authentication (sync)"""
        # Build and send initial payload
        payload = self._build_initial_payload()
        stream.send_payload(payload, "CACHING_SHA2_PASSWORD", reset_sequence=False)
        
        # Read response packet
        response: bytes = stream.read_payload()
        
        # Check if server requests more authentication data
        if len(response) > 0 and response[0] == 0x01:
            # Server requests more authentication data
            if len(response) > 1:
                auth_method = response[1]
                if auth_method == 0x03:
                    # Fast authentication successful
                    return response
                elif auth_method == 0x04:
                    # Perform full authentication
                    if self.conf.ssl:
                        # Send password in clear text over SSL
                        payload = self._build_cleartext_password_payload()
                        stream.send_payload(payload, "CACHING_SHA2_CLEAR_PWD", reset_sequence=False)
                        return stream.read_payload()
                    else:
                        # SSL not available - try RSA public key encryption
                        if not HAS_CRYPTOGRAPHY:
                            raise OperationalError(
                                "Authentication plugin 'caching_sha2_password' requires SSL connection "
                                "or cryptography library for RSA encryption when not cached"
                            )
                        
                        # Request RSA public key from server
                        stream.send_payload(bytearray([0x02]), "CACHING_SHA2_REQUEST_KEY", reset_sequence=False)
                        
                        # Read public key response
                        key_response: bytes = stream.read_payload()
                        
                        if len(key_response) == 0 or key_response[0] == 0xFF:
                            raise OperationalError("Failed to get RSA public key from server")
                        
                        # Parse public key (skip first byte which is packet type)
                        public_key_pem = key_response[1:].decode('utf-8')
                        
                        # Encrypt password using shared logic
                        encrypted_payload = self._encrypt_password_with_rsa(public_key_pem)
                        
                        # Send encrypted password
                        stream.send_payload(encrypted_payload, "CACHING_SHA2_RSA_PWD", reset_sequence=False)
                        
                        return stream.read_payload()
                else:
                    raise OperationalError(f"Unknown authentication method: {auth_method}")
        
        return response
    
    def is_mitm_proof(self) -> bool:
        """Caching SHA2 password plugin is MitM-proof"""
        return True
    
    def hash(self, conf: Configuration) -> Optional[bytes]:
        """Return hash for credential"""
        password = conf.password
        if password is None:
            return None
        
        password_bytes = password.encode('utf-8')
        
        # SHA256(password)
        stage1 = hashlib.sha256(password_bytes).digest()
        
        # SHA256(SHA256(password))
        stage2 = hashlib.sha256(stage1).digest()
        
        return stage2
