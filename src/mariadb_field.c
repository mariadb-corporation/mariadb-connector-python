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
 ******************************************************************************/

#include <mariadb_python.h>

static void
Mariadb_Fieldinfo_dealloc(Mariadb_Fieldinfo *self);

/* todo: move information into docs subdirectory */
static char mariadb_fieldinfo_documentation[] =
"Returns a MariaDB field information object";

static PyObject *
Mariadb_Fieldinfo_gettype(Mariadb_Fieldinfo *self, PyObject *args);

static PyObject *
Mariadb_Fieldinfo_getflag(Mariadb_Fieldinfo *self, PyObject *args);

static PyMethodDef
Mariadb_Fieldinfo_Methods[] =
{
    {"type", (PyCFunction)Mariadb_Fieldinfo_gettype,
        METH_VARARGS,
        "Returns type information for the given field"},
    {"flag", (PyCFunction)Mariadb_Fieldinfo_getflag,
        METH_VARARGS,
        "Returns flag information for the given field"},
    {NULL} /* always last */
};

static struct PyMemberDef
Mariadb_Fieldinfo_Members[] =
{
    {NULL}
};

static void
Mariadb_Fieldinfo_dealloc(Mariadb_Fieldinfo *self)
{
    Py_TYPE(self)->tp_free((PyObject*)self);
}

static int
Mariadb_Fieldinfo_traverse(Mariadb_Fieldinfo *self,
                           visitproc visit,
                           void *arg)
{
    return 0;
}

PyTypeObject Mariadb_Fieldinfo_Type =
{
    PyVarObject_HEAD_INIT(NULL, 0)
        "mariadb.fieldinfo",
    sizeof(Mariadb_Fieldinfo),
    0,
    (destructor)Mariadb_Fieldinfo_dealloc, /* tp_dealloc */
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
    mariadb_fieldinfo_documentation, /* tp_doc Documentation string */

    /* call function for all accessible objects */
    (traverseproc)Mariadb_Fieldinfo_traverse,/* tp_traverse */

    /* delete references to contained objects */
    0, /* tp_clear */

    /* rich comparisons */
    0, /* (richcmpfunc) tp_richcompare */

    /* weak reference enabler */
    0, /* (long) tp_weaklistoffset */

    /* Iterators */
    0, /* (getiterfunc) tp_iter */
    0, /* (iternextfunc) tp_iternext */

    /* Attribute descriptor and subclassing stuff */
    (struct PyMethodDef *)Mariadb_Fieldinfo_Methods, /* tp_methods */
    (struct PyMemberDef *)Mariadb_Fieldinfo_Members, /* tp_members */
    0, /* (struct getsetlist *) tp_getset; */
    0, /* (struct _typeobject *) tp_base; */
    0, /* (PyObject *) tp_dict */
    0, /* (descrgetfunc) tp_descr_get */
    0, /* (descrsetfunc) tp_descr_set */
    0, /* (long) tp_dictoffset */
    0, /* (initproc)Mariadb_Fieldinfo_initialize, tp_init */
    PyType_GenericAlloc, //NULL, /* tp_alloc */
    PyType_GenericNew, //NULL, /* tp_new */
    NULL, /* tp_free Low-level free-memory routine */ 
    0, /* (PyObject *) tp_bases */
    0, /* (PyObject *) tp_mro method resolution order */
    0, /* (PyObject *) tp_defined */
};

struct st_type_mapping {
    enum enum_field_types type;
    const char *name;
} type_code[]= {
    {MYSQL_TYPE_DECIMAL, "DECIMAL"},
    {MYSQL_TYPE_TINY, "TINY"},
    {MYSQL_TYPE_SHORT, "SHORT"},
    {MYSQL_TYPE_LONG, "LONG"},
    {MYSQL_TYPE_FLOAT, "FLOAT"},
    {MYSQL_TYPE_DOUBLE, "DOUBLE"},
    {MYSQL_TYPE_NULL, "NULL"},
    {MYSQL_TYPE_TIMESTAMP, "TIMESTAMP"},
    {MYSQL_TYPE_LONGLONG, "LONGLONG"},
    {MYSQL_TYPE_INT24, "INT24"},
    {MYSQL_TYPE_DATE, "DATE"},
    {MYSQL_TYPE_TIME, "TIME"},
    {MYSQL_TYPE_DATETIME, "DATETIME"},
    {MYSQL_TYPE_YEAR, "YEAR"},
    {MYSQL_TYPE_NEWDATE, "NEWDATE"},
    {MYSQL_TYPE_VARCHAR, "VARCHAR"},
    {MYSQL_TYPE_BIT, "BIT"},
    {MYSQL_TYPE_JSON, "JSON"},
    {MYSQL_TYPE_NEWDECIMAL, "NEWDECIMAL"},
    {MYSQL_TYPE_ENUM, "ENUM"},
    {MYSQL_TYPE_SET, "SET"},
    {MYSQL_TYPE_TINY_BLOB, "BLOB"},
    {MYSQL_TYPE_MEDIUM_BLOB, "MEDIUM_BLOB"},
    {MYSQL_TYPE_LONG_BLOB, "LONG_BLOB"},
    {MYSQL_TYPE_BLOB, "BLOB"},
    {MYSQL_TYPE_VAR_STRING, "VAR_STRING"},
    {MYSQL_TYPE_STRING, "STRING"},
    {MYSQL_TYPE_GEOMETRY, "GEOMETRY"},
    {0, NULL}
};

