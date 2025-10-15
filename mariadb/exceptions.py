"""
MariaDB exception classes
"""


class Error(Exception):
    """Base class for all MariaDB errors"""
    pass


class Warning(Exception):
    """Exception raised for important warnings"""
    pass


class InterfaceError(Error):
    """Exception raised for errors related to the database interface"""
    pass


class DatabaseError(Error):
    """Exception raised for errors related to the database"""
    pass


class InternalError(DatabaseError):
    """Exception raised when the database encounters an internal error"""
    pass


class OperationalError(DatabaseError):
    """Exception raised for errors related to database operation"""
    pass


class ProgrammingError(DatabaseError):
    """Exception raised for programming errors"""
    pass


class IntegrityError(DatabaseError):
    """Exception raised when database relational integrity is affected"""
    pass


class DataError(DatabaseError):
    """Exception raised for errors due to problems with processed data"""
    pass


class NotSupportedError(DatabaseError):
    """Exception raised when a method or database API is not supported"""
    pass


class PoolError(Error):
    """Exception raised for connection pool errors"""
    pass
