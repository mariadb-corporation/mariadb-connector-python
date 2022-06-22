/******************************************************************************
  Copyright (C) 2018-2020 Georg Richter and MariaDB Corporation AB

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
 ******************************************************************************/
#define MARIADB_CONNECTION

#include "mariadb_python.h"
#include "docs/module.h"
#include "docs/exception.h"
#include <structmember.h>
#include <datetime.h>

extern int codecs_datetime_init(void);

PyObject *decimal_module= NULL,
         *decimal_type= NULL,
         *socket_module= NULL,
         *indicator_module= NULL;
extern uint16_t max_pool_size;

int
Mariadb_traverse(PyObject *self,
                 visitproc visit,
                 void *arg)
{
    return 0;
}

static PyMethodDef
Mariadb_Methods[] =
{
    /* PEP-249: mandatory */
    {"connect", (PyCFunction)MrdbConnection_connect,
        METH_VARARGS | METH_KEYWORDS,
        module_connect__doc__},
    /* Todo: add methods for api functions which don't require
       a connection */
    {NULL} /* always last */
};

/* MariaDB module definition */
static struct PyModuleDef 
mariadb_module= {
    PyModuleDef_HEAD_INIT,
    "_mariadb",
    "MariaDB Connector for Python",
    -1,
    Mariadb_Methods
};

static int mariadb_datetime_init(void)
{
    PyDateTime_IMPORT;

    if (!PyDateTimeAPI) {
        PyErr_SetString(PyExc_ImportError, "DateTimeAPI initialization failed");
        return 1;
    }
    return 0;
}

static void mariadb_add_exception(PyObject *module,
        PyObject **exception,
        const char *exception_name,
        PyObject *base_exception,
        const char *doc,
        const char *object_name)
{
    *exception= PyErr_NewExceptionWithDoc(exception_name,
            doc,
            Mariadb_Error,
            NULL);

    Py_INCREF(*exception);
    PyModule_AddObject(module, object_name, *exception);
}

/* MariaDB module initialization function */
PyMODINIT_FUNC PyInit__mariadb(void)
{
    PyObject *module= PyModule_Create(&mariadb_module);

    /* Initialize DateTimeAPI */
    if (mariadb_datetime_init() ||
        codecs_datetime_init())
    {
        goto error;
    }

    Py_SET_TYPE(&MrdbConnection_Type, &PyType_Type);
    if (PyType_Ready(&MrdbConnection_Type) == -1)
    {
        goto error;
    }

    /* Import Decimal support (CONPY-49) */
    if (!(decimal_module= PyImport_ImportModule("decimal")) ||
        !(decimal_type= PyObject_GetAttrString(decimal_module, "Decimal")))
    {
        goto error;
    }

    if (!(socket_module= PyImport_ImportModule("socket")))
    {
        goto error;
    }

    Py_SET_TYPE(&MrdbCursor_Type, &PyType_Type);
    if (PyType_Ready(&MrdbCursor_Type) == -1)
    {
        goto error;
    }
    PyModule_AddObject(module, "cursor", (PyObject *)&MrdbCursor_Type);

    /* optional (MariaDB specific) globals */
    PyModule_AddObject(module, "mariadbapi_version",
                       PyUnicode_FromString(mysql_get_client_info()));

    Mariadb_Error= PyErr_NewException("mariadb.Error",
            PyExc_Exception,
            NULL);
    Py_INCREF(Mariadb_Error);
    PyModule_AddObject(module, "Error", Mariadb_Error);

    mariadb_add_exception(module, &Mariadb_InterfaceError,
            "mariadb.InterfaceError", Mariadb_Error,
            exception_interface__doc__, "InterfaceError");
    mariadb_add_exception(module, &Mariadb_DatabaseError,
            "mariadb.DatabaseError", Mariadb_Error,
            exception_database__doc__, "DatabaseError");
    mariadb_add_exception(module, &Mariadb_OperationalError,
            "mariadb.OperationalError", Mariadb_Error,
            exception_operational__doc__, "OperationalError");
    mariadb_add_exception(module, &Mariadb_Warning,
            "mariadb.Warning", NULL, exception_warning__doc__, "Warning");
    mariadb_add_exception(module, &Mariadb_IntegrityError,
            "mariadb.IntegrityError", Mariadb_Error,
            exception_integrity__doc__, "IntegrityError");
    mariadb_add_exception(module, &Mariadb_InternalError,
            "mariadb.InternalError", Mariadb_Error,
            exception_internal__doc__, "InternalError");
    mariadb_add_exception(module, &Mariadb_ProgrammingError,
            "mariadb.ProgrammingError", Mariadb_Error,
            exception_programming__doc__, "ProgrammingError");
    mariadb_add_exception(module, &Mariadb_NotSupportedError,
            "mariadb.NotSupportedError", Mariadb_Error,
            exception_notsupported__doc__, "NotSupportedError");
    mariadb_add_exception(module, &Mariadb_DataError,
            "mariadb.DataError", Mariadb_DatabaseError,
            exception_data__doc__, "DataError");
    mariadb_add_exception(module, &Mariadb_PoolError,
            "mariadb.PoolError", Mariadb_Error,
            exception_pool__doc__, "PoolError");

    Py_INCREF(&MrdbConnection_Type);
    PyModule_AddObject(module, "connection", (PyObject *)&MrdbConnection_Type);

    return module;
error:
    PyErr_SetString(PyExc_ImportError, "Mariadb module initialization failed");
    return NULL;
}
