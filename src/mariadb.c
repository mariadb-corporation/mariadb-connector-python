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

int Mariadb_traverse(PyObject *self,
                     visitproc visit,
                     void *arg)
{
	return 0;
}

PyObject *MariaDBInterfaceError;

static PyMethodDef Mariadb_Methods[] =
{
  /* PEP-249: mandatory */
  {"connect", (PyCFunction)Mariadb_connect,
     METH_VARARGS | METH_KEYWORDS,
     "Connect with a MySQL server"},
  /* DBAPITypes 
  {"NUMBER", (PyCFunction)Mariadb_NUMBER,
    METH_VARARGS,
    ""},
  {"STRING", (PyCFunction)Mariadb_STRING,
    METH_VARARGS,
    ""},
  {"BINARY", (PyCFunction)Mariadb_BINARY,
    METH_VARARGS,
    ""},
  {"DATETIME", (PyCFunction)Mariadb_DATETIME,
    METH_VARARGS,
    ""},
  {"ROWID", (PyCFunction)Mariadb_ROWID,
    METH_VARARGS,
    ""},
    */
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
  {"INDICATOR_NTS", {STMT_INDICATOR_NTS}},
  {"INDICATOR_NONE", {STMT_INDICATOR_NONE}},
  {"INDICATOR_NULL", {STMT_INDICATOR_NULL}},
  {"INDICATOR_DEFAULT", {STMT_INDICATOR_DEFAULT}},
  {"INDICATOR_IGNORE", {STMT_INDICATOR_IGNORE}},
  {"INDICATOR_IGNORE_ROW", {STMT_INDICATOR_IGNORE_ROW}},
  {"CURSOR_TYPE_READ_ONLY", {CURSOR_TYPE_READ_ONLY}},
  {"CURSOR_TYPE_NONE", {CURSOR_TYPE_NO_CURSOR}},
  {NULL, {0}} /* Always last */
};

/* MariaDB module initialization function */
PyMODINIT_FUNC PyInit_mariadb(void)
{
  PyObject *module= PyModule_Create(&mariadb_module);
  struct st_constants *intvals= int_constants;

  Py_TYPE(&Mariadb_Connection_Type) = &PyType_Type;
  if (PyType_Ready(&Mariadb_Connection_Type) == -1)
    goto error;

  Py_TYPE(&Mariadb_Cursor_Type) = &PyType_Type;
  if (PyType_Ready(&Mariadb_Cursor_Type) == -1)
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

  Mariadb_InterfaceError= PyErr_NewException("mariadb.InterfaceError",
                                             Mariadb_Error,
                                             NULL);

  Py_INCREF(Mariadb_InterfaceError);
  PyModule_AddObject(module, "InterfaceError", Mariadb_InterfaceError);

  Mariadb_DatabaseError= PyErr_NewException("mariadb.DatabaseError",
                                            Mariadb_Error,
                                            NULL);
  Py_INCREF(Mariadb_DatabaseError);
  PyModule_AddObject(module, "DatabaseError", Mariadb_DatabaseError);

  Mariadb_DataError= PyErr_NewException("mariadb.DatabaseError.DataError",
                                         Mariadb_DatabaseError,
                                         NULL);
  Py_INCREF(Mariadb_DataError);

  PyModule_AddObject(module, "DatabaseError", Mariadb_DatabaseError);

  Py_INCREF(&Mariadb_Connection_Type);
  PyModule_AddObject(module, "connection", (PyObject *)&Mariadb_Connection_Type);
  PyModule_AddObject(module, "NUMBER", Mariadb_DBAPIType_Object(DBAPI_NUMBER));
  PyModule_AddObject(module, "BINARY", Mariadb_DBAPIType_Object(DBAPI_BINARY));
  PyModule_AddObject(module, "STRING", Mariadb_DBAPIType_Object(DBAPI_STRING));
  PyModule_AddObject(module, "DATETIME", Mariadb_DBAPIType_Object(DBAPI_DATETIME));
  PyModule_AddObject(module, "ROWID", Mariadb_DBAPIType_Object(DBAPI_ROWID));



  Py_INCREF(&Mariadb_Cursor_Type);
  PyModule_AddObject(module, "cursor", (PyObject *)&Mariadb_Cursor_Type);

  Py_INCREF(&Mariadb_Fieldinfo_Type);
  PyModule_AddObject(module, "fieldinfo", (PyObject *)&Mariadb_Fieldinfo_Type);

  return module;
error:
  PyErr_SetString(PyExc_ImportError, "Mariadb module initialization failed");
  return NULL;
}

