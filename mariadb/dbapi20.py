"""
DB-API 2.0 compliant types and utility functions.

This module defines the types and utility functions required by PEP 249
(Python Database API Specification v2.0).
"""
import datetime
import time

from mariadb_shared import constants

# ==============================================================================
# DB-API 2.0 Module Attributes
# ==============================================================================

apilevel = '2.0'
paramstyle = 'qmark'
threadsafety = 3


# ==============================================================================
# Type System
# ==============================================================================

class DbApiType(frozenset):
    """
    Immutable set for DB-API 2.0 type checking.

    This class allows comparing field types against predefined type categories.
    By default, the following type sets are defined:

    - BINARY: Binary field types (BLOB, GEOMETRY, etc.)
    - NUMBER: Numeric field types (INT, FLOAT, DECIMAL, etc.)
    - STRING: Character-based field types (VARCHAR, TEXT, etc.)
    - DATE: Date field types
    - DATETIME: DateTime and Timestamp field types
    - TIME: Time field types
    - TIMESTAMP: Alias for DATETIME (includes TIMESTAMP types)
    - ROWID: Row identifier types (currently empty)

    Example:
        >>> from mariadb_shared import constants
        >>> constants.FIELD_TYPE.GEOMETRY == BINARY
        True
        >>> constants.FIELD_TYPE.FLOAT == BINARY
        False
    """

    def __eq__(self, field_type):
        """
        Compare this type set with a field type or another DbApiType.

        Args:
            field_type: Field type constant or another DbApiType instance

        Returns:
            bool: True if the field type is in this type set
        """
        if isinstance(field_type, DbApiType):
            return not self.difference(field_type)
        return field_type in self


# DB-API 2.0 Type Objects
BINARY = DbApiType([
    constants.FIELD_TYPE.GEOMETRY,
    constants.FIELD_TYPE.LONG_BLOB,
    constants.FIELD_TYPE.MEDIUM_BLOB,
    constants.FIELD_TYPE.TINY_BLOB,
    constants.FIELD_TYPE.BLOB
])

STRING = DbApiType([
    constants.FIELD_TYPE.ENUM,
    constants.FIELD_TYPE.JSON,
    constants.FIELD_TYPE.STRING,
    constants.FIELD_TYPE.VARCHAR,
    constants.FIELD_TYPE.VAR_STRING
])

NUMBER = DbApiType([
    constants.FIELD_TYPE.DECIMAL,
    constants.FIELD_TYPE.DOUBLE,
    constants.FIELD_TYPE.FLOAT,
    constants.FIELD_TYPE.INT24,
    constants.FIELD_TYPE.LONG,
    constants.FIELD_TYPE.LONGLONG,
    constants.FIELD_TYPE.NEWDECIMAL,
    constants.FIELD_TYPE.SHORT,
    constants.FIELD_TYPE.TINY,
    constants.FIELD_TYPE.YEAR
])

DATE = DbApiType([constants.FIELD_TYPE.DATE])

TIME = DbApiType([constants.FIELD_TYPE.TIME])

DATETIME = DbApiType([
    constants.FIELD_TYPE.DATETIME,
    constants.FIELD_TYPE.TIMESTAMP
])

TIMESTAMP = DATETIME  # Alias for backwards compatibility

ROWID = DbApiType()


# ==============================================================================
# Constructor Functions
# ==============================================================================

def Binary(obj):
    """
    Construct an object capable of holding a binary value.

    Args:
        obj: Object to convert to bytes

    Returns:
        bytes: Binary representation of the object
    """
    return bytes(obj)


def Date(year, month, day):
    """
    Construct an object holding a date value.

    Args:
        year (int): Year value
        month (int): Month value (1-12)
        day (int): Day value (1-31)

    Returns:
        datetime.date: Date object
    """
    return datetime.date(year, month, day)


def Time(hour, minute, second):
    """
    Construct an object holding a time value.

    Args:
        hour (int): Hour value (0-23)
        minute (int): Minute value (0-59)
        second (int): Second value (0-59)

    Returns:
        datetime.time: Time object
    """
    return datetime.time(hour, minute, second)


def Timestamp(year, month, day, hour, minute, second):
    """
    Construct an object holding a datetime value.

    Args:
        year (int): Year value
        month (int): Month value (1-12)
        day (int): Day value (1-31)
        hour (int): Hour value (0-23)
        minute (int): Minute value (0-59)
        second (int): Second value (0-59)

    Returns:
        datetime.datetime: DateTime object
    """
    return datetime.datetime(year, month, day, hour, minute, second)


# ==============================================================================
# Time-based Constructor Functions
# ==============================================================================

def DateFromTicks(ticks):
    """
    Construct a date object from the given ticks value.

    The ticks value represents the number of seconds since the epoch
    (January 1, 1970, 00:00:00 UTC).

    Args:
        ticks (float): Number of seconds since the epoch

    Returns:
        datetime.date: Date object constructed from ticks

    See Also:
        Standard Python time module documentation for more information
        about ticks and time representation.
    """
    return Date(*time.localtime(ticks)[:3])


def TimeFromTicks(ticks):
    """
    Construct a time object from the given ticks value.

    The ticks value represents the number of seconds since the epoch
    (January 1, 1970, 00:00:00 UTC).

    Args:
        ticks (float): Number of seconds since the epoch

    Returns:
        datetime.time: Time object constructed from ticks

    See Also:
        Standard Python time module documentation for more information
        about ticks and time representation.
    """
    return Time(*time.localtime(ticks)[3:6])


def TimestampFromTicks(ticks):
    """
    Construct a datetime object from the given ticks value.

    The ticks value represents the number of seconds since the epoch
    (January 1, 1970, 00:00:00 UTC).

    Args:
        ticks (float): Number of seconds since the epoch

    Returns:
        datetime.datetime: DateTime object constructed from ticks

    See Also:
        Standard Python time module documentation for more information
        about ticks and time representation.
    """
    return datetime.datetime(*time.localtime(ticks)[:6])


# ==============================================================================
# Module Exports
# ==============================================================================

__all__ = [
    # DB-API 2.0 module attributes
    'apilevel',
    'paramstyle',
    'threadsafety',
    # Type system
    'DbApiType',
    'BINARY',
    'STRING',
    'NUMBER',
    'DATE',
    'TIME',
    'DATETIME',
    'TIMESTAMP',
    'ROWID',
    # Constructor functions
    'Binary',
    'Date',
    'Time',
    'Timestamp',
    'DateFromTicks',
    'TimeFromTicks',
    'TimestampFromTicks',
]
