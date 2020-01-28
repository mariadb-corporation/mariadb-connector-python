/******************************************************************************
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
 *****************************************************************************/

#include <mariadb_python.h>
#include <docs/pool.h>

static void
MrdbPool_dealloc(MrdbPool *self);

static PyObject 
*MrdbPool_addconnection(MrdbPool *self, PyObject *args);

static PyObject *
MrdbPool_setconfig(MrdbPool *self, PyObject *args, PyObject *kwargs);

static PyObject *
MrdbPool_poolsize(MrdbPool *self);

static PyObject *
MrdbPool_poolname(MrdbPool *self);

static int
MrdbPool_set_resetconnection(MrdbPool *self, PyObject *arg);

static PyObject *
MrdbPool_get_resetconnection(MrdbPool *self);

extern PyObject *cnx_pool;
uint16_t max_pool_size= MAX_POOL_SIZE;

static PyGetSetDef
MrdbPool_sets[]=
{
    {"pool_name", (getter)MrdbPool_poolname, NULL,
        pool_pool_name__doc__}, 
    {"pool_size", (getter)MrdbPool_poolsize, NULL,
        pool_pool_size__doc__}, 
    {"pool_reset_connection", (getter)MrdbPool_get_resetconnection, 
        (setter)MrdbPool_set_resetconnection, 
        pool_pool_reset_connection__doc__}, 
    {NULL}
};

static PyMethodDef
MrdbPool_Methods[] =
{

    {"add_connection", (PyCFunction)MrdbPool_addconnection,
        METH_VARARGS,
        pool_add_connection__doc__},
    {"get_connection", (PyCFunction)MrdbPool_getconnection,
        METH_NOARGS,
        pool_get_connection__doc__},
    {"set_config", (PyCFunction)MrdbPool_setconfig,
        METH_VARARGS | METH_KEYWORDS,
        pool_set_config__doc__ }, 
    {NULL} /* always last */
};

static struct PyMemberDef
MrdbPool_Members[] =
{
    {"max_size",
        T_SHORT,
        offsetof(MrdbPool, max_size),
        READONLY,
        pool_max_size__doc__},
    {NULL}
};

/*  Pool initialization

Keywords:
pool_name              name of the pool
pool_size              number of max. connections
reset_session     reset session after returning to the pool
idle_timeout           
acquire_timeout
 */
static int
MrdbPool_initialize(MrdbPool *self, PyObject *args, PyObject *kwargs)
{
    char *key_words[]= {"pool_name", "pool_size", "pool_reset_connection", NULL};
    PyObject *pool_kwargs= NULL;
    PyObject *conn_kwargs= NULL;
    char *pool_name= NULL;
    Py_ssize_t pool_name_length= 0;
    uint32_t pool_size= 5;
    uint8_t reset_session= 1;
    uint32_t idle_timeout= 1800;
    uint32_t i;
    PyObject *pn;
    PyObject *key, *value;
    Py_ssize_t pos = 0;

    if (!self)
    {
        return -1;
    }

    /* check if pool already exists */
    if (kwargs && (pn= PyDict_GetItemString(kwargs, "pool_name")))
    {
        if (PyDict_Contains(cnx_pool, pn))
        {
            mariadb_throw_exception(NULL, Mariadb_ProgrammingError, 0,
                    "Pool '%s' already exists", PyUnicode_AsUTF8(pn));
            return -1;
        }
    }
    else {
        mariadb_throw_exception(NULL, Mariadb_ProgrammingError, 0,
                "No pool name specified");
        return -1;
    }

    while(PyDict_Next(kwargs, &pos, &key, &value))
    {
        const char *utf8key= PyUnicode_AsUTF8(key);
        if (!strncmp(utf8key, "pool", 4))
        {
            if (!pool_kwargs)
            {
                pool_kwargs= PyDict_New();
            }
            PyDict_SetItemString(pool_kwargs, utf8key, value);
        }
        else {
            if (!conn_kwargs)
            {
                conn_kwargs= PyDict_New();
            }
            PyDict_SetItemString(conn_kwargs, utf8key, value);
        }
    }

    if (!PyArg_ParseTupleAndKeywords(args, pool_kwargs,
                "|s#ib:ConnectionPool", key_words, &pool_name,
                &pool_name_length, &pool_size, &reset_session))
    {
        return -1;
    }

    if (pool_size > max_pool_size)
    {
        mariadb_throw_exception(NULL, Mariadb_ProgrammingError, 0,
                "pool_size exceeds maximum of %d", MAX_POOL_SIZE);
        goto error;
    }

    pthread_mutex_init(&self->lock, NULL);
    self->pool_name= strdup(pool_name);
    self->pool_name_length= pool_name_length;
    self->pool_size= pool_size;
    self->max_size= max_pool_size;
    self->reset_session= reset_session;
    self->idle_timeout= idle_timeout;

    if (!(self->connection= (MrdbConnection **)PyMem_RawCalloc(self->pool_size, sizeof(PyObject *))))
    {
        mariadb_throw_exception(NULL, PyExc_MemoryError, 0, "can't allocate %ld bytes", 
                (unsigned long)self->pool_size * sizeof(PyObject*));
        goto error;
    }

    if ((self->configuration= conn_kwargs))
    {
        for (i=0; i < pool_size; i++)
        {
            if (!(self->connection[i]= 
                        (MrdbConnection *)MrdbConnection_connect(NULL, args, self->configuration)))
            {
                goto error;
            }
            clock_gettime(CLOCK_MONOTONIC_RAW, &self->connection[i]->last_used);
            Py_INCREF(self->connection[i]);
            self->connection[i]->pool= self;
        }
        self->connection_cnt= self->pool_size;
    }
    PyDict_SetItemString(cnx_pool, self->pool_name, (PyObject *)self);
    Py_DECREF(self);

    return 0;
error:
    if (self->connection)
    {
        for (i=0; i < self->pool_size; i++)
        {
            if (self->connection[i])
            {
                self->connection[i]->pool= 0;
                MrdbConnection_close(self->connection[i]);
            }
        }
    }
    MARIADB_FREE_MEM(self->connection);
    return -1;
}

