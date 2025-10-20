from mariadb_shared import constants
import time
import datetime

apilevel = '2.0'

paramstyle = 'qmark'

threadsafety = True


class DbApiType(frozenset):
    """
    Immutable set for type checking

    By default the following sets are defined:

    - BINARY: for binary field types
    - NUMBER: for numeric field types
    - STRING: for character based (string) field types
    - DATE: for date field type(s)
    - DATETIME: for datetime and timestamp field type(s)
    - TIME: for time field type(s)
    - TIMESTAMP: for datetime and timestamp field type(s)


    Example:
    >>> constants.FIELD_TYPE.GEOMETRY == mariadb.BINARY
    True
    >>> constants.FIELD_TYPE.FLOAT == mariadb.BINARY
    False
    """

    def __eq__(self, field_type):
        if (isinstance(field_type, DbApiType)):
            return not self.difference(field_type)
        return field_type in self


BINARY = DbApiType([constants.FIELD_TYPE.GEOMETRY,
                    constants.FIELD_TYPE.LONG_BLOB,
                    constants.FIELD_TYPE.MEDIUM_BLOB,
                    constants.FIELD_TYPE.TINY_BLOB,
                    constants.FIELD_TYPE.BLOB])

STRING = DbApiType([constants.FIELD_TYPE.ENUM,
                    constants.FIELD_TYPE.JSON,
                    constants.FIELD_TYPE.STRING,
                    constants.FIELD_TYPE.VARCHAR,
                    constants.FIELD_TYPE.VAR_STRING])

NUMBER = DbApiType([constants.FIELD_TYPE.DECIMAL,
                    constants.FIELD_TYPE.DOUBLE,
                    constants.FIELD_TYPE.FLOAT,
                    constants.FIELD_TYPE.INT24,
                    constants.FIELD_TYPE.LONG,
                    constants.FIELD_TYPE.LONGLONG,
                    constants.FIELD_TYPE.NEWDECIMAL,
                    constants.FIELD_TYPE.SHORT,
                    constants.FIELD_TYPE.TINY,
                    constants.FIELD_TYPE.YEAR])

DATE = DbApiType([constants.FIELD_TYPE.DATE])
TIME = DbApiType([constants.FIELD_TYPE.TIME])
DATETIME = TIMESTAMP = DbApiType([constants.FIELD_TYPE.DATETIME,
                                 constants.FIELD_TYPE.TIMESTAMP])
ROWID = DbApiType()


def Binary(object):
    """Constructs an object capable of holding a binary value."""
    return bytes(object)


def Date(year, month, day):
    """Constructs an object holding a date value."""
    return datetime.date(year, month, day)


def Time(hour, minute, second):
    """Constructs an object holding a time value."""
    return datetime.time(hour, minute, second)


def Timestamp(year, month, day, hour, minute, second):
    """Constructs an object holding a datetime value."""
    return datetime.datetime(year, month, day, hour, minute, second)


def DateFromTicks(ticks):
    """Constructs an object holding a date value from the given ticks value
       (number of seconds since the epoch).
       For more information see the documentation of the standard Python
       time module."""
    return Date(*time.localtime(ticks)[:3])


def TimeFromTicks(ticks):
    """Constructs an object holding a time value from the given ticks value
       (number of seconds since the epoch).
       For more information see the documentation of the standard Python
       time module."""
    return Time(*time.localtime(ticks)[3:6])


def TimestampFromTicks(ticks):
    """Constructs an object holding a datetime value from the given ticks value
       (number of seconds since the epoch).
       For more information see the documentation of the standard Python
       time module."""
    return datetime.datetime(*time.localtime(ticks)[:6])
