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
Native Password Authentication Plugin

Implementation of mysql_native_password authentication plugin.
Equivalent to the Java NativePasswordPlugin class.
"""

import hashlib
from typing import Optional, Any

from ...impl.client.context import Context
from ...impl.client.socket.packet_writer import PacketWriter
from ...impl.client.socket.packet_reader import PacketReader
from ..authentication_plugin import AuthenticationPlugin, Credential


class NativePasswordPlugin(AuthenticationPlugin):
    """
    Native password authentication plugin implementation
    
    Equivalent to the Java NativePasswordPlugin class.
    See https://mariadb.com/kb/en/library/authentication-plugin-mysql_native_password/
    """
        
    def __init__(self, authentication_data: Optional[str], seed: bytes):
        """
        Initialize plugin with authentication data and seed
        
        Args:
            authentication_data: Password string
            seed: Server provided seed
        """
        self.authentication_data = authentication_data
        self.seed = seed

    @staticmethod
    def encrypt_password(password: Optional[str], seed: bytes) -> bytes:
        """
        Encrypts a password using MySQL native password algorithm
        
        Protocol for authentication:
        1. Server sends a random array of bytes (the seed)
        2. Client makes a SHA1 digest of the password
        3. Client hashes the output of step 2
        4. Client digests the seed
        5. Client updates the digest with the output from step 3
        6. XOR of the output of step 5 and step 2 is sent to server
        7. Server does the same thing and verifies that the scrambled passwords match
        
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
        
        # Step 2: SHA1 digest of the password
        stage1 = hashlib.sha1(password_bytes).digest()
        
        # Step 3: Hash the output of step 2
        stage2 = hashlib.sha1(stage1).digest()
        
        # Step 4-5: Digest the seed and update with stage2
        digest = hashlib.sha1()
        digest.update(seed)
        digest.update(stage2)
        stage3 = digest.digest()
        
        # Step 6: XOR stage1 and stage3
        result = bytes(a ^ b for a, b in zip(stage1, stage3))
        return result
    
    def process(self, writer: PacketWriter, reader: PacketReader, context: Context) -> bytes:
        """
        Process native password plugin authentication
        
        Args:
            writer: Output stream writer
            reader: Input stream reader
            context: Connection context
            
        Returns:
            Response packet bytes
            
        Raises:
            IOError: If socket error occurs
        """
        if self.authentication_data is None:
            # Send empty packet for no password
            writer.start_payload(reset_sequence=False)
            writer.send_payload("NATIVE EMPTY PWD")
        else:
            # Truncate seed to 20 bytes (remove null terminator if present)
            truncated_seed = self.seed[:20] if len(self.seed) > 20 else self.seed
            
            # Encrypt password and send
            encrypted = self.encrypt_password(self.authentication_data, truncated_seed)
            writer.start_payload(reset_sequence=False)
            writer.write_bytes(encrypted)
            writer.send_payload("NATIVE SEND PWD")            
        
        # Read response packet
        return reader.read_packet()
    
    def is_mitm_proof(self) -> bool:
        """
        Native password plugin is MitM-proof
        
        Returns:
            True
        """
        return True
    
    def hash(self, credential: Credential) -> Optional[bytes]:
        """
        Return hash for credential (double SHA1)
        
        Args:
            credential: Credential to hash
            
        Returns:
            Hash bytes (SHA1(SHA1(password)))
        """
        password = credential.get_password()
        if password is None:
            return None
        
        password_bytes = password.encode('utf-8')
        
        # SHA1(password)
        stage1 = hashlib.sha1(password_bytes).digest()
        
        # SHA1(SHA1(password))
        stage2 = hashlib.sha1(stage1).digest()
        
        return stage2
