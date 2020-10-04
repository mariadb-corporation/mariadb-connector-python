/************************************************************************************
    Copyright (C) 2018 Georg Richter and MariaDB Corporation AB

   This library is free software; you can redistribute it and/or
   modify it under the terms of the GNU Library General Public
   License as published by the Free Software Foundation; either
   version 2 of the License, or (at your option) any later version.

   This library is distributed in the hope that it will be useful,
   but WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
   Library General Public License for more details.

   You should have received a copy of the GNU Library General Public
   License along with this library; if not see <http://www.gnu.org/licenses>
   or write to the Free Software Foundation, Inc.,
   51 Franklin St., Fifth Floor, Boston, MA 02110, USA
*************************************************************************************/

#include <mariadb_python.h>
#include <mysqld_error.h>

/* Exceptions */
PyObject *Mariadb_InterfaceError;
PyObject *Mariadb_Error;
PyObject *Mariadb_DatabaseError;
PyObject *Mariadb_DataError;
PyObject *Mariadb_PoolError;
PyObject *Mariadb_OperationalError;
PyObject *Mariadb_IntegrityError;
PyObject *Mariadb_InternalError;
PyObject *Mariadb_ProgrammingError;
PyObject *Mariadb_NotSupportedError;
PyObject *Mariadb_Warning;

struct st_error_map {
  char  sqlstate[3];
  uint8_t type;
};

static PyObject *get_exception_type(int error_number)
{
  /* This list might be incomplete, special error values which are
     not handled yet will be returned as Internal or Operational errors.
     error codes are defined in errmsg.h (client errors) and mysqld_error.h
     (server errors) */
  switch (error_number) {
  /* InterfaceError */
  case 0:
  case CR_SERVER_LOST:
  case CR_SERVER_GONE_ERROR:
  case CR_SERVER_HANDSHAKE_ERR:
  case CR_IPSOCK_ERROR:
  case CR_COMMANDS_OUT_OF_SYNC:
      return Mariadb_InterfaceError;
  /* DataError: Exception raised for errors that are due to problems with the processed
     data like division by zero, numeric value out of range, etc */
  case ER_DATA_TOO_LONG:
  case ER_DATETIME_FUNCTION_OVERFLOW:
  case ER_DIVISION_BY_ZERO:
  case ER_NO_DEFAULT:
  case ER_PRIMARY_CANT_HAVE_NULL:
  case ER_WARN_DATA_OUT_OF_RANGE:
  case WARN_DATA_TRUNCATED:
      return Mariadb_DataError;

  /* ProgrammingError: Exception raised for programming errors, e.g. table not found or 
     already exists, syntax error in the SQL statement, wrong number of parameters specified, etc. */
  case ER_EMPTY_QUERY:
  case ER_CANT_DO_THIS_DURING_AN_TRANSACTION:
  case ER_DB_CREATE_EXISTS:
  case ER_FIELD_SPECIFIED_TWICE:
  case ER_INVALID_GROUP_FUNC_USE:
  case ER_NO_SUCH_INDEX:
  case ER_NO_SUCH_KEY_VALUE:
  case ER_NO_SUCH_TABLE:
  case ER_NO_SUCH_USER:
  case ER_PARSE_ERROR:
  case ER_SYNTAX_ERROR:
  case ER_TABLE_MUST_HAVE_COLUMNS:
  case ER_UNSUPPORTED_EXTENSION:
  case ER_WRONG_DB_NAME:
  case ER_WRONG_TABLE_NAME:
  case ER_BAD_DB_ERROR:
      return Mariadb_ProgrammingError;

  /* IntegrityError: Exception raised when the relational integrity of the database is affected,
     e.g. a foreign key check fails */
  case ER_CANNOT_ADD_FOREIGN:
  case ER_DUP_ENTRY:
  case ER_DUP_UNIQUE:
  case ER_NO_DEFAULT_FOR_FIELD:
  case ER_NO_REFERENCED_ROW:
  case ER_NO_REFERENCED_ROW_2:
  case ER_ROW_IS_REFERENCED:
  case ER_ROW_IS_REFERENCED_2:
  case ER_XAER_OUTSIDE:
  case ER_XAER_RMERR:
  case ER_BAD_NULL_ERROR:
  case ER_DATA_OUT_OF_RANGE:
  case ER_CONSTRAINT_FAILED:
  case ER_DUP_CONSTRAINT_NAME:
      return Mariadb_IntegrityError;
  default:
      /* MariaDB Error */
      if (error_number >= 1000)
          return Mariadb_OperationalError;
      /* same behavior as in MySQLdb: we return an InternalError, in case of system errors */
      return Mariadb_InternalError;
  }

  return NULL;
}

