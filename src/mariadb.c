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

#include "mariadb_python.h"
#include <structmember.h>
#include <datetime.h>

int Mariadb_traverse(PyObject *self,
                     visitproc visit,
                     void *arg)
{
	return 0;
}

static PyObject *Mariadb_date_from_ticks(PyObject *self,
                                         PyObject *args);
static PyObject *Mariadb_time_from_ticks(PyObject *self,
                                         PyObject *args);
static PyObject *Mariadb_timestamp_from_ticks(PyObject *self,
                                         PyObject *args);
static PyObject *Mariadb_date(PyObject *self,
                              PyObject *args);
static PyObject *Mariadb_time(PyObject *self,
                              PyObject *args);
static PyObject *Mariadb_timestamp(PyObject *self,
                                   PyObject *args);
static PyObject *Mariadb_binary(PyObject *self,
                               PyObject *args);

static PyMethodDef Mariadb_Methods[] =
{
  /* PEP-249: mandatory */
  {"Binary", (PyCFunction)Mariadb_binary,
     METH_VARARGS,
     "Returns a binary object"},
  {"connect", (PyCFunction)MrdbConnection_connect,
     METH_VARARGS | METH_KEYWORDS,
     "Connect with a MySQL server"},
  /* PEP-249 DB-API */
  {"DateFromTicks", (PyCFunction)Mariadb_date_from_ticks,
     METH_VARARGS,
     "Get date from ticks"},
  {"TimeFromTicks", (PyCFunction)Mariadb_time_from_ticks,
     METH_VARARGS,
     "Get time from ticks"},
  {"TimestampFromTicks", (PyCFunction)Mariadb_timestamp_from_ticks,
     METH_VARARGS,
     "Get timestamp from ticks"},
  {"Date", (PyCFunction)Mariadb_date,
     METH_VARARGS,
     "Constructs an object holding a date value"},
  {"Time", (PyCFunction)Mariadb_time,
     METH_VARARGS,
     "Constructs an object holding a time value"},
  {"Timestamp", (PyCFunction)Mariadb_timestamp,
     METH_VARARGS,
     "Constructs an object holding a time value"},
  /* Todo: add methods for api functions which don't require
           a connection */
  {NULL} /* always last */
};

/* MariaDB module definition */
static struct PyModuleDef mariadb_module= {
  PyModuleDef_HEAD_INIT,
  "mariadb",
  "MariaDB Connector for Python",
  -1,
  Mariadb_Methods
};

/*  constants */
struct st_constants {
  const char *name;
  union {
    long lvalue;
    const char *strvalue;
  } u;
 };

 struct st_constants int_constants[]= {
  {"CURSOR_TYPE_READ_ONLY", {CURSOR_TYPE_READ_ONLY}},
  {"CURSOR_TYPE_NONE", {CURSOR_TYPE_NO_CURSOR}},
  {NULL, {0}} /* Always last */
};

static void mariadb_add_exception(PyObject *module,
                                  PyObject **exception,
                                  const char *exception_name,
                                  const char *object_name)
{
  *exception= PyErr_NewException(exception_name,
                                 Mariadb_Error,
                                 NULL);

  Py_INCREF(*exception);
  PyModule_AddObject(module, object_name, *exception);
}