static int
MrdbPool_traverse(MrdbPool *self,
                  visitproc visit,
                  void *arg)
{
    return 0;
}

PyTypeObject
MrdbPool_Type =
{
    PyVarObject_HEAD_INIT(NULL, 0)
        "mariadb.ConnectionPool",
    sizeof(MrdbPool),
    0,
    (destructor)MrdbPool_dealloc, /* tp_dealloc */
    0, /*tp_print*/
    0, /* tp_getattr */
    0, /* tp_setattr */
    0, /* PyAsyncMethods * */
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
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_HAVE_GC | Py_TPFLAGS_BASETYPE |
        Py_TPFLAGS_HAVE_FINALIZE,
    connection_pool__doc__, /* tp_doc Documentation string */

    /* call function for all accessible objects */
    (traverseproc)MrdbPool_traverse,/* tp_traverse */

    /* delete references to contained objects */
    0, /* tp_clear */

    /* rich comparisons */
    0, /* (richcmpfunc) tp_richcompare */

    /* weak reference enabler */
    0, /* (long) tp_weaklistoffset */

    /* Iterators */
    0, //(getiterfunc)MrdbCursor_iter,
    0, //(iternextfunc)MrdbCursor_iternext,

    /* Attribute descriptor and subclassing stuff */
    (struct PyMethodDef *)MrdbPool_Methods, /* tp_methods */
    (struct PyMemberDef *)MrdbPool_Members, /* tp_members */
    MrdbPool_sets,
    0, /* (struct _typeobject *) tp_base; */
    0, /* (PyObject *) tp_dict */
    0, /* (descrgetfunc) tp_descr_get */
    0, /* (descrsetfunc) tp_descr_set */
    0, /* (long) tp_dictoffset */
    (initproc)MrdbPool_initialize, /* tp_init */
    PyType_GenericAlloc, //NULL, /* tp_alloc */
    PyType_GenericNew, //NULL, /* tp_new */
    0, /* tp_free Low-level free-memory routine */ 
};

void
MrdbPool_dealloc(MrdbPool *self)
{
    uint32_t i;

    pthread_mutex_lock(&self->lock);

    if (self->pool_name)
    {
        if (PyDict_Contains(cnx_pool, PyUnicode_FromString(self->pool_name)))
        {
            PyDict_DelItemString(cnx_pool, self->pool_name);
        }
        MARIADB_FREE_MEM(self->pool_name);
        self->pool_name= NULL;
    }

    for (i=0; i < self->pool_size; i++)
    {
        if (self->connection[i])
        {
            self->connection[i]->pool= NULL;
            MrdbConnection_close(self->connection[i]);
            Py_DECREF(self->connection[i]);
            self->connection[i]= NULL;
        }
    }
    self->pool_size= 0;
    MARIADB_FREE_MEM(self->connection);
    self->connection= NULL;


    pthread_mutex_unlock(&self->lock);
    pthread_mutex_destroy(&self->lock);

    Py_TYPE(self)->tp_free((PyObject*)self);
}
/* }}} */

