/*****************************************************************************
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
 *****************************************************************************/

#include <mariadb_python.h>

int32_t numeric_field_types[]= {
    MYSQL_TYPE_DECIMAL, MYSQL_TYPE_TINY, MYSQL_TYPE_SHORT,
    MYSQL_TYPE_LONG, MYSQL_TYPE_INT24, MYSQL_TYPE_FLOAT,
    MYSQL_TYPE_DOUBLE, MYSQL_TYPE_LONGLONG, MYSQL_TYPE_YEAR,
    MYSQL_TYPE_NEWDECIMAL,
    -1 /* always last */
};

int32_t string_field_types[]= {
    MYSQL_TYPE_VARCHAR, MYSQL_TYPE_JSON, MYSQL_TYPE_STRING,
    MYSQL_TYPE_VAR_STRING, MYSQL_TYPE_ENUM,
    -1 /* always last */
};

int32_t binary_field_types[]= {
    MYSQL_TYPE_TINY_BLOB, MYSQL_TYPE_MEDIUM_BLOB,
    MYSQL_TYPE_BLOB, MYSQL_TYPE_LONG_BLOB, MYSQL_TYPE_GEOMETRY,
    -1 /* always last */
};

int32_t datetime_field_types[]= {
    MYSQL_TYPE_TIMESTAMP, MYSQL_TYPE_DATE, MYSQL_TYPE_TIME,
    MYSQL_TYPE_DATETIME,
    -1 /* always last */
};

int32_t rowid_field_types[]= {-1};

static void
Mariadb_DBAPIType_dealloc(Mariadb_DBAPIType *self);

static PyMethodDef
Mariadb_DBAPIType_Methods[] =
{
    {NULL} /* always last */
};

static struct PyMemberDef
Mariadb_DBAPIType_Members[] =
{
    {NULL}
};

static void
Mariadb_DBAPIType_dealloc(Mariadb_DBAPIType *self)
{
    Py_TYPE(self)->tp_free((PyObject*)self);
}

static PyObject *
Mariadb_DBAPIType_richcompare(Mariadb_DBAPIType *self,
                              PyObject *type,
                              int op)
{
    PyObject *res= NULL;

    if (Py_TYPE(type) != &PyLong_Type)
    {
        res= Py_NotImplemented;
    }
    else {
        switch(op) {
            case Py_EQ:
            case Py_NE:
                {
                    int32_t val, i= 0;
                    val= (uint32_t)PyLong_AsLong(type);

                    while (self->types[i] != -1) {
                        if (self->types[i] == val) {
                            res= (op == Py_EQ) ? Py_True : Py_False;
                            goto end;
                        }
                        i++;
                    }
                    res= (op == Py_EQ) ? Py_False : Py_True;
                }
                break;
            default:
                res= Py_NotImplemented;
                break;
        }
    }
end:
    Py_INCREF(res);
    return res;
}

static
int Mariadb_DBAPIType_initialize(Mariadb_DBAPIType *self,
                                 PyObject *args,
                                 PyObject *kwargs);

PyTypeObject Mariadb_DBAPIType_Type =
{
    PyVarObject_HEAD_INIT(NULL, 0)
    "dbapitype",
    sizeof(Mariadb_DBAPIType),
    0,
    (destructor)Mariadb_DBAPIType_dealloc, /* tp_dealloc */
    0, /*tp_print*/
    0, /* tp_getattr */
    0, /* tp_setattr */
    0, /*tp_compare*/
    0, /* tp_repr */

    /* Method suites for standard classes */

    0, /* (PyNumberMethods *) tp_as_number */
    0, /* (PySequenceMethods *) tp_as_sequence */
    0, /* (PyMappingMethods *) tp_as_mapping */

    /* More standard operations (here for binary compatibility) */

    0, /* (hashfunc) tp_hash */
    0, /* (ternaryfunc) tp_call */
    0, /* (reprfunc) tp_str */
    0, /* tp_getattro */
    0, /* tp_setattro */

    /* Functions to access object as input/output buffer */
    0, /* (PyBufferProcs *) tp_as_buffer */

    /* (tp_flags) Flags to define presence of optional/expanded features */
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_HAVE_GC | Py_TPFLAGS_BASETYPE,
    0, /* tp_doc Documentation string */

    /* call function for all accessible objects */
    (traverseproc)Mariadb_traverse,/* tp_traverse */

    /* delete references to contained objects */
    0, /* tp_clear */

    /* rich comparisons */
    (richcmpfunc)Mariadb_DBAPIType_richcompare,

    /* weak reference enabler */
    0, /* (long) tp_weaklistoffset */

    /* Iterators */
    0, /* (getiterfunc) tp_iter */
    0, /* (iternextfunc) tp_iternext */

    /* Attribute descriptor and subclassing stuff */
    (struct PyMethodDef *)Mariadb_DBAPIType_Methods, /* tp_methods */
    (struct PyMemberDef *)Mariadb_DBAPIType_Members, /* tp_members */
    0, /* (struct getsetlist *) tp_getset; */
    0, /* (struct _typeobject *) tp_base; */
    0, /* (PyObject *) tp_dict */
    0, /* (descrgetfunc) tp_descr_get */
    0, /* (descrsetfunc) tp_descr_set */
    0, /* (long) tp_dictoffset */
    (initproc)Mariadb_DBAPIType_initialize, /* (initproc)p_init */
    PyType_GenericAlloc, //NULL, /* tp_alloc */
    PyType_GenericNew, //NULL, /* tp_new */
    0, /* tp_free Low-level free-memory routine */ 
    0, /* (PyObject *) tp_bases */
    0, /* (PyObject *) tp_mro method resolution order */
    0, /* (PyObject *) tp_defined */
};

static int
Mariadb_DBAPIType_initialize(Mariadb_DBAPIType *self,
                             PyObject *args,
                             PyObject *kwargs)

{
    uint32_t group=0;

    if (!PyArg_ParseTuple(args, "I", &group))
    {
        return -1;
    }

    switch(group) {
        case DBAPI_NUMBER:
            self->types= numeric_field_types;
            return 0;
        case DBAPI_STRING:
            self->types= string_field_types;
            return 0;
        case DBAPI_BINARY:
            self->types= binary_field_types;
            return 0;
        case DBAPI_DATETIME:
            self->types= datetime_field_types;
            return 0;
        case DBAPI_ROWID:
            self->types= rowid_field_types;
            return 0;
        default:
            mariadb_throw_exception(NULL, Mariadb_InterfaceError, 0,
                    "Invalid DBAPI type");
            return -1;
    }
}