/* MariaDB module initialization function */
PyMODINIT_FUNC PyInit_mariadb(void)
{
  PyObject *module= PyModule_Create(&mariadb_module);
  struct st_constants *intvals= int_constants;

  Py_TYPE(&MrdbConnection_Type) = &PyType_Type;
  if (PyType_Ready(&MrdbConnection_Type) == -1)
    goto error;

  Py_TYPE(&MrdbCursor_Type) = &PyType_Type;
  if (PyType_Ready(&MrdbCursor_Type) == -1)
    goto error;

  Py_TYPE(&MrdbIndicator_Type) = &PyType_Type;
  if (PyType_Ready(&MrdbIndicator_Type) == -1)
    goto error;

  Py_TYPE(&Mariadb_Fieldinfo_Type) = &PyType_Type;
  if (PyType_Ready(&Mariadb_Fieldinfo_Type) == -1)
    goto error;

  Py_TYPE(&Mariadb_DBAPIType_Type) = &PyType_Type;
  if (PyType_Ready(&Mariadb_DBAPIType_Type) == -1)
    goto error;

  /* Mariadb module constants */
  while (intvals->name) {
    PyModule_AddIntConstant(module, intvals->name,
                                    intvals->u.lvalue);
    intvals++;
  }

  /* PEP-249: mandatory module globals */
  PyModule_AddObject(module, "apilevel", PyUnicode_FromString(MARIADB_PY_APILEVEL));
  PyModule_AddObject(module, "paramstyle", PyUnicode_FromString(MARIADB_PY_PARAMSTYLE));
  PyModule_AddObject(module, "threadsafety", PyLong_FromLong(MARIADB_PY_THREADSAFETY));
  /* optional (MariaDB specific) globals */
  PyModule_AddObject(module, "mariadbapi_version", PyUnicode_FromString(mysql_get_client_info()));

  Mariadb_Error= PyErr_NewException("mariadb.Error",
                                    PyExc_Exception,
                                    NULL);
  Py_INCREF(Mariadb_Error);
  PyModule_AddObject(module, "Error", Mariadb_Error);

  mariadb_add_exception(module, &Mariadb_InterfaceError,
                        "mariadb.InterfaceError", "InterfaceError");
  mariadb_add_exception(module, &Mariadb_OperationalError,
                        "mariadb.OperationalError", "OperationalError");
  mariadb_add_exception(module, &Mariadb_Warning,
                        "mariadb.Warning", "Warning");
  mariadb_add_exception(module, &Mariadb_OperationalError,
                        "mariadb.OperationalError", "OperationalError");
  mariadb_add_exception(module, &Mariadb_IntegrityError,
                        "mariadb.IntegrityError", "IntegrityError");
  mariadb_add_exception(module, &Mariadb_InternalError,
                        "mariadb.InternalError", "InternalError");
  mariadb_add_exception(module, &Mariadb_ProgrammingError,
                        "mariadb.ProgrammingError", "ProgrammingError");
  mariadb_add_exception(module, &Mariadb_NotSupportedError,
                        "mariadb.NotSupportedError", "NotSupportedError");
  mariadb_add_exception(module, &Mariadb_DatabaseError,
                        "mariadb.DatabaseError", "DatabaseError");
  mariadb_add_exception(module, &Mariadb_DataError,
                        "mariadb.DatabaseError.DataError", "DataError");



  PyModule_AddObject(module, "DatabaseError", Mariadb_DatabaseError);

  Py_INCREF(&MrdbConnection_Type);
  PyModule_AddObject(module, "connection", (PyObject *)&MrdbConnection_Type);

  PyModule_AddObject(module, "indicator_null", MrdbIndicator_Object(STMT_INDICATOR_NULL));
  PyModule_AddObject(module, "indicator_default", MrdbIndicator_Object(STMT_INDICATOR_DEFAULT));
  PyModule_AddObject(module, "indicator_ignore", MrdbIndicator_Object(STMT_INDICATOR_IGNORE));
  PyModule_AddObject(module, "indicator_row", MrdbIndicator_Object(STMT_INDICATOR_IGNORE_ROW));

  PyModule_AddObject(module, "NUMBER", Mariadb_DBAPIType_Object(DBAPI_NUMBER));
  PyModule_AddObject(module, "BINARY", Mariadb_DBAPIType_Object(DBAPI_BINARY));
  PyModule_AddObject(module, "STRING", Mariadb_DBAPIType_Object(DBAPI_STRING));
  PyModule_AddObject(module, "DATETIME", Mariadb_DBAPIType_Object(DBAPI_DATETIME));
  PyModule_AddObject(module, "ROWID", Mariadb_DBAPIType_Object(DBAPI_ROWID));



  Py_INCREF(&MrdbCursor_Type);
  PyModule_AddObject(module, "cursor", (PyObject *)&MrdbCursor_Type);

  Py_INCREF(&Mariadb_Fieldinfo_Type);
  PyModule_AddObject(module, "fieldinfo", (PyObject *)&Mariadb_Fieldinfo_Type);

  return module;
error:
  PyErr_SetString(PyExc_ImportError, "Mariadb module initialization failed");
  return NULL;
}

