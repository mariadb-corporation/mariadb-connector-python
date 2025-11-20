# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from typing import Optional, Any
from ...exceptions import (
    DatabaseError, 
    OperationalError, 
    IntegrityError, 
    ProgrammingError,
    DataError,
    NotSupportedError,
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
            elif sql_state.startswith('23') or sql_state.startswith('XA'):
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
        
        if errno:
            if errno in (1044, 1045, 1046, 1049, 1142, 1143, 1227, 1370):
                # Access denied errors and database errors
                exception_class = ProgrammingError if errno == 1049 else OperationalError
            elif errno in (2002, 2003, 2006, 2013):
                # Connection errors (can't connect, lost connection, etc.)
                exception_class = OperationalError
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
