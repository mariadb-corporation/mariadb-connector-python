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
    
    def create_exception(self, 
                        message: str, 
                        sql_state: Optional[str] = None, 
                        errno: Optional[int] = None,
                        sql: Optional[str] = None) -> Exception:
        """
        Create appropriate exception based on SQL state and error code
        
        Args:
            message: Error message
            sql_state: SQL state code
            errno: MySQL error code
            sql: SQL statement that caused the error
            
        Returns:
            Appropriate exception instance
        """
        exception_class = DatabaseError

        # Map SQL states to exception types
        if sql_state:
            if sql_state.startswith('08'):
                # Connection exception
                exception_class = OperationalError
            elif sql_state.startswith('23'):
                # Integrity constraint violation
                exception_class = IntegrityError
            elif sql_state.startswith('42'):
                # Syntax error or access rule violation
                exception_class = ProgrammingError
            elif sql_state.startswith('22'):
                # Data exception
                exception_class = DataError
            elif sql_state.startswith('0A'):
                # Feature not supported
                exception_class = NotSupportedError
            elif sql_state.startswith('HY'):
                # General error
                exception_class = DatabaseError
        elif errno:
            if errno in (1044, 1045, 1046, 1049, 1142, 1143, 1227, 1370):
                # Access denied errors and database errors
                exception_class = ProgrammingError if errno == 1049 else OperationalError
            elif errno in (1062, 1169, 1216, 1217, 1451, 1452):
                # Integrity constraint violations
                exception_class = IntegrityError
            elif errno in (1054, 1064, 1146, 1149, 1305, 1364):
                # Syntax and access rule violations
                exception_class = ProgrammingError
            elif errno in (1264, 1265, 1292, 1366, 1411, 1525):
                # Data exceptions
                exception_class = DataError
        
        # Create exception with proper constructor arguments
        exception = exception_class(msg=message, errno=errno, sqlstate=sql_state)
    
        return exception


    def create_communication_exception(self, message: str, cause: Optional[Exception] = None) -> OperationalError:
        """
        Create communication exception
        
        Args:
            message: Error message
            cause: Underlying cause exception
            
        Returns:
            OperationalError instance
        """
        exc = OperationalError(msg=message, errno=2013, sqlstate='08S01')  # Lost connection error code
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
        return OperationalError(msg=message, errno=1205, sqlstate='HYT00')  # Lock wait timeout
    
    def create_connection_exception(self, message: str, cause: Optional[Exception] = None) -> OperationalError:
        """
        Create connection exception
        
        Args:
            message: Error message
            cause: Underlying cause exception
            
        Returns:
            OperationalError instance
        """
        exc = OperationalError(msg=message, errno=2003, sqlstate='08001')  # Can't connect error code
        if cause:
            exc.__cause__ = cause
        return exc
