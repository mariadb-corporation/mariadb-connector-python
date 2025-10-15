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
Caching SHA2 Password Authentication Plugin

Implementation of caching_sha2_password authentication plugin.
Equivalent to the Java CachingSha2PasswordPlugin class.
"""

import hashlib
import os
from typing import Optional, Any

from ...impl.client.context import Context
from ...impl.client.socket.packet_writer import PacketWriter
from ...impl.client.socket.packet_reader import PacketReader
from ..authentication_plugin import AuthenticationPlugin, Credential
from ...exceptions import OperationalError

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa, padding
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False


class CachingSha2PasswordPlugin(AuthenticationPlugin):
    """
    Caching SHA2 password authentication plugin implementation
    
    Equivalent to the Java CachingSha2PasswordPlugin class.
    """
    
    TYPE = "caching_sha2_password"
    
    def __init__(self, authentication_data: Optional[str], seed: bytes, conf: Any, host_address: Any):
        """
        Initialize plugin with authentication data and seed
        
        Args:
            authentication_data: Password string
            seed: Server provided seed
            conf: Connection configuration
            host_address: Host address
        """
        self.authentication_data = authentication_data
        self.seed = seed
        self.conf = conf
        self.host_address = host_address
    
    @staticmethod
    def encrypt_password(password: Optional[str], seed: bytes) -> bytes:
        """
        Send an SHA-2 encrypted password
        
        Encryption: XOR(SHA256(password), SHA256(seed, SHA256(SHA256(password))))
        
        Args:
            password: The password to encrypt
            seed: The seed to use
            
        Returns:
            Scrambled password bytes
        """
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
    
    def process(self, writer: PacketWriter, reader: PacketReader, context: Context) -> bytes:
        """
        Process caching SHA2 password plugin authentication
        
        Args:
            writer: Output stream writer
            reader: Input stream reader
            context: Connection context
            
        Returns:
            Response packet bytes
            
        Raises:
            IOError: If socket error occurs
            OperationalError: If authentication fails
        """
        if self.authentication_data is None:
            # Send empty packet for no password
            writer.start_payload(reset_sequence=False)
            writer.send_payload("CACHING_SHA2_PWD EMPTY PACKET")

        else:
            # Truncate seed to 20 bytes (remove null terminator if present)
            truncated_seed = self.seed[:20] if len(self.seed) > 20 else self.seed
            
            # Encrypt password and send
            encrypted = self.encrypt_password(self.authentication_data, truncated_seed)
            writer.start_payload(reset_sequence=False)
            writer.write_bytes(encrypted)
            writer.send_payload("CACHING_SHA2_PWD SEND PASSWORD")
        
        # Read response packet
        response = reader.read_packet()
        
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
                    return self._perform_full_authentication(writer, reader, context)
                else:
                    raise OperationalError(f"Unknown authentication method: {auth_method}")
        
        return response
    
    def _perform_full_authentication(self, writer: PacketWriter, reader: PacketReader, context: Context) -> bytes:
        """
        Perform full authentication when fast authentication fails
        
        Args:
            writer: Output stream writer
            reader: Input stream reader
            context: Connection context
            
        Returns:
            Response packet bytes
            
        Raises:
            OperationalError: If authentication fails
        """
        # Check if SSL is available
        if getattr(self.conf, 'ssl', False):
            # Send password in clear text over SSL
            if self.authentication_data:
                password_bytes = self.authentication_data.encode('utf-8')

                writer.start_payload(reset_sequence=False)
                writer.write_bytes(password_bytes)
                writer.write_byte(0)  # Null terminator
                writer.send_payload("CACHING_SHA2_PWD SEND CLEAR PASSWORD")
            else:
                writer.start_payload(reset_sequence=False)
                writer.write_byte(0)  # Null terminator
                writer.send_payload("CACHING_SHA2_PWD SEND NULL PASSWORD")
            
        else:
            # SSL not available - try RSA public key encryption
            if HAS_CRYPTOGRAPHY:
                return self._perform_rsa_authentication(writer, reader, context)
            else:
                raise OperationalError(
                    "Authentication plugin 'caching_sha2_password' requires SSL connection "
                    "or cryptography library for RSA encryption when not cached"
                )
        
        return reader.read_packet()
    
    def _perform_rsa_authentication(self, writer: PacketWriter, reader: PacketReader, context: Context) -> bytes:
        """
        Perform RSA public key authentication
        
        Args:
            writer: Output stream writer
            reader: Input stream reader
            context: Connection context
            
        Returns:
            Response packet bytes
            
        Raises:
            OperationalError: If RSA authentication fails
        """
        # Request RSA public key from server
        writer.start_payload(reset_sequence=False)
        writer.write_byte(0x02)  # Request public key
        writer.send_payload("CACHING_SHA2_PWD REQUEST PUBLIC KEY")
        
        # Read public key response
        key_response = reader.read_packet()
        
        if len(key_response) == 0 or key_response[0] == 0xFF:
            raise OperationalError("Failed to get RSA public key from server")
        
        try:
            # Parse public key (skip first byte which is packet type)
            public_key_pem = key_response[1:].decode('utf-8')
            
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
                writer.start_payload(reset_sequence=False)
                writer.write_bytes(encrypted)
                writer.send_payload("CACHING_SHA2_PWD RSA ENCRYTED PWD")
            else:
                writer.start_payload(reset_sequence=False)
                writer.write_byte(0)  # Empty password
                writer.send_payload("CACHING_SHA2_PWD RSA ENCRYTED PWD")
            
            return reader.read_packet()
            
        except Exception as e:
            raise OperationalError(f"RSA authentication failed: {e}")
    
    def is_mitm_proof(self) -> bool:
        """
        Caching SHA2 password plugin is MitM-proof
        
        Returns:
            True
        """
        return True
    
    def hash(self, credential: Credential) -> Optional[bytes]:
        """
        Return hash for credential (double SHA256)
        
        Args:
            credential: Credential to hash
            
        Returns:
            Hash bytes (SHA256(SHA256(password)))
        """
        password = credential.get_password()
        if password is None:
            return None
        
        password_bytes = password.encode('utf-8')
        
        # SHA256(password)
        stage1 = hashlib.sha256(password_bytes).digest()
        
        # SHA256(SHA256(password))
        stage2 = hashlib.sha256(stage1).digest()
        
        return stage2
