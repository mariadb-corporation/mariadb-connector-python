//  SPDX-License-Identifier: LGPL-2.1-or-later
//  Copyright (c) 2020-2025 MariaDB Corporation Ab

#define MARIADB_CONNECTION

#include "mariadb_python.h"
#include "docs/module.h"
#include "docs/exception.h"
#include <structmember.h>
#include <datetime.h>

#ifdef __clang__
#  if defined(__has_feature) && __has_feature(address_sanitizer)
#    define HAVE_ASAN Py_True
#  else
#    define HAVE_ASAN Py_False
#  endif
#elif defined(__GNUC__)
#  ifdef __SANITIZE_ADDRESS__
#    define HAVE_ASAN Py_True
#  else
#    define HAVE_ASAN Py_False
#  endif
#else
#  define HAVE_ASAN Py_False
#endif

extern int codecs_datetime_init(void);
extern int connection_datetime_init(void);

PyObject *decimal_module= NULL,
         *decimal_type= NULL,
         *socket_module= NULL,
         *indicator_module= NULL;

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

    /* check if client library is compatible */
    if (mysql_get_client_version() < MARIADB_PACKAGE_VERSION_ID)
    {
      char errmsg[255];

      snprintf(errmsg, 254, "MariaDB Connector/Python was build with MariaDB Connector/C %s, "
               "while the loaded MariaDB Connector/C library has version %s.",
               MARIADB_PACKAGE_VERSION, mysql_get_client_info());
      PyErr_SetString(PyExc_ImportError, errmsg);
      goto error;
    }

    /* Initialize DateTimeAPI */
    if (mariadb_datetime_init() ||
        connection_datetime_init() ||
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
        !(decimal_type= PyObject_GetAttr(decimal_module, PyUnicode_FromString("Decimal"))))
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

    // Import exceptions from main mariadb package
    // This MUST succeed - if mariadb package is not available, we should fail
    PyObject *mariadb_module = PyImport_ImportModule("mariadb");
    if (!mariadb_module) {
        PyErr_SetString(PyExc_ImportError, "Cannot import mariadb module. mariadb_c must be imported after mariadb.");
        goto error;
    }
    
    Mariadb_Error = PyObject_GetAttrString(mariadb_module, "Error");
    Mariadb_Warning = PyObject_GetAttrString(mariadb_module, "Warning");
    Mariadb_InterfaceError = PyObject_GetAttrString(mariadb_module, "InterfaceError");
    Mariadb_DatabaseError = PyObject_GetAttrString(mariadb_module, "DatabaseError");
    Mariadb_InternalError = PyObject_GetAttrString(mariadb_module, "InternalError");
    Mariadb_OperationalError = PyObject_GetAttrString(mariadb_module, "OperationalError");
    Mariadb_ProgrammingError = PyObject_GetAttrString(mariadb_module, "ProgrammingError");
    Mariadb_IntegrityError = PyObject_GetAttrString(mariadb_module, "IntegrityError");
    Mariadb_DataError = PyObject_GetAttrString(mariadb_module, "DataError");
    Mariadb_NotSupportedError = PyObject_GetAttrString(mariadb_module, "NotSupportedError");
    
    Py_DECREF(mariadb_module);
    
    // All exceptions MUST be successfully imported
    if (!Mariadb_Error || !Mariadb_Warning || !Mariadb_InterfaceError || 
        !Mariadb_DatabaseError || !Mariadb_InternalError || !Mariadb_OperationalError ||
        !Mariadb_ProgrammingError || !Mariadb_IntegrityError || !Mariadb_DataError ||
        !Mariadb_NotSupportedError) {
        PyErr_SetString(PyExc_ImportError, "Failed to import exceptions from mariadb module");
        goto error;
    }
    
    Py_INCREF(&MrdbConnection_Type);
    PyModule_AddObject(module, "connection", (PyObject *)&MrdbConnection_Type);
    PyModule_AddObject(module, "_have_asan", HAVE_ASAN);
    Py_INCREF(HAVE_ASAN);

    return module;
error:
    if (PyErr_Occurred())
    {
        return NULL;
    }
    PyErr_SetString(PyExc_ImportError, "Mariadb module initialization failed.");
    return NULL;
}
