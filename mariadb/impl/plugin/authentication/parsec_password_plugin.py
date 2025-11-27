# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab


from __future__ import annotations

import hashlib
import secrets
from typing import Optional, TYPE_CHECKING

from ...configuration import Configuration

from typing import Callable, Awaitable
from ...client.context import Context
from ...message.payload_reader import PayloadReader
from ..authentication_plugin import AuthenticationPlugin
from ....exceptions import OperationalError

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False


class ParsecPasswordPlugin(AuthenticationPlugin):
    """
    Parsec password authentication plugin implementation
    
    Uses PBKDF2 key derivation and Ed25519 signing for authentication.
    """
    
    # PKCS#8 Ed25519 header for private key encoding
    PKCS8_ED25519_HEADER = bytes([
        0x30, 0x2e, 0x02, 0x01, 0x00, 0x30, 0x05, 0x06, 0x03, 0x2b, 0x65, 0x70, 0x04, 0x22, 0x04, 0x20
    ])
    
    def __init__(self, authentication_data: Optional[str], seed: bytes):
        """Initialize plugin with authentication data and seed"""
        self.authentication_data = authentication_data
        self.seed = seed
        self._hash = None
    
    def _derive_key_and_sign(self, salt: bytes, iterations_exp: int) -> tuple[bytes, bytes, bytes]:
        """Derive key using PBKDF2 and create signature"""
        # Derive key using PBKDF2
        password = self.authentication_data or ""
        password_bytes = password.encode('utf-8')
        
        iterations = 1024 << iterations_exp  # 1024 * 2^iterations_exp
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA512(),
            length=32,  # 256 bits
            salt=salt,
            iterations=iterations,
        )
        derived_key = kdf.derive(password_bytes)
        
        # Create Ed25519 private key from derived key
        private_key = Ed25519PrivateKey.from_private_bytes(derived_key)
        public_key = private_key.public_key()
        
        # Get raw public key bytes
        raw_public_key = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        
        # Create hash for credential storage
        self._hash = self._combine_arrays([
            bytes([0x50, iterations_exp]),  # 'P' + iterations
            salt,
            raw_public_key
        ])
        
        # Generate client nonce (scramble)
        client_scramble = secrets.token_bytes(32)
        
        # Sign concatenation of server nonce + client nonce
        message_to_sign = self.seed + client_scramble
        signature = private_key.sign(message_to_sign)
        
        return client_scramble, signature, raw_public_key
    
    async def processAsync(
        self, 
        read_payload_func: Callable[[], Awaitable[memoryview]], 
        write_payload_func: Callable[[bytearray, str, bool], Awaitable[None]], 
        context: Context
    ) -> memoryview:
        """Process Parsec password plugin authentication (async)"""
        if not HAS_CRYPTOGRAPHY:
            raise OperationalError(
                "Parsec authentication requires cryptography library. "
                "Install with: pip install cryptography"
            )
        
        # Step 1: Request extended salt from server (empty payload)
        await write_payload_func(bytearray(b'\0\0\0\0'), "PARSEC_REQUEST_SALT", reset_sequence=False)

        # Step 2: Read server response with salt and parameters
        response = await read_payload_func()
        
        if len(response) < 3:
            raise OperationalError("Invalid parsec authentication response")
        
        # Parse response
        parser = PayloadReader(response)
        
        if parser.get_byte() == 0x01:
            # skip authentication data header
            parser.read_byte()

        first_byte = parser.read_byte()
        iterations_exp = parser.read_byte()
        salt = parser.read_remaining()
        
        # Validate format
        if first_byte != 0x50 or iterations_exp > 3:  # 'P' for PBKDF2, Maximum iteration of 8192 (2^13 = 1024 << 3)
            raise OperationalError("Wrong parsec authentication format: expected 'P' for KDF algorithm or iteration count too high")

        # Derive key and create signature
        client_scramble, signature, _ = self._derive_key_and_sign(salt, iterations_exp)
        
        # Send client scramble + signature to server
        payload = bytearray(b'\0\0\0\0')
        payload.extend(client_scramble)
        payload.extend(signature)
        await write_payload_func(payload, "PARSEC_AUTH", reset_sequence=False)

        # Read final response
        return await read_payload_func()
    
    def processSync(
        self, 
        read_payload_func: Callable[[], memoryview], 
        write_payload_func: Callable[[bytearray, str, bool], None], 
        context: Context
    ) -> memoryview:
        """Process Parsec password plugin authentication (sync)"""
        if not HAS_CRYPTOGRAPHY:
            raise OperationalError(
                "Parsec authentication requires cryptography library. "
                "Install with: pip install cryptography"
            )
        
        # Step 1: Request extended salt from server (empty payload)
        write_payload_func(bytearray(b'\0\0\0\0'), "PARSEC_REQUEST_SALT", reset_sequence=False)
        
        # Step 2: Read server response with salt and parameters
        response = read_payload_func()
        
        if len(response) < 3:
            raise OperationalError("Invalid parsec authentication response")
        
        # Parse response
        parser = PayloadReader(response)
        if (parser.get_byte() == 0x01):
            parser.read_byte()
            
        first_byte = parser.read_byte()
        iterations_exp = parser.read_byte()
        salt = parser.read_remaining()
        
        # Validate format
        if first_byte != 0x50 or iterations_exp > 3:  # 'P' for PBKDF2, Maximum iteration of 8192 (2^13 = 1024 << 3)
            raise OperationalError("Wrong parsec authentication format: expected 'P' for KDF algorithm or iteration count too high")
        
        # Derive key and create signature
        client_scramble, signature, _ = self._derive_key_and_sign(salt, iterations_exp)
        
        # Send client scramble + signature to server
        payload = bytearray(b'\0\0\0\0')
        payload.extend(client_scramble)
        payload.extend(signature)
        write_payload_func(payload, "PARSEC_AUTH", reset_sequence=False)
        
        # Read final response
        return read_payload_func()
    
    def is_mitm_proof(self) -> bool:
        """Parsec password plugin is MitM-proof"""
        return True
    
    def hash(self, conf: Configuration) -> Optional[bytes]:
        """Return hash for credential"""
        return self._hash
    
    def _combine_arrays(self, arrays: list) -> bytes:
        """Combine multiple byte arrays into one"""
        result = b''
        for arr in arrays:
            result += arr
        return result