static time_t get_ticks(PyObject *object)
{
  time_t ticks= 0;
  if (Py_TYPE(object) == &PyFloat_Type)
    ticks= (time_t)PyFloat_AsDouble(object);
  if (Py_TYPE(object) == &PyLong_Type)
    ticks= (time_t)PyLong_AsLong(object);
  return ticks;
}

static PyObject *Mariadb_date_from_ticks(PyObject *module,
                                         PyObject *args)
{
  PyObject *o, *Date;
  struct tm *ts;
  time_t epoch;

  if (!PyDateTimeAPI)
    PyDateTime_IMPORT;


  if (!PyArg_ParseTuple(args, "O", &o))
    return NULL;

  epoch= get_ticks(o);
  ts= localtime(&epoch);

  Date= PyDate_FromDate(ts->tm_year + 1900, ts->tm_mon + 1, ts->tm_mday);
  return Date;
}

static PyObject *Mariadb_time_from_ticks(PyObject *module,
                                         PyObject *args)
{
  struct tm *ts;
  time_t epoch;
  PyObject *o, *Time= NULL;

  if (!PyDateTimeAPI)
    PyDateTime_IMPORT;


  if (!PyArg_ParseTuple(args, "O", &o))
    return NULL;

  epoch= get_ticks(o);
  ts= localtime(&epoch);

  Time= PyTime_FromTime(ts->tm_hour, ts->tm_min, ts->tm_sec, 0);
  return Time;
}

static PyObject *Mariadb_timestamp_from_ticks(PyObject *module,
                                         PyObject *args)
{
  PyObject *o,*Timestamp;
  struct tm *ts;
  time_t epoch;

  if (!PyDateTimeAPI)
    PyDateTime_IMPORT;

  if (!PyArg_ParseTuple(args, "O", &o))
    return NULL;

  epoch= get_ticks(o);
  ts= localtime(&epoch);

  Timestamp= PyDateTime_FromDateAndTime(ts->tm_year + 1900, ts->tm_mon + 1, ts->tm_mday, ts->tm_hour, ts->tm_min, ts->tm_sec, 0);
  return Timestamp;
}

static PyObject *Mariadb_date(PyObject *self,
                              PyObject *args)
{
  PyObject *date= NULL;
  int32_t year=0, month=0, day= 0;

  if (!PyDateTimeAPI)
    PyDateTime_IMPORT;

  if (!PyArg_ParseTuple(args, "iii", &year, &month, &day))
    return NULL;

  date= PyDate_FromDate(year, month, day);
  return date;
}

static PyObject *Mariadb_timestamp(PyObject *self,
                                  PyObject *args)
{
  PyObject *timestamp= NULL;
  int32_t year=0, month=0, day= 0;
  int32_t hour=0, min=0, sec= 0;

  if (!PyDateTimeAPI)
    PyDateTime_IMPORT;
  if (!PyArg_ParseTuple(args, "iiiiii", &year, &month, &day, &hour, &min, &sec))
    return NULL;

  timestamp= PyDateTime_FromDateAndTime(year, month, day, hour, min, sec, 0);
  return timestamp;
}


static PyObject *Mariadb_time(PyObject *self,
                              PyObject *args)
{
  PyObject *time= NULL;
  int32_t hour=0, min=0, sec= 0;
  if (!PyDateTimeAPI)
    PyDateTime_IMPORT;

  if (!PyArg_ParseTuple(args, "iii", &hour, &min, &sec))
    return NULL;

  time= PyTime_FromTime(hour, min, sec, 0);
  return time;
}

static PyObject *Mariadb_binary(PyObject *self,
                               PyObject *args)
{
  PyObject *b,*o;

  if (!PyArg_ParseTuple(args, "O", &o))
    return NULL;

  b= PyBytes_FromObject(o);
  return b;
}
