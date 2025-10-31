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
Parsec Password Authentication Plugin

Implementation of parsec authentication plugin.
Equivalent to the Java ParsecPasswordPlugin class.
See https://mariadb.com/kb/en/connection/#parsec-plugin
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ...impl.client.context import Context
    from ...impl.client.socket.payload_writer import PayloadWriter
    from ...impl.client.socket.stream.stream import Stream

from ..authentication_plugin import AuthenticationPlugin, Credential
from ...exceptions import OperationalError

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
    
    Equivalent to the Java ParsecPasswordPlugin class.
    Uses PBKDF2 key derivation and Ed25519 signing for authentication.
    """
    
    # PKCS#8 Ed25519 header for private key encoding
    PKCS8_ED25519_HEADER = bytes([
        0x30, 0x2e, 0x02, 0x01, 0x00, 0x30, 0x05, 0x06, 0x03, 0x2b, 0x65, 0x70, 0x04, 0x22, 0x04, 0x20
    ])
    
    def __init__(self, authentication_data: Optional[str], seed: bytes):
        """
        Initialize plugin with authentication data and seed
        
        Args:
            authentication_data: Password string
            seed: Server provided seed
        """
        self.authentication_data = authentication_data
        self.seed = seed
        self._hash = None
    
    def process(self, writer: PayloadWriter, stream: Stream, context: Context) -> bytes:
        """
        Process Parsec password plugin authentication
        
        Args:
            writer: Output stream writer
            reader: Input stream reader
            context: Connection context
            
        Returns:
            Response packet bytes
            
        Raises:
            OperationalError: If authentication fails or cryptography is not available
        """
        if not HAS_CRYPTOGRAPHY:
            raise OperationalError(
                "Parsec authentication requires cryptography library. "
                "Install with: pip install cryptography"
            )
        
        try:
            # Step 1: Request extended salt from server
            writer.start_payload(reset_sequence=False)
            writer.send_payload("PARSEC REQUEST EXT-ALT")                
            # Step 2: Read server response with salt and parameters
            response = reader.read_packet()
            
            if len(response) < 3:
                raise OperationalError("Invalid parsec authentication response")
            
            # Parse response
            first_byte = response[0]
            iterations_exp = response[1]
            salt = response[2:]
            
            # Validate format
            if first_byte != 0x50:  # 'P' for PBKDF2
                raise OperationalError("Wrong parsec authentication format: expected 'P' for KDF algorithm")
            
            if iterations_exp > 3:  # Maximum iteration of 8192 (2^13 = 1024 << 3)
                raise OperationalError("Wrong parsec authentication format: iteration count too high")
            
            # Step 3: Derive key using PBKDF2
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
            
            # Step 4: Create Ed25519 private key from derived key
            private_key = Ed25519PrivateKey.from_private_bytes(derived_key)
            public_key = private_key.public_key()
            
            # Get raw public key bytes
            raw_public_key = public_key.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw
            )
            
            # Step 5: Create hash for credential storage
            self._hash = self._combine_arrays([
                bytes([0x50, iterations_exp]),  # 'P' + iterations
                salt,
                raw_public_key
            ])
            
            # Step 6: Generate client nonce (scramble)
            client_scramble = secrets.token_bytes(32)
            
            # Step 7: Sign concatenation of server nonce + client nonce
            message_to_sign = self.seed + client_scramble
            signature = private_key.sign(message_to_sign)
            
            # Step 8: Send client scramble + signature to server
            writer.start_payload(reset_sequence=False)
            writer.write_bytes(client_scramble)
            writer.write_bytes(signature)
            writer.send_payload("PARSEC REQUEST")                
            
            # Step 9: Read final response
            return reader.read_packet()
            
        except Exception as e:
            if isinstance(e, OperationalError):
                raise
            raise OperationalError(f"Error during parsec authentication: {e}")
    
    def is_mitm_proof(self) -> bool:
        """
        Parsec password plugin is MitM-proof
        
        Returns:
            True
        """
        return True
    
    def hash(self, credential: Credential) -> Optional[bytes]:
        """
        Return hash for credential
        
        Args:
            credential: Credential to hash
            
        Returns:
            Hash bytes containing salt, iterations, and public key
        """
        return self._hash
    
    def _combine_arrays(self, arrays: list) -> bytes:
        """
        Combine multiple byte arrays into one
        
        Args:
            arrays: List of byte arrays to combine
            
        Returns:
            Combined byte array
        """
        result = b''
        for arr in arrays:
            result += arr
        return result
