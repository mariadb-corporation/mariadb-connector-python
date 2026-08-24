# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from __future__ import annotations

import contextlib
import hashlib

from ...configuration import Configuration
from ...host_address import HostAddress

from typing import Any, Callable, Awaitable
from ...client.context import Context
from ...fips import is_fips_mode

from ..authentication_plugin import AuthenticationPlugin
from ....exceptions import OperationalError

hashes: Any = None
serialization: Any = None
rsa: Any = None
padding: Any = None
with contextlib.suppress(Exception):
    from cryptography.hazmat.primitives import hashes, serialization  # pyright: ignore[reportMissingImports]
    from cryptography.hazmat.primitives.asymmetric import rsa, padding  # pyright: ignore[reportMissingImports]
HAS_CRYPTOGRAPHY = padding is not None


class CachingSha2PasswordPlugin(AuthenticationPlugin):
    """
    Caching SHA2 password authentication plugin implementation
    """
    
    TYPE = "caching_sha2_password"
    
    def __init__(self, authentication_data: str | None, seed: bytes, conf: Configuration, host_address: HostAddress):
        """Initialize plugin with authentication data and seed"""
        self.authentication_data: str | None = authentication_data
        self.seed: bytes = seed
        self.conf: Configuration = conf
        self.host_address: HostAddress = host_address
    
    @staticmethod
    def encrypt_password(password: str | None, seed: bytes) -> bytearray:
        """Send an SHA-2 encrypted password: XOR(SHA256(password), SHA256(seed, SHA256(SHA256(password))))"""
        if password is None or password == "":  # nosec B105
            return bytearray(b'')
        
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
        
        result = bytearray(32)
        for i in range(32):
            result[i] = stage1[i] ^ stage3[i]
        return result
    
    def _get_rsa_encrytped_pwd(self, public_key_pem: str) -> bytes:
        """Encrypt password using RSA public key """
        if is_fips_mode():
            # The server's public-key exchange is defined with RSA-OAEP over
            # SHA-1 (see the padding below), which a FIPS provider refuses.
            # Say so here: the alternative failure is an obscure error from
            # `cryptography` deep inside the exchange.
            raise OperationalError(
                "Authentication plugin 'caching_sha2_password' cannot exchange the "
                "server's RSA public key with a FIPS-enabled crypto backend: that "
                "exchange is defined with RSA-OAEP over SHA-1. Enable TLS (ssl=True) "
                "so the password is sent over the secure channel instead, or grant "
                "this account a FIPS-compliant authentication plugin such as 'parsec'."
            )
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
                
                # Encrypt with RSA OAEP padding. SHA1 is the OAEP/MGF1 digest
                # required by the server's caching_sha2_password public-key
                # exchange (MySQL/MariaDB use RSA_PKCS1_OAEP_PADDING, whose
                # default digest is SHA1); it is dictated by interoperability,
                # not chosen for its cryptographic strength.
                encrypted: bytes = public_key.encrypt(
                    password_bytes,
                    padding.OAEP(
                        mgf=padding.MGF1(algorithm=hashes.SHA1()),  # nosec B303
                        algorithm=hashes.SHA1(),  # nosec B303
                        label=None
                    )
                )
                return encrypted
            else:
                return bytes([0x00])
        except Exception as e:
            raise OperationalError(f"RSA authentication failed: {e}")
    
    async def processAsync(
        self, 
        read_payload_func: Callable[[], Awaitable[memoryview]], 
        write_payload_func: Callable[[bytearray, str, bool], Awaitable[None]], 
        context: Context
    ) -> memoryview:
        """Process caching SHA2 password plugin authentication (async)"""
        # Build and send initial payload
        truncated_seed = self.seed[:20] if len(self.seed) > 20 else self.seed
        encrypted = self.encrypt_password(self.authentication_data, truncated_seed)
        payload = bytearray(b'\0\0\0\0')
        payload.extend(encrypted)
        await write_payload_func(payload, "CACHING_SHA2_PASSWORD ENCRYPTED PWD", False)
        
        # Read response packet
        response = await read_payload_func()
        # Server requests more authentication data
        if len(response) > 1 and response[0] == 0x01:
            auth_method = response[1]
            if auth_method == 0x03:
                # Fast authentication successful, return ending ok packet
                return await read_payload_func()
            elif auth_method == 0x04:
                if self._is_connection_secure():
                    # Send password in clear text over the secure transport
                    if self.authentication_data:
                        payload = bytearray(b'\0\0\0\0')
                        payload.extend(self.authentication_data.encode('utf-8'))
                        payload.append(0)
                    else:
                        payload = bytearray(b'\0\0\0\0\0')  # Null terminator
                    await write_payload_func(payload, "CACHING_SHA2_PASSWORD CLEAR PWD", False)
                    return await read_payload_func()
                else:
                    if not HAS_CRYPTOGRAPHY:
                        raise OperationalError(
                            "caching_sha2_password requires SSL or cryptography library for RSA encryption"
                        )

                    # Request public key from server
                    await write_payload_func(bytearray(b'\0\0\0\0\2'), "CACHING_SHA2_REQUEST_KEY", False)

                    # Read public key response
                    key_response = await read_payload_func()
                    if len(key_response) > 0 and key_response[0] == 0xFF:
                        return key_response

                    # Parse public key
                    public_key_pem = bytes(key_response[1:])  # Skip first byte

                    # Encrypt password with RSA public key
                    encrypted_pwd = self._get_rsa_encrytped_pwd(public_key_pem.decode('utf-8'))
                    payload = bytearray(b'\0\0\0\0')
                    payload.extend(encrypted_pwd)
                    await write_payload_func(payload, "CACHING_SHA2_PASSWORD RSA ENCRYPTED PWD", False)

                    return await read_payload_func()
            else:
                raise OperationalError(f"Unknown authentication method: {auth_method}")
        
        return response
    


    def processSync(
        self, 
        read_payload_func: Callable[[], memoryview], 
        write_payload_func: Callable[[bytearray, str, bool], None], 
        context: Context
    ) -> memoryview:
        """Process caching SHA2 password plugin authentication (sync)"""
        # Build and send initial payload
        truncated_seed = self.seed[:20] if len(self.seed) > 20 else self.seed
        encrypted = self.encrypt_password(self.authentication_data, truncated_seed)
        payload = bytearray(b'\0\0\0\0')
        payload.extend(encrypted)
        write_payload_func(payload, "CACHING_SHA2_PASSWORD ENCRYPTED PWD", False)
        
        # Read response packet
        response = read_payload_func()
        # Server requests more authentication data
        if len(response) > 1 and response[0] == 0x01:
            auth_method = response[1]
            if auth_method == 0x03:
                # Fast authentication successful, return ending ok packet
                return read_payload_func()
            elif auth_method == 0x04:
                if self._is_connection_secure():
                    if self.authentication_data and self.authentication_data != "":
                        # Send password in clear text over the secure transport
                        payload = bytearray(b'\0\0\0\0')
                        payload.extend(self.authentication_data.encode('utf-8'))
                        payload.append(0)
                    else:
                        payload = bytearray(b'\0\0\0\0\0')  # Null terminator
                    write_payload_func(payload, "CACHING_SHA2_PASSWORD CLEAR PWD", False)
                    return read_payload_func()
                else:
                    if not HAS_CRYPTOGRAPHY:
                        raise OperationalError(
                            "Authentication plugin 'caching_sha2_password' requires SSL connection "
                            "or cryptography library for RSA encryption when not cached"
                        )

                    # Request RSA public key from server
                    write_payload_func(bytearray(b'\0\0\0\0\2'), "CACHING_SHA2_REQUEST_KEY", False)

                    # Read public key response
                    key_response = read_payload_func()
                    if len(key_response) > 0 and key_response[0] == 0xFF:
                        return key_response

                    # Parse public key (skip first byte which is packet type)
                    public_key_pem = bytes(key_response[1:]).decode('utf-8')

                    # Encrypt password using shared logic
                    encrypted_pwd = self._get_rsa_encrytped_pwd(public_key_pem)
                    payload = bytearray(b'\0\0\0\0')
                    payload.extend(encrypted_pwd)
                    write_payload_func(payload, "CACHING_SHA2_PASSWORD RSA ENCRYPTED PWD", False)

                    return read_payload_func()
            else:
                raise OperationalError(f"Unknown authentication method: {auth_method}")

        return response

    # --- transport-security helper --------------------------------------------

    def _is_connection_secure(self) -> bool:
        """a connection is secure when TLS is active, or when the transport is not 
        a plain TCP socket (e.g. a unix socket)."""
        if self.conf.ssl:
            return True
        return bool(self.conf.unix_socket) and getattr(self.conf, 'protocol', 0) != 1

    def is_mitm_proof(self) -> bool:
        return False
    
    def hash(self, conf: Configuration) -> bytes | None:
        """Return hash for credential"""
        return None