void mariadb_exception_connection_gone(PyObject *exception_type,
                                  int error_no,
                                  const char *message,
                                  ...)
{
  va_list ap;
  PyObject *ErrorMsg= 0;
  PyObject *ErrorNo= 0;
  PyObject *SqlState= 0;
  PyObject *Exception= 0;

  
  ErrorNo= PyLong_FromLong(CR_UNKNOWN_ERROR);
  SqlState= PyUnicode_FromString("HY000");
  va_start(ap, message);
  ErrorMsg= PyUnicode_FromFormatV(message, ap);
  va_end(ap);

  if (!(Exception= PyObject_CallFunctionObjArgs(exception_type, ErrorMsg, NULL)))
  {
    PyErr_SetString(PyExc_RuntimeError,
                    "Failed to create exception");
    return;
  }

  PyObject_SetAttr(Exception, PyUnicode_FromString("sqlstate"), SqlState);
  PyObject_SetAttr(Exception, PyUnicode_FromString("errno"), ErrorNo);
  PyObject_SetAttr(Exception, PyUnicode_FromString("errmsg"), ErrorMsg);
  /* For MySQL Connector/Python compatibility */
  PyObject_SetAttr(Exception, PyUnicode_FromString("msg"), ErrorMsg);
  PyErr_SetObject(exception_type, Exception);
  Py_XDECREF(ErrorMsg);
  Py_XDECREF(ErrorNo);
  Py_XDECREF(SqlState);
}

/**
 mariadb_throw_exception()
 @brief  raises an exception

 @param  handle[in]            a connection or statement handle
 @param  exception_type[in]    type of exception
 @param  handle_type[in]       -1 no handle (use error_no)
                                0 MYSQL
                                1 MYSQL_STMT
 @param  message[in]           Error message. If message is NULL, the error
                               message will be retrieved from specified handle.
 @param  ... [in]              message parameter

 @return void

*/
void mariadb_throw_exception(void *handle,
                             PyObject *exception_type,
                             int8_t is_statement,
                             const char *message,
                             ...)
{
  va_list ap;
  PyObject *ErrorMsg= 0;
  PyObject *ErrorNo= 0;
  PyObject *SqlState= 0;
  PyObject *Exception= 0;

  if (message)
  {
    ErrorNo= PyLong_FromLong(CR_UNKNOWN_ERROR);
    SqlState= PyUnicode_FromString("HY000");
    va_start(ap, message);
    ErrorMsg= PyUnicode_FromFormatV(message, ap);
    va_end(ap);
  } else
  {
    exception_type= get_exception_type(is_statement ? mysql_stmt_errno((MYSQL_STMT*) handle) : mysql_errno((MYSQL *)handle));

    if (!exception_type)
      exception_type= Mariadb_DatabaseError;
 
    ErrorNo= PyLong_FromLong(is_statement ?
                          mysql_stmt_errno((MYSQL_STMT *)handle) : mysql_errno((MYSQL *)handle));
    ErrorMsg= PyUnicode_FromString(is_statement ?
                        mysql_stmt_error((MYSQL_STMT *)handle) : mysql_error((MYSQL *)handle));
    SqlState= PyUnicode_FromString(is_statement ?
                        mysql_stmt_sqlstate((MYSQL_STMT *)handle) : mysql_sqlstate((MYSQL *)handle));
  }

  if (!(Exception= PyObject_CallFunctionObjArgs(exception_type, ErrorMsg, NULL)))
  {
    PyErr_SetString(PyExc_RuntimeError,
                    "Failed to create exception");
    return;
  }

  PyObject_SetAttr(Exception, PyUnicode_FromString("sqlstate"), SqlState);
  PyObject_SetAttr(Exception, PyUnicode_FromString("errno"), ErrorNo);
  PyObject_SetAttr(Exception, PyUnicode_FromString("errmsg"), ErrorMsg);
  /* For MySQL Connector/Python compatibility */
  PyObject_SetAttr(Exception, PyUnicode_FromString("msg"), ErrorMsg);
  PyErr_SetObject(exception_type, Exception);
  Py_XDECREF(ErrorMsg);
  Py_XDECREF(ErrorNo);
  Py_XDECREF(SqlState);
}



