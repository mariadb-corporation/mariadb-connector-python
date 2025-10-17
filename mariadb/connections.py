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

import socket
from typing import Optional, Any, Dict, Union, Type
from .cursors import Cursor
from . import constants
from .exceptions import ProgrammingError, NotSupportedError, OperationalError
from packaging import version
from .impl.client.client import Client
from .impl.configuration import Configuration
from .impl.host_address import HostAddress
from .impl.string_utils import StringEscaper

_DEFAULT_CHARSET = "utf8mb4"
_DEFAULT_COLLATION = "utf8mb4_general_ci"
_MAX_TPC_XID_SIZE = 64

class Connection:
    """
    MariaDB Connector/Python Connection Object

    Handles the connection to a MariaDB or MySQL database server.
    It encapsulates a database session.

    This is a pure Python stub implementation. The actual database operations
    will be implemented later.
    
    Connections are created using the method mariadb.connect()
    """

    def _check_closed(self) -> None:
        if self._closed:
            raise ProgrammingError("Invalid connection or not connected")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        Establishes a connection to a database server and returns a connection
        object.
        
        Creates a socket connection to the MariaDB server using the implementation
        classes.
        """
        self._closed = False
        self.host = kwargs.get('host', 'localhost')
        self.port = kwargs.get('port', 3306)
        self.user = kwargs.get('user') or kwargs.get('username')
        self._database = kwargs.get('database') or kwargs.get('db')
        
        # Store all connection parameters
        self._connection_params = kwargs
        
        # Create configuration and host address
        self._configuration = Configuration.from_dict(kwargs)
        self._host_address = HostAddress(host=self.host, port=self.port)
        
        # Create the Java-equivalent client implementation
        self._client = Client(self._configuration, self._host_address)
        
        # Initialize socket connection
        try:
            # Connect using the Java-equivalent client implementation
            self._client.connect()
            
            # Connection info is available directly from client context
                
        except Exception as e:
            self._closed = True
            raise OperationalError(f"Connection failed: {e}")
        self.autocommit = self._configuration.autocommit
        
    def cursor(self, cursor_class: Optional[Type[Cursor]] = None, **kwargs: Any) -> Cursor:
        """
        Returns a new cursor object for the current connection
        
        Args:
            cursor_class: Optional custom cursor class
            **kwargs: Additional cursor parameters (named_tuple, dictionary, etc.)
            
        Returns:
            Cursor object
        """
        self._check_closed()
        
        # Update configuration with cursor-specific options
        if kwargs:
            # Create a temporary configuration with cursor options
            temp_config = Configuration.from_dict({**self._connection_params, **kwargs})
            # Update the client's configuration temporarily
            original_config = self._client.configuration
            self._client.configuration = temp_config
            
            try:
                if cursor_class is None:
                    cursor = Cursor(self)
                else:
                    cursor = cursor_class(self, **kwargs)
                    
                # Store the configuration on the cursor for later use
                cursor._cursor_config = temp_config
                return cursor
            finally:
                # Restore original configuration
                self._client.configuration = original_config
        else:
            if cursor_class is None:
                return Cursor(self)
            else:
                return cursor_class(self, **kwargs)
        
    def commit(self) -> None:
        """Commit the current transaction"""
        self._check_closed()
        # Stub implementation
        pass
        
    def rollback(self) -> None:
        """Rollback the current transaction"""
        self._check_closed()
        # Stub implementation
        pass
        
    def close(self) -> None:
        """Close the connection"""
        if not self._closed:
            self._closed = True
            if hasattr(self, '_client') and self._client:
                try:
                    self._client.close()
                except Exception:
                    pass  # Ignore errors during close
            
    def ping(self) -> bool:
        """Check if the connection to the server is alive"""
        self._check_closed()
        if hasattr(self, '_client') and self._client:
            try:
                from .impl.message.client.ping_packet import PingPacket
                ping_packet = PingPacket()
                results = self._client.execute(ping_packet, self._configuration)
                return True  # If no exception, ping succeeded
            except Exception as e:
                raise OperationalError(f"Ping failed: {e}")
        else:
            raise NotSupportedError("Connection client not available")
    
    def reconnect(self) -> None:
        """Reconnect to the database server"""
        self._check_closed()
        raise NotSupportedError("Pure Python implementation - reconnect not yet implemented")
        
    def reset(self) -> None:
        """Reset the connection"""
        self._check_closed()
        raise NotSupportedError("Pure Python implementation - reset not yet implemented")
        
    def change_user(self, user: str, password: str, database: Optional[str] = None) -> None:
        """Change the user and database of the current connection"""
        self._check_closed()
        raise NotSupportedError("Pure Python implementation - change_user not yet implemented")
        
    def select_db(self, database: str) -> None:
        """Set the current database"""
        self._check_closed()
        self.database = database

    @property
    def connection_id(self) -> int:
        """Get current connection_id"""
        if not self._closed and self._client and self._client.context:
            return self._client.context.connection_id
        return -1
    
    @property
    def database(self) -> Optional[str]:
        """Get current database name"""
        # Try to get from context first (most up-to-date), then fall back to stored value
        if self._client and self._client.context:
            context_db = self._client.context.database
            if context_db is not None:
                return context_db
        return self._database
    
    @database.setter
    def database(self, value: Optional[str]) -> None:
        """Set database name"""
        self._check_closed()
        if self._client and self._client.context:
            context_db = self._client.context.database
            if context_db is not None and value == context_db:
                return
        
        # Send COM_INIT_DB packet to change database
        if self._client and value:
            from .impl.message.client.change_db_packet import ChangeDbPacket
            packet = ChangeDbPacket(value)
            self._client.execute(packet, self._configuration)
            
        self._database = value
    
    @property
    def autocommit(self) -> bool:
        """Get current autocommit status"""
        # Get from server status if available, otherwise fall back to stored value
        if self._client and self._client.context:
            server_status = self._client.context.server_status
            return (server_status & constants.STATUS.AUTOCOMMIT) > 0
        return False
    
    @autocommit.setter
    def autocommit(self, value: bool) -> None:
        """Set autocommit status"""
        self._check_closed()
        
        # If already at the desired state, do nothing
        if self.autocommit == bool(value):
            return
        
        # Execute SET autocommit query
        if self._client:
            from .impl.message.client.query_packet import QueryPacket
            query = f"SET autocommit={1 if value else 0}"
            packet = QueryPacket(query)
            self._client.execute(packet, self._configuration)
    
    @property
    def server_status(self) -> int:
        """Get current server_status status"""
        # Get server status if available
        if self._client and self._client.context:
            return int(self._client.context.server_status)
        return 0
    
    def escape_string(self, string: str) -> str:
        """Escape a string for use in SQL statements"""
        self._check_closed()
        no_backslash_escapes = (self._client.context.server_status & constants.STATUS.NO_BACKSLASH_ESCAPES) > 0
        return StringEscaper.escape_string_with_quotes(string, no_backslash_escapes)        
        
    def __enter__(self) -> 'Connection':
        """Context manager entry"""
        return self
        
    def __exit__(self, exc_type: Optional[type], exc_val: Optional[Exception], exc_tb: Optional[Any]) -> bool:
        """Context manager exit"""
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()
        return False
        
    @property
    def server_version(self) -> int:
        """Get server version as integer in format MMPPRR (major, minor, patch with 2 digits each)"""
        self._check_closed()
        if not self._client or not self._client.context or not self._client.context.server_version:
            return 0
        
        # Parse version string like "12.1.1-MariaDB-ubu2404" or "8.4.0"
        import re
        version_match = re.search(r'(\d+)\.(\d+)\.(\d+)', self._client.context.server_version)
        if version_match:
            major = int(version_match.group(1))
            minor = int(version_match.group(2))
            patch = int(version_match.group(3))
            
            # Convert to MMPPRR format (e.g., 8.4.0 -> 080400, 12.1.1 -> 120101)
            return major * 10000 + minor * 100 + patch
        
        return 0

    @property
    def server_version_info(self):
        """
        Returns numeric version of connected database server in tuple format.
        """

        self._check_closed()
        version = self.server_version
        return (int(version / 10000),
                int((version % 10000) / 100),
                version % 100)

    def get_server_version(self):
        """
        Returns a tuple representing the version of the connected server in
        the following format: (MAJOR_VERSION, MINOR_VERSION, PATCH_VERSION)
        """

        return self.server_version_info

    @property
    def server_info(self) -> Optional[str]:
        """Get server version as string"""
        self._check_closed()
        if self._client and self._client.context:
            return self._client.context.server_version
        return None
        
    @property
    def character_set(self) -> str:
        """Get current character set"""
        return _DEFAULT_CHARSET
        
    @property
    def collation(self) -> str:
        """Get current collation"""
        return _DEFAULT_COLLATION

    @property
    def server_port(self) -> Optional[str]:
        """
        Database server TCP/IP port. This value will be 0 in case of an unix
        socket connection.
        """
        self._check_closed()
        if self._client and self._client.context:
            return str(self._client.host_address.port)
        return None

    @property
    def unix_socket(self) -> Optional[str]:
        """Unix socket name."""

        self._check_closed()
        return None

    @property
    def server_name(self) -> Optional[str]:
        """Name or IP address of database server."""
        self._check_closed()
        if self._client and self._client.context:
            return str(self._client.host_address.host)
        return None

    @property
    def _tls(self) -> Optional[str]:
        """
        Get if using SSL connection
        
        Returns:
            True if SSL is active,
            False if not using SSL connection
        """
        self._check_closed()
        if (self._client and 
            hasattr(self._client, 'ssl_wrapper') and 
            self._client.ssl_wrapper):
            return self._client.ssl_wrapper.get_tls_version() != None
        return False

    @property
    def _tls_version(self) -> Optional[str]:
        """
        Get current TLS version if using SSL connection
        
        Returns:
            TLS version string (e.g., 'TLSv1.3', 'TLSv1.2') if SSL is active,
            None if not using SSL connection
        """
        self._check_closed()
        if (self._client and 
            hasattr(self._client, 'ssl_wrapper') and 
            self._client.ssl_wrapper):
            return self._client.ssl_wrapper.get_tls_version()
        return None

    @property
    def tls_peer_cert_info(self) -> Optional[dict]:
        """
        Get peer certificate information for TLS connections
        
        Returns:
            Dictionary containing certificate information if TLS is active,
            None if not using TLS connection
        """
        self._check_closed()
        if (self._client and 
            getattr(self._client, 'ssl_wrapper', None) is not None):
            return self._client.ssl_wrapper.get_peer_certificate()
        return None

    @property
    def _tls_verify_status(self) -> Optional[int]:
        """
        Get TLS certificate verification status
        
        Returns:
            None if SSL is not enabled,
            1 if SSL verification is enabled (check_hostname=True and verify_mode=CERT_REQUIRED),
            0 if SSL is enabled but verification is disabled
        """
        self._check_closed()
        if (self._client and 
            getattr(self._client, 'ssl_wrapper', None) is not None):
            # SSL is enabled, check verification settings
            ssl_wrapper = self._client.ssl_wrapper
            if hasattr(ssl_wrapper, 'ssl_context'):
                context = ssl_wrapper.ssl_context
                # Check if both hostname verification and certificate verification are enabled
                if (getattr(context, 'check_hostname', False) and 
                    getattr(context, 'verify_mode', None) == ssl.CERT_REQUIRED):
                    return 1
                else:
                    return 0
            return 0
        return None

    def __del__(self) -> None:
        """Destructor - close connection if still open"""
        if not self._closed:
            self.close()
