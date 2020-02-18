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

static PyObject *get_exception_type(const char *sqlstate)
{
  if (!sqlstate || strlen(sqlstate) != 5)
    return NULL;

  if (!strncmp(sqlstate, "21", 2) ||
      !strncmp(sqlstate, "22", 2) ||
      !strncmp(sqlstate, "02", 2))
    return Mariadb_DataError;

  if (!strncmp(sqlstate, "07", 2) ||
      !strncmp(sqlstate, "2B", 2) ||
      !strncmp(sqlstate, "2D", 2) ||
      !strncmp(sqlstate, "33", 2) ||
      !strncmp(sqlstate, "HY", 2))
    return Mariadb_DatabaseError;

  if (!strncmp(sqlstate, "23", 2) ||
      !strncmp(sqlstate, "XA", 2))
    return Mariadb_IntegrityError;

  if (!strncmp(sqlstate, "0A", 2))
    return Mariadb_NotSupportedError;

  if (!strncmp(sqlstate, "40", 2) ||
      !strncmp(sqlstate, "44", 2))
    return Mariadb_InternalError;

  if (!strncmp(sqlstate, "0K", 2) ||
      !strncmp(sqlstate, "08", 2) ||
      !strncmp(sqlstate, "HZ", 2))
    return Mariadb_OperationalError;

  if (!strncmp(sqlstate, "24", 2) ||
      !strncmp(sqlstate, "25", 2) ||
      !strncmp(sqlstate, "26", 2) ||
      !strncmp(sqlstate, "27", 2) ||
      !strncmp(sqlstate, "28", 2) ||
      !strncmp(sqlstate, "2A", 2) ||
      !strncmp(sqlstate, "2C", 2) ||
      !strncmp(sqlstate, "2F", 2) ||
      !strncmp(sqlstate, "34", 2) ||
      !strncmp(sqlstate, "35", 2) ||
      !strncmp(sqlstate, "3C", 2) ||
      !strncmp(sqlstate, "3D", 2) ||
      !strncmp(sqlstate, "3F", 2) ||
      !strncmp(sqlstate, "37", 2) ||
      !strncmp(sqlstate, "42", 2) ||
      !strncmp(sqlstate, "70", 2))
    return Mariadb_ProgrammingError;

  return NULL;
}

/**
 mariadb_throw_exception()
 @brief  raises an exception

 @param  handle[in]            a connection or statement handle
 @param  exception_type[in]    type of exception
 @param  is_statement[in]      1 is handle is a MYSQL_STMT handle
 @param  message[in]           Error message. If message is NULL, the error
                               message will be retrieved from specified handle.
 @param  ... [in]              message parameter

 @return void

*/
void mariadb_throw_exception(void *handle,
                             PyObject *exception_type,
                             unsigned char is_statement,
                             const char *message,
                             ...)
{
  va_list ap;
  PyObject *ErrorMsg= 0;
  PyObject *ErrorNo= 0;
  PyObject *SqlState= 0;
  PyObject *Exception= 0;

  //if (!exception_type)
//    exception_type= Mariadb_InterfaceError;

  if (message)
  {
    ErrorNo= PyLong_FromLong(-1);
    SqlState= PyUnicode_FromString("HY000");
    va_start(ap, message);
    ErrorMsg= PyUnicode_FromFormatV(message, ap);
    va_end(ap);
  } else
  {
    exception_type= get_exception_type(is_statement ? mysql_stmt_sqlstate((MYSQL_STMT*) handle) : mysql_sqlstate((MYSQL *)handle));

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



