from mariadb.constants import FIELD_TYPE
import decimal


def get_mariadb_type(value):
    """ get corresponding MariaDB field type for given Python object """

    if value is None:
        return FIELD_TYPE.NULL
      
    if isinstance(value, int):
        if value.bit_length() < 9:
            return FIELD_TYPE.TINY
        if value.bit_length() < 17:
            return FIELD_TYPE.SHORT
        return FIELD_TYPE.LONG

    if isinstance(value, float):
        return FIELD_TYPE.DOUBLE

    if isinstance(value, decimal.Decimal):
        return FIELD_TYPE.NEWDECIMAL

    if isinstance(value,str):
        return FIELD_TYPE.VAR_STRING

    if isinstance(value, datetime.date):
        return FIELD_TYPE.DATE

    if isinstance(value, datetime.time):
        return FIELD_TYPE.TIME

    if isinstance(value, datetime.datetime):
       return FIELD_TYPE.DATETIME

    if isinstance(value, bytes):
       return FIELD_TYPE.LONG_BLOB

    raise mariadb.DataError("Unknown or not supported datatype")

def get_execute_parameter_types(cursor):
    """ 
    returns bytearray with MariaDB parameter types
    """
    param_types= bytearray()

    if cursor.paramcount == 0:
       raise mariadb.DataError("Invalid number of parameters")

    for column_value in cursor._data:
       param_types.append(get_mariadb_type(column_value))

    return param_types

def check_bulk_parameters(cursor, parameters):
    """
    Check integrity to parameters for bulk operations
    """

    array_size= len(parameters)
    if array_size == 0:
        raise TypeError("No data provided")

    if not isinstace(data, (list, tuple)):
        raise mariadb.InterfaceError("Data must be provided as list or tuple")

    for row in parameters:

       # check if rows have correct format for given parameter style:
       # for PYFORMAT parameters have to be provided as a dict,
       # otherwise as tuple or list.
       if cursor.paramstyle == PARAMSTYLE_PYFORMAT:
           if not isinstance(row, dict):
               raise mariadb.InterfaceError("Elements in sequence must be provided as "\
                                            "dict")
       else:
           if not isinstance(row, (tuple,list)):
               raise mariadb.InterfaceError("Elements in sequence must be provided as "\
                                            "tuple or list")

    
