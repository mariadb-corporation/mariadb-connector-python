# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from __future__ import annotations

import hashlib
from typing import Optional

from ...configuration import Configuration
from ...host_address import HostAddress

from ...client.socket.read_stream import AsyncReadStream, SyncReadStream, PacketBuffer
from ...client.socket.write_stream import AsyncWriteStream, SyncWriteStream
from ...client.context import Context

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
        if password is None or password == "":
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
    
    def _get_rsa_encrytped_pwd(self, public_key_pem: str) -> bytes:
        """Encrypt password using RSA public key """
        try:
            # Load the public key
            public_key = serialization.load_pem_public_key(public_key_pem.encode('utf-8'))
            
            if not isinstance(public_key, rsa.RSAPublicKey):
                raise OperationalError("Server provided non-RSA public key")
            
            # Encrypt password with RSA public key
            if self.authentication_data and self.authentication_data != "":
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
                return encrypted
            else:
                return [0x00]
        except Exception as e:
            raise OperationalError(f"RSA authentication failed: {e}")
    
    async def processAsync(self, read_stream: AsyncReadStream, write_stream: AsyncWriteStream, context: Context) -> PacketBuffer:
        """Process caching SHA2 password plugin authentication (async)"""
        # Build and send initial payload
        write_stream.begin_write(False)
        truncated_seed = self.seed[:20] if len(self.seed) > 20 else self.seed
        encrypted = self.encrypt_password(self.authentication_data, truncated_seed)
        write_stream.write_bytes(encrypted)        
        await write_stream.flush("CACHING_SHA2_PASSWORD ENCRYPTED PWD")
        
        # Read response packet
        response = await read_stream.read_payload()
        # Server requests more authentication data
        if len(response) > 1 and response[0] == 0x01:
            auth_method = response[1]
            response.release()
            if auth_method == 0x03:
                # Fast authentication successful, return ending ok packet
                return await read_stream.read_payload()
            elif auth_method == 0x04:
                # Perform full authentication
                if self.conf.ssl:
                    # Send password in clear text over SSL
                    write_stream.begin_write(False)
                    if self.authentication_data and self.authentication_data != "":
                        write_stream.write_string(self.authentication_data)
                        write_stream.write_byte(0x00)  # Null terminator
                    else:
                        write_stream.write_byte(0x00)  # Null terminator
                    await write_stream.flush("CACHING_SHA2_PASSWORD CLEAR PWD")
                    return await read_stream.read_payload()
                else:
                    # SSL not available - try RSA public key encryption
                    if not HAS_CRYPTOGRAPHY:
                        raise OperationalError(
                            "Authentication plugin 'caching_sha2_password' requires SSL connection "
                            "or cryptography library for RSA encryption when not cached"
                        )
                    
                    # Request RSA public key from server
                    write_stream.begin_write(False)
                    write_stream.write_byte(0x02)
                    await write_stream.flush("CACHING_SHA2_REQUEST_KEY")
                    
                    # Read public key response
                    key_response = await read_stream.read_payload()
                    if len(key_response) > 0 and key_response[0] == 0xFF:
                        return key_response
                    
                    # Parse public key (skip first byte which is packet type)
                    public_key_pem = bytes(key_response[1:]).decode('utf-8')
                    key_response.release()
                    
                    # Encrypt password using shared logic
                    write_stream.begin_write(False)
                    write_stream.write_bytes(self._get_rsa_encrytped_pwd(public_key_pem))
                    await write_stream.flush("CACHING_SHA2_PASSWORD RSA ENCRYPTED PWD")

                    return await read_stream.read_payload()
            else:
                response.release()
                raise OperationalError(f"Unknown authentication method: {auth_method}")
        
        return response
    


    def processSync(self, read_stream: SyncReadStream, write_stream: SyncWriteStream, context: Context) -> PacketBuffer:
        """Process caching SHA2 password plugin authentication (sync)"""
        # Build and send initial payload
        write_stream.begin_write(False)
        truncated_seed = self.seed[:20] if len(self.seed) > 20 else self.seed
        encrypted = self.encrypt_password(self.authentication_data, truncated_seed)
        write_stream.write_bytes(encrypted)        
        write_stream.flush("CACHING_SHA2_PASSWORD ENCRYPTED PWD")
        
        # Read response packet
        response = read_stream.read_payload()
        # Server requests more authentication data
        if len(response) > 1 and response[0] == 0x01:
            auth_method = response[1]
            response.release()
            if auth_method == 0x03:
                # Fast authentication successful, return ending ok packet
                return read_stream.read_payload()
            elif auth_method == 0x04:
                # Perform full authentication
                if self.conf.ssl:
                    # Send password in clear text over SSL
                    write_stream.begin_write(False)
                    if self.authentication_data and self.authentication_data != "":
                        write_stream.write_string(self.authentication_data)
                        write_stream.write_byte(0x00)  # Null terminator
                    else:
                        write_stream.write_byte(0x00)  # Null terminator
                    write_stream.flush("CACHING_SHA2_PASSWORD CLEAR PWD")
                    return read_stream.read_payload()
                else:
                    # SSL not available - try RSA public key encryption
                    if not HAS_CRYPTOGRAPHY:
                        raise OperationalError(
                            "Authentication plugin 'caching_sha2_password' requires SSL connection "
                            "or cryptography library for RSA encryption when not cached"
                        )
                    
                    # Request RSA public key from server
                    write_stream.begin_write(False)
                    write_stream.write_byte(0x02)
                    write_stream.flush("CACHING_SHA2_REQUEST_KEY")
                    
                    # Read public key response
                    key_response = read_stream.read_payload()
                    if len(key_response) > 0 and key_response[0] == 0xFF:
                        return key_response
                    
                    # Parse public key (skip first byte which is packet type)
                    public_key_pem = bytes(key_response[1:]).decode('utf-8')
                    key_response.release()
                    
                    # Encrypt password using shared logic
                    write_stream.begin_write(False)
                    write_stream.write_bytes(self._get_rsa_encrytped_pwd(public_key_pem))
                    write_stream.flush("CACHING_SHA2_PASSWORD RSA ENCRYPTED PWD")

                    return read_stream.read_payload()
            else:
                response.release()
                raise OperationalError(f"Unknown authentication method: {auth_method}")
        
        return response
    
    def is_mitm_proof(self) -> bool:
        return False
    
    def hash(self, conf: Configuration) -> Optional[bytes]:
        """Return hash for credential"""
        return None
