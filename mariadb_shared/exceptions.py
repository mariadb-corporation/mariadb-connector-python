# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
MariaDB exception hierarchy

This module defines the exception hierarchy used by both the pure Python
and C extension implementations of MariaDB Connector/Python.
"""

# Standard exception hierarchy following PEP 249 (DB API 2.0)

class Warning(UserWarning):
    """
    Exception raised for important warnings like data truncations
    while inserting, etc.
    """
    pass

class Error(Exception):
    """
    Exception that is the base class of all other error exceptions.
    You can use this to catch all errors with one single except statement.
    """
    
    def __init__(self, msg=None, errno=None, sqlstate=None):
        """
        Initialize error with message, error number, and SQL state.
        
        Args:
            msg: Error message
            errno: MySQL/MariaDB error number
            sqlstate: SQL state code (5 characters)
        """
        super().__init__(msg)
        self._msg = msg or ""
        self._errno = errno or 0
        self._sqlstate = sqlstate or "HY000"
    
    @property
    def errmsg(self):
        """Get error message"""
        return self._msg
    
    @errmsg.setter
    def errmsg(self, value):
        """Set error message"""
        self._msg = value
    
    @property
    def msg(self):
        """Get error message (alias for errmsg)"""
        return self._msg
    
    @msg.setter
    def msg(self, value):
        """Set error message"""
        self._msg = value
    
    @property
    def errno(self):
        """Get error number"""
        return self._errno
    
    @errno.setter
    def errno(self, value):
        """Set error number"""
        self._errno = value if value is not None else 0
    
    @property
    def sqlstate(self):
        """Get SQL state"""
        return self._sqlstate
    
    @sqlstate.setter
    def sqlstate(self, value):
        """Set SQL state"""
        self._sqlstate = value if value is not None else "HY000"
    
    def __str__(self):
        """String representation of error"""
        if self._errno:
            return f"{self._msg} (errno: {self._errno}, sqlstate: {self._sqlstate})"
        return self._msg

class InterfaceError(Error):
    """
    Exception raised for errors that are related to the database
    interface rather than the database itself.
    """
    pass

class DatabaseError(Error):
    """
    Exception raised for errors that are related to the database.
    """
    pass

class DataError(DatabaseError):
    """
    Exception raised for errors that are due to problems with the
    processed data like division by zero, numeric value out of range, etc.
    """
    pass

class OperationalError(DatabaseError):
    """
    Exception raised for errors that are related to the database's
    operation and not necessarily under the control of the programmer.
    """
    pass

class IntegrityError(DatabaseError):
    """
    Exception raised when the relational integrity of the database
    is affected, e.g. a foreign key check fails.
    """
    pass

class InternalError(DatabaseError):
    """
    Exception raised when the database encounters an internal error.
    """
    pass

class ProgrammingError(DatabaseError):
    """
    Exception raised for programming errors, e.g. table not found
    or already exists, syntax error in the SQL statement, wrong number
    of parameters specified, etc.
    """
    pass

class NotSupportedError(DatabaseError):
    """
    Exception raised in case a method or database API was used
    which is not supported by the database.
    """
    pass

class PoolError(Error):
    """
    Exception raised for connection pool related errors.
    """
    pass
