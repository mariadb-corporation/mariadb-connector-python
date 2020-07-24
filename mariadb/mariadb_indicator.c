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
 *****************************************************************************/

#include <mariadb_python.h>

static void
MrdbIndicator_dealloc(MrdbIndicator *self);

/* todo: move documentation to include/docs */
static char MrdbIndicator_documentation[] =
"Returns a MariaDB indicator object";

static PyMethodDef
MrdbIndicator_Methods[] =
{
    {NULL} /* always last */
};

static struct PyMemberDef
MrdbIndicator_Members[] =
{
    {NULL} /* always last */
};

static void
MrdbIndicator_dealloc(MrdbIndicator *self)
{
    Py_TYPE(self)->tp_free((PyObject*)self);
}

static int
MrdbIndicator_initialize(MrdbIndicator *self,
                         PyObject *args,
                         PyObject *kwargs)
{
    int indicator;
    PyObject *obj;

    if (!PyArg_ParseTuple(args, "O!", &PyLong_Type, &obj))
    {
        return -1;
    }

    indicator= PyLong_AsLong(obj);

    /* check if indicator is in range */
    if (indicator < STMT_INDICATOR_NULL ||
            indicator > STMT_INDICATOR_IGNORE_ROW)
    {
        mariadb_throw_exception(NULL, Mariadb_InterfaceError, 0,
                "Invalid indicator value");
        return -1;
    }
    self->indicator= indicator;
    return 0;
}

static int
MrdbIndicator_traverse(MrdbIndicator *self,
                       visitproc visit,
                       void *arg)
{
    return 0;
}

PyTypeObject
MrdbIndicator_Type =
{
    PyVarObject_HEAD_INIT(NULL, 0)
        "mariadb.indicator",
    sizeof(MrdbIndicator),
    0,
    (destructor)MrdbIndicator_dealloc, /* tp_dealloc */
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
    MrdbIndicator_documentation, /* tp_doc Documentation string */

    /* call function for all accessible objects */
    (traverseproc)MrdbIndicator_traverse,/* tp_traverse */

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
    (struct PyMethodDef *)MrdbIndicator_Methods, /* tp_methods */
    (struct PyMemberDef *)MrdbIndicator_Members, /* tp_members */
    0, /* (struct getsetlist *) tp_getset; */
    0, /* (struct _typeobject *) tp_base; */
    0, /* (PyObject *) tp_dict */
    0, /* (descrgetfunc) tp_descr_get */
    0, /* (descrsetfunc) tp_descr_set */
    0, /* (long) tp_dictoffset */
    (initproc)MrdbIndicator_initialize,/* tp_init */
    PyType_GenericAlloc, //NULL, /* tp_alloc */
    PyType_GenericNew, //NULL, /* tp_new */
    NULL, /* tp_free Low-level free-memory routine */ 
    0, /* (PyObject *) tp_bases */
    0, /* (PyObject *) tp_mro method resolution order */
    0, /* (PyObject *) tp_defined */
};

PyObject *
MrdbIndicator_Object(uint32_t type)
{
    PyObject *types= Py_BuildValue("(I)", (uint32_t)type);
    PyObject *number= PyObject_CallObject((PyObject *)&MrdbIndicator_Type,
            types);
    Py_DECREF(types);
    return number;
}

long
MrdbIndicator_AsLong(PyObject *v)
{
    if (!MrdbIndicator_Check(v))
    {
        return -1;
    }
    return (long)((MrdbIndicator *)v)->indicator;
}