static PyObject *Mariadb_Fieldinfo_gettype(Mariadb_Fieldinfo *self,
        PyObject *args)
{
    uint16_t i=0;
    enum enum_field_types field_type;
    PyObject *data= NULL;
    PyObject *type= NULL;

    if (!PyArg_ParseTuple(args, "O!", &PyTuple_Type, &data))
    {
        return NULL;
    }

    if (PyTuple_Size(data) != 8)
    {
        mariadb_throw_exception(NULL, Mariadb_InterfaceError, 0,
                "Parameter isn't a (valid) description sequence");
        return NULL;
    }

    type= PyTuple_GetItem(data, 1);

    if (Py_TYPE(type) != &PyLong_Type)
    {
        mariadb_throw_exception(NULL, Mariadb_InterfaceError, 0,
                "Parameter isn't a (valid) description sequence");
        return NULL;
    }

    field_type= PyLong_AsLong(type);

    while(type_code[i].name)
    {
        if (type_code[i].type == field_type)
        {
            return PyUnicode_FromString(type_code[i].name);
        }
        i++;
    }
    return PyUnicode_FromString("UNKNOWN");
}

struct st_flag {
    uint32_t flag;
    const char *name;
} flag_name[]= {
    {NOT_NULL_FLAG, "NOT_NULL"},
    {PRI_KEY_FLAG, "PRIMARY_KEY"},
    {UNIQUE_KEY_FLAG, "UNIQUE_KEY"},
    {MULTIPLE_KEY_FLAG, "PART_KEY"},
    {BLOB_FLAG, "BLOB"},
    {UNSIGNED_FLAG, "UNSIGNED"},
    {ZEROFILL_FLAG, "ZEROFILL"},
    {BINARY_FLAG, "BINARY"},
    {ENUM_FLAG, "NUMERIC"},
    {AUTO_INCREMENT_FLAG, "AUTO_INCREMENT"},
    {TIMESTAMP_FLAG, "TIMESTAMP"},
    {SET_FLAG, "SET"},
    {NO_DEFAULT_VALUE_FLAG, "NO_DEFAULT"},
    {ON_UPDATE_NOW_FLAG, "UPDATE_TIMESTAMP"},
    {NUM_FLAG, "NUMERIC"},
    {0, NULL}
};

static PyObject *
Mariadb_Fieldinfo_getflag(Mariadb_Fieldinfo *self, PyObject *args)
{
    uint16_t i=0;
    unsigned long flag_val= 0;
    PyObject *data= NULL;
    PyObject *flag= NULL;
    char str_flag[512]= {0};

    if (!PyArg_ParseTuple(args, "O!", &PyTuple_Type, &data))
    {
        return NULL;
    }

    if (PyTuple_Size(data) != 8)
    {
        mariadb_throw_exception(NULL, Mariadb_InterfaceError, 0,
                "Parameter isn't a (valid) description sequence");
        return NULL;
    }

    flag= PyTuple_GetItem(data, 7);

    if (Py_TYPE(flag) != &PyLong_Type)
    {
        mariadb_throw_exception(NULL, Mariadb_InterfaceError, 0,
                "Parameter isn't a (valid) description sequence");
        return NULL;
    }
    flag_val= PyLong_AsUnsignedLong(flag);

    if (!flag_val)
    {
        goto end;
    }

    while(flag_name[i].name)
    {
        if (flag_val & flag_name[i].flag)
        {
            if (!str_flag[0])
            {
                strcat(str_flag, flag_name[i].name);
            }
            else {
                strcat(str_flag, " | ");
                strcat(str_flag, flag_name[i].name);
            }
        }
        i++;
    }
end:
    return PyUnicode_FromString(str_flag);
}
