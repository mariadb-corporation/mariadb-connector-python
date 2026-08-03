# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab


from __future__ import annotations

import contextlib
import math
import secrets

from ...configuration import Configuration

from typing import Any, Callable, Awaitable
from ...client.context import Context
from ...message.payload_reader import PayloadReader
from ..authentication_plugin import AuthenticationPlugin
from ....exceptions import OperationalError

hashes: Any = None
serialization: Any = None
PBKDF2HMAC: Any = None  # pyright: ignore[reportConstantRedefinition]
Ed25519PrivateKey: Any = None
with contextlib.suppress(Exception):
    from cryptography.hazmat.primitives import hashes, serialization  # pyright: ignore[reportMissingImports]
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC  # pyright: ignore[reportMissingImports, reportConstantRedefinition]
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # pyright: ignore[reportMissingImports]
HAS_CRYPTOGRAPHY = Ed25519PrivateKey is not None

PBKDF2_ROUNDS_PER_MS = 262144 / 225

SERVER_CONNECT_TIMEOUT_DEFAULT = 10.0


class ParsecPasswordPlugin(AuthenticationPlugin):
    """
    Parsec password authentication plugin implementation
    
    Uses PBKDF2 key derivation and Ed25519 signing for authentication.
    """
    
    # PKCS#8 Ed25519 header for private key encoding
    PKCS8_ED25519_HEADER = bytes([
        0x30, 0x2e, 0x02, 0x01, 0x00, 0x30, 0x05, 0x06, 0x03, 0x2b, 0x65, 0x70, 0x04, 0x22, 0x04, 0x20
    ])
    
    def __init__(self, authentication_data: str | None, seed: bytes, conf: Configuration):
        """Initialize plugin with authentication data and seed"""
        self.authentication_data = authentication_data
        self.seed = seed
        self.conf: Configuration = conf
        self._hash = None

    def _time_budget(self) -> float:
        """Connection time budget in seconds, falling back to the default"""
        connect_timeout = self.conf.connect_timeout
        if connect_timeout is not None and connect_timeout > 0:
            return float(connect_timeout)
        return SERVER_CONNECT_TIMEOUT_DEFAULT

    def _max_iteration_factor(self) -> int:
        """Highest iteration factor whose derivation fits the time budget."""
        affordable_rounds = PBKDF2_ROUNDS_PER_MS * self._time_budget() * 1000 / 1024
        if affordable_rounds <= 0:
            return 0
        return max(0, math.floor(math.log2(affordable_rounds)))

    def _validate_format(self, first_byte: int, iterations_exp: int) -> None:
        """Reject a non-PBKDF2 algorithm or an unaffordable iteration factor"""
        if first_byte != 0x50:  # 'P' for PBKDF2
            raise OperationalError(
                "Wrong parsec authentication format: expected 'P' for KDF algorithm")

        max_iterations_exp = self._max_iteration_factor()
        if iterations_exp > max_iterations_exp:
            raise OperationalError(
                f"Wrong parsec authentication format: server requires parsec iteration "
                f"factor {iterations_exp}, above the maximum factor "
                f"{max_iterations_exp} ({1024 << max_iterations_exp} PBKDF2 "
                f"rounds) that fits the {self._time_budget():g}s connection time budget. "
                f"Raise connect_timeout to permit a higher factor.")

    def _derive_key_and_sign(self, salt: bytes, iterations_exp: int) -> tuple[bytes, bytes, bytes]:
        """Derive key using PBKDF2 and create signature"""
        # Derive key using PBKDF2
        password = self.authentication_data or ""
        password_bytes = password.encode('utf-8')

        iterations = 1024 << iterations_exp  # 1024 * 2^iterations_exp

        # cryptography rather than hashlib.pbkdf2_hmac: same primitive and same
        # output, but it derives faster against its bundled OpenSSL. This needs
        # cryptography >= 50.0.0, the first release to drop the GIL during the
        # derivation -- older ones stall every other thread for its duration.
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
        self._hash = self._combine_arrays([  # type: ignore[assignment]
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
        await write_payload_func(bytearray(b'\0\0\0\0'), "PARSEC_REQUEST_SALT", False)

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
        self._validate_format(first_byte, iterations_exp)

        # Derive key and create signature
        client_scramble, signature, _ = self._derive_key_and_sign(salt, iterations_exp)

        # Send client scramble + signature to server
        payload = bytearray(b'\0\0\0\0')
        payload.extend(client_scramble)
        payload.extend(signature)
        await write_payload_func(payload, "PARSEC_AUTH", False)

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
        write_payload_func(bytearray(b'\0\0\0\0'), "PARSEC_REQUEST_SALT", False)
        
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
        self._validate_format(first_byte, iterations_exp)

        # Derive key and create signature
        client_scramble, signature, _ = self._derive_key_and_sign(salt, iterations_exp)
        
        # Send client scramble + signature to server
        payload = bytearray(b'\0\0\0\0')
        payload.extend(client_scramble)
        payload.extend(signature)
        write_payload_func(payload, "PARSEC_AUTH", False)
        
        # Read final response
        return read_payload_func()
    
    def is_mitm_proof(self) -> bool:
        """Parsec password plugin is MitM-proof"""
        return True
    
    def hash(self, conf: Configuration) -> bytes | None:
        """Return hash for credential"""
        return self._hash
    
    def _combine_arrays(self, arrays: list[bytes]) -> bytes:
        """Combine multiple byte arrays into one"""
        result = b''
        for arr in arrays:
            result += arr
        return result
