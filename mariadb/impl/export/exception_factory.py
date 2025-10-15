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
Exception Factory for MariaDB connector

Equivalent to the Java ExceptionFactory class.
"""

from typing import Optional, Any
from ...exceptions import (
    DatabaseError, 
    OperationalError, 
    IntegrityError, 
    ProgrammingError,
    InterfaceError,
    DataError,
    NotSupportedError,
    InternalError
)


class ExceptionFactory:
    """
    Factory for creating appropriate SQL exceptions
    
    Equivalent to the Java ExceptionFactory class.
    """
    
    def __init__(self):
        """Initialize exception factory"""
        self.connection = None
    
    def set_connection(self, connection: Any) -> 'ExceptionFactory':
        """
        Set connection reference
        
        Args:
            connection: Connection object
            
        Returns:
            Self for chaining
        """
        self.connection = connection
        return self
    
    def create_exception(self, 
                        message: str, 
                        sql_state: Optional[str] = None, 
                        error_code: Optional[int] = None,
                        sql: Optional[str] = None) -> Exception:
        """
        Create appropriate exception based on SQL state and error code
        
        Args:
            message: Error message
            sql_state: SQL state code
            error_code: MySQL error code
            sql: SQL statement that caused the error
            
        Returns:
            Appropriate exception instance
        """
        # Map SQL states to exception types
        if sql_state:
            if sql_state.startswith('08'):
                # Connection exception
                return OperationalError(message, sql_state, error_code)
            elif sql_state.startswith('23'):
                # Integrity constraint violation
                return IntegrityError(message, sql_state, error_code)
            elif sql_state.startswith('42'):
                # Syntax error or access rule violation
                return ProgrammingError(message, sql_state, error_code)
            elif sql_state.startswith('22'):
                # Data exception
                return DataError(message, sql_state, error_code)
            elif sql_state.startswith('0A'):
                # Feature not supported
                return NotSupportedError(message, sql_state, error_code)
            elif sql_state.startswith('HY'):
                # General error
                return DatabaseError(message, sql_state, error_code)
        
        # Map specific error codes
        if error_code:
            if error_code in (1044, 1045, 1046, 1049, 1142, 1143, 1227, 1370):
                # Access denied errors
                return OperationalError(message, sql_state, error_code)
            elif error_code in (1062, 1169, 1216, 1217, 1451, 1452):
                # Integrity constraint violations
                return IntegrityError(message, sql_state, error_code)
            elif error_code in (1054, 1064, 1146, 1149, 1305, 1364):
                # Syntax and access rule violations
                return ProgrammingError(message, sql_state, error_code)
            elif error_code in (1264, 1265, 1292, 1366, 1411, 1525):
                # Data exceptions
                return DataError(message, sql_state, error_code)
        
        # Default to DatabaseError
        return DatabaseError(message, sql_state, error_code)
    
    def create_communication_exception(self, message: str, cause: Optional[Exception] = None) -> OperationalError:
        """
        Create communication exception
        
        Args:
            message: Error message
            cause: Underlying cause exception
            
        Returns:
            OperationalError instance
        """
        exc = OperationalError(message, '08S01', 2013)  # Lost connection error code
        if cause:
            exc.__cause__ = cause
        return exc
    
    def create_timeout_exception(self, message: str) -> OperationalError:
        """
        Create timeout exception
        
        Args:
            message: Error message
            
        Returns:
            OperationalError instance
        """
        return OperationalError(message, 'HYT00', 1205)  # Lock wait timeout
    
    def create_connection_exception(self, message: str, cause: Optional[Exception] = None) -> OperationalError:
        """
        Create connection exception
        
        Args:
            message: Error message
            cause: Underlying cause exception
            
        Returns:
            OperationalError instance
        """
        exc = OperationalError(message, '08001', 2003)  # Can't connect error code
        if cause:
            exc.__cause__ = cause
        return exc