PyObject *
MrdbPool_add(PyObject *self,
             PyObject *args,
             PyObject *kwargs)
{
    MrdbPool *c;

    if (!(c= (MrdbPool *)PyType_GenericAlloc(&MrdbPool_Type, 1)))
    {
        return NULL;
    }

    if (MrdbPool_initialize(c, args, kwargs))
    {
        Py_DECREF(c);
        return NULL;
    }
    return (PyObject *) c;
}

PyObject *
MrdbPool_getconnection(MrdbPool *self)
{
    uint32_t i;
    MrdbConnection *conn= NULL;
    uint64_t tdiff= 0;
    struct timespec now;

    clock_gettime(CLOCK_MONOTONIC_RAW, &now);

    pthread_mutex_lock(&self->lock);

    for (i=0; i < self->pool_size; i++)
    {
        if (self->connection[i] && !self->connection[i]->inuse)
        {
            if (!mysql_ping(self->connection[i]->mysql))
            {
                uint64_t t= TIMEDIFF(now, self->connection[i]->last_used);
                if (t >= tdiff)
                {
                    conn= self->connection[i];
                    tdiff= t;
                }
            }
            else {
                self->connection[i]->pool= NULL;
                MrdbConnection_close(self->connection[i]);
                self->connection[i]= NULL;
            }
        }
    }
    if (conn)
    {
        conn->inuse= 1;
    }
    pthread_mutex_unlock(&self->lock);
    if (conn)
    {
        return (PyObject *)conn;
    }
    mariadb_throw_exception(NULL, Mariadb_PoolError, 0,
            "No more connections from pool '%s' available",
            self->pool_name);
    return NULL;
}

static PyObject 
*MrdbPool_setconfig(MrdbPool *self, PyObject *args, PyObject *kwargs)
{
    PyObject *key, *value;
    Py_ssize_t pos = 0;

    while(PyDict_Next(kwargs, &pos, &key, &value))
    {
        const char *utf8key= PyUnicode_AsUTF8(key);
        if (!strncmp(utf8key, "pool", 4))
        {
            mariadb_throw_exception(NULL, Mariadb_PoolError, 0,
            "Invalid parameter '%s'. Only DSN parameters are supported",
            utf8key);
            return NULL;
        }
    }
    self->configuration= kwargs;
    Py_RETURN_NONE;
}

static PyObject *
MrdbPool_addconnection(MrdbPool *self, PyObject *args)
{
    uint32_t i;
    MrdbConnection *conn= NULL;

    if (!self->configuration)
    {
        mariadb_throw_exception(NULL, Mariadb_PoolError, 0,
                "Couldn't get configuration for pool '%s'.",
                self->pool_name);
        return NULL;
    }

    if (!PyArg_ParseTuple(args, "|O!", &MrdbConnection_Type, &conn))
    {
        return NULL;
    }

    if (conn && conn->pool)
    {
        mariadb_throw_exception(NULL, Mariadb_PoolError, 0,
                "Connection is already in connection pool '%s'.",
                self->pool_name);
        return NULL;
    }

    pthread_mutex_lock(&self->lock);
    for (i=0; i < self->pool_size; i++)
    {
        if (!self->connection[i])
        {
            if (!conn &&
                (!(conn = (MrdbConnection *)MrdbConnection_connect(NULL, args,
                                                                   self->configuration))))
            {
                return NULL;
            }
            Py_INCREF(conn);
            self->connection[i]= conn; 
            self->connection[i]->inuse= 0;
            clock_gettime(CLOCK_MONOTONIC_RAW, &self->connection[i]->last_used);
            conn->pool= self;
            pthread_mutex_unlock(&self->lock);
            Py_RETURN_NONE;
        }
    }

    pthread_mutex_unlock(&self->lock);

    mariadb_throw_exception(NULL, Mariadb_PoolError, 0,
            "Couldn't add connection to pool '%s' (no free slot available).",
            self->pool_name);
    return NULL;
}

static PyObject *
MrdbPool_poolname(MrdbPool *self)
{
    return PyUnicode_FromString(self->pool_name);
}

static PyObject 
*MrdbPool_poolsize(MrdbPool *self)
{
    return PyLong_FromUnsignedLongLong(self->pool_size);
}

static PyObject *
MrdbPool_get_resetconnection(MrdbPool *self)
{
    if (self->reset_session)
    {
        Py_RETURN_TRUE;
    }
    Py_RETURN_FALSE;
}

static int
MrdbPool_set_resetconnection(MrdbPool *self, PyObject *arg)
{
    if (!arg || Py_TYPE(arg) != &PyBool_Type)
    {
        PyErr_SetString(PyExc_TypeError, "Argument must be boolean");
        return -1;
    }

    self->reset_session= PyObject_IsTrue(arg);
    return 0;
}
