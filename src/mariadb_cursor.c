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
 ****************************************************************************/

#include <mariadb_python.h>
#include <docs/cursor.h>

static void
MrdbCursor_dealloc(MrdbCursor *self);

static PyObject *
MrdbCursor_close(MrdbCursor *self);

static PyObject *
MrdbCursor_execute(MrdbCursor *self,
                   PyObject *args,
                   PyObject *kwargs);

static PyObject *
MrdbCursor_nextset(MrdbCursor *self);

static PyObject *
MrdbCursor_executemany(MrdbCursor *self,
                       PyObject *args);

static PyObject *
MrdbCursor_description(MrdbCursor *self);

static PyObject *
MrdbCursor_fetchall(MrdbCursor *self);

static PyObject *
MrdbCursor_fetchone(MrdbCursor *self);

static PyObject
*MrdbCursor_fetchmany(MrdbCursor *self,
                      PyObject *args,
                      PyObject *kwargs);

static PyObject *
MrdbCursor_scroll(MrdbCursor *self,
                  PyObject *args,
                  PyObject *kwargs);

static PyObject *
MrdbCursor_callproc(MrdbCursor *self,
                    PyObject *args);

static PyObject *
MrdbCursor_fieldcount(MrdbCursor *self);

void
field_fetch_fromtext(MrdbCursor *self, char *data, unsigned int column);

void
field_fetch_callback(void *data, unsigned int column, unsigned char **row);
static PyObject *mariadb_get_sequence_or_tuple(MrdbCursor *self);
static PyObject * MrdbCursor_iter(PyObject *self);
static PyObject * MrdbCursor_iternext(PyObject *self);
static PyObject *MrdbCursor_enter(MrdbCursor *self, PyObject *args __attribute__((unused)));
static PyObject *MrdbCursor_exit(MrdbCursor *self, PyObject *args __attribute__((unused)));

/* todo: write more documentation, this is just a placeholder */
static char mariadb_cursor_documentation[] =
"Returns a MariaDB cursor object";

#define CURSOR_SET_STATEMENT(a,s,l)\
    MARIADB_FREE_MEM((a)->statement);\
(a)->statement= PyMem_RawMalloc((l)+ 1);\
strncpy((a)->statement, (s), (l));\
(a)->statement_len= (unsigned long)(l);\
(a)->statement[(l)]= 0;

#define CURSOR_FIELD_COUNT(a)\
    ((a)->is_text ? mysql_field_count((a)->connection->mysql) : (a)->stmt ? mysql_stmt_field_count((a)->stmt) : 0)

#define CURSOR_WARNING_COUNT(a)\
    (((a)->is_text) ? (long)mysql_warning_count((a)->connection->mysql) : ((a)->stmt) ? (long)mysql_stmt_warning_count((a)->stmt) : 0L)

#define CURSOR_AFFECTED_ROWS(a)\
    (int64_t)((a)->is_text ? mysql_affected_rows((a)->connection->mysql) : (a)->stmt ? mysql_stmt_affected_rows((a)->stmt) : 0)

#define CURSOR_INSERT_ID(a)\
    ((a)->is_text ? mysql_insert_id((a)->connection->mysql) : (a)->stmt ? mysql_stmt_insert_id((a)->stmt) : 0)

#define CURSOR_NUM_ROWS(a)\
    ((a)->is_text ? mysql_num_rows((a)->result) : (a)->stmt ? mysql_stmt_num_rows((a)->stmt) : 0)

#define MARIADB_SET_SEQUENCE_OR_TUPLE_ITEM(self, row, column)\
if ((self)->is_named_tuple)\
{\
    PyStructSequence_SET_ITEM((row), (column),\
     (self)->values[(column)]);\
}\
else {\
    PyTuple_SET_ITEM((row), (column), (self)->values[(column)]);\
}


static char *mariadb_named_tuple_name= "Row";
static char *mariadb_named_tuple_desc= "Named tupled row";
static PyObject *Mariadb_no_operation(MrdbCursor *,
        PyObject *);
static PyObject *Mariadb_row_count(MrdbCursor *self);
static PyObject *Mariadb_row_number(MrdbCursor *self);
static PyObject *MrdbCursor_warnings(MrdbCursor *self);
static PyObject *MrdbCursor_getbuffered(MrdbCursor *self);
static int MrdbCursor_setbuffered(MrdbCursor *self, PyObject *arg);
static PyObject *MrdbCursor_lastrowid(MrdbCursor *self);
static PyObject *MrdbCursor_closed(MrdbCursor *self);
static PyObject *MrdbCursor_sp_outparams(MrdbCursor *self);


static PyGetSetDef MrdbCursor_sets[]=
{
    {"lastrowid", (getter)MrdbCursor_lastrowid, NULL,
        cursor_lastrowid__doc__, NULL},
    {"description", (getter)MrdbCursor_description, NULL,
        cursor_description__doc__, NULL},
    {"rowcount", (getter)Mariadb_row_count, NULL,
        cursor_rowcount__doc__, NULL},
    {"warnings", (getter)MrdbCursor_warnings, NULL,
        cursor_warnings__doc__, NULL},
    {"closed", (getter)MrdbCursor_closed, NULL,
        cursor_closed__doc__, NULL},
    {"buffered", (getter)MrdbCursor_getbuffered, (setter)MrdbCursor_setbuffered,
        cursor_buffered__doc__, NULL},
    {"rownumber", (getter)Mariadb_row_number, NULL,
        cursor_rownumber__doc__, NULL},
    {"sp_outparams", (getter)MrdbCursor_sp_outparams, NULL,
        cursor_sp_outparam__doc__, NULL},
    {NULL}
};

static PyMethodDef MrdbCursor_Methods[] =
{
    /* PEP-249 methods */
    {"callproc", (PyCFunction)MrdbCursor_callproc,
        METH_VARARGS,
        cursor_callproc__doc__},
    {"close", (PyCFunction)MrdbCursor_close,
        METH_NOARGS,
        cursor_close__doc__},
    {"execute", (PyCFunction)MrdbCursor_execute,
        METH_VARARGS | METH_KEYWORDS,
        cursor_execute__doc__,},
    {"executemany", (PyCFunction)MrdbCursor_executemany,
        METH_VARARGS,
        cursor_executemany__doc__ }, 
    {"fetchall", (PyCFunction)MrdbCursor_fetchall,
        METH_NOARGS,
        cursor_fetchall__doc__},
    {"fetchone", (PyCFunction)MrdbCursor_fetchone,
        METH_NOARGS,
        cursor_fetchone__doc__,},
    {"fetchmany", (PyCFunction)MrdbCursor_fetchmany,
        METH_VARARGS | METH_KEYWORDS,
        cursor_fetchmany__doc__},
    {"fieldcount", (PyCFunction)MrdbCursor_fieldcount,
        METH_NOARGS,
        cursor_field_count__doc__},
    {"nextset", (PyCFunction)MrdbCursor_nextset,
        METH_NOARGS,
        cursor_nextset__doc__},
    {"setinputsizes", (PyCFunction)Mariadb_no_operation,
        METH_VARARGS,
        cursor_setinputsizes__doc__},
    {"setoutputsize", (PyCFunction)Mariadb_no_operation,
        METH_VARARGS,
        cursor_setoutputsize__doc__},
    {"callproc", (PyCFunction)Mariadb_no_operation,
        METH_VARARGS,
        cursor_callproc__doc__},
    {"next", (PyCFunction)MrdbCursor_fetchone,
        METH_NOARGS,
        cursor_next__doc__},
    {"scroll", (PyCFunction)MrdbCursor_scroll,
        METH_VARARGS | METH_KEYWORDS,
        cursor_scroll__doc__},
    {"__enter__", (PyCFunction)MrdbCursor_enter,
        METH_NOARGS, cursor_enter__doc__},
    {"__exit__", (PyCFunction)MrdbCursor_exit,
        METH_VARARGS, cursor_exit__doc__},
    {NULL} /* always last */
};

static struct PyMemberDef MrdbCursor_Members[] =
{
    {"connection",
        T_OBJECT,
        offsetof(MrdbCursor, connection),
        READONLY,
        cursor_connection__doc__},
    {"statement",
        T_STRING,
        offsetof(MrdbCursor, statement),
        READONLY,
        cursor_statement__doc__},
    {"buffered",
        T_BYTE,
        offsetof(MrdbCursor, is_buffered),
        0,
        cursor_buffered__doc__},
    {"arraysize",
        T_LONG,
        offsetof(MrdbCursor, row_array_size),
        0,
        cursor_arraysize__doc__},
    {NULL}
};

/* {{{ MrdbCursor_initialize
   Cursor initialization

   Optional keywprds:
   named_tuple (Boolean): return rows as named tuple instead of tuple
prefetch_size:         Prefetch size for readonly cursors
cursor_type:           Type of cursor: CURSOR_TYPE_READONLY or CURSOR_TYPE_NONE (default)
buffered:              buffered or unbuffered result sets
 */
static int MrdbCursor_initialize(MrdbCursor *self, PyObject *args,
        PyObject *kwargs)
{
    char *key_words[]= {"", "named_tuple", "prefetch_size", "cursor_type", 
        "buffered", "prepared", NULL};
    PyObject *connection;
    uint8_t is_named_tuple= 0;
    unsigned long cursor_type= 0,
                  prefetch_rows= 0;
    uint8_t is_buffered= 0;
    uint8_t is_prepared= 0;

    if (!self)
        return -1;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs,
                "O!|bkkbb", key_words, &MrdbConnection_Type, &connection,
                &is_named_tuple, &prefetch_rows, &cursor_type, &is_buffered,
                &is_prepared))
        return -1;

    if (!((MrdbConnection *)connection)->mysql)
    {
        mariadb_throw_exception(NULL, Mariadb_ProgrammingError, 0,
                "Connection isn't valid anymore");
        return -1;
    }

    if (cursor_type != CURSOR_TYPE_READ_ONLY &&
            cursor_type != CURSOR_TYPE_NO_CURSOR)
    {
        mariadb_throw_exception(NULL, Mariadb_DataError, 0,
                "Invalid value %ld for cursor_type", cursor_type);
        return -1;
    }

    Py_INCREF(connection);
    self->connection= (MrdbConnection *)connection;
    self->is_buffered= is_buffered ? is_buffered : self->connection->is_buffered;

    self->is_prepared= is_prepared;
    self->is_text= 0;

    if (!(self->stmt= mysql_stmt_init(self->connection->mysql)))
    {
        mariadb_throw_exception(self->connection->mysql, NULL, 0, NULL);
        return -1;
    }

    self->cursor_type= cursor_type;
    self->prefetch_rows= prefetch_rows;
    self->is_named_tuple= is_named_tuple;
    self->row_array_size= 1;

    if (self->cursor_type || self->prefetch_rows)
    {
        if (!(self->stmt = mysql_stmt_init(self->connection->mysql)))
        {
            mariadb_throw_exception(self->connection->mysql, Mariadb_OperationalError, 0, NULL);
            return -1;
        }
    }
    else
        return 0;

    mysql_stmt_attr_set(self->stmt, STMT_ATTR_CURSOR_TYPE, &self->cursor_type);
    mysql_stmt_attr_set(self->stmt, STMT_ATTR_PREFETCH_ROWS, &self->prefetch_rows);
    return 0;
}
/* }}} */

static int MrdbCursor_traverse(
        MrdbCursor *self,
        visitproc visit,
        void *arg)
{
    return 0;
}

PyTypeObject MrdbCursor_Type =
{
    PyVarObject_HEAD_INIT(NULL, 0)
        "mariadb.connection.cursor",
    sizeof(MrdbCursor),
    0,
    (destructor)MrdbCursor_dealloc, /* tp_dealloc */
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
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_HAVE_GC | Py_TPFLAGS_BASETYPE,
    mariadb_cursor_documentation, /* tp_doc Documentation string */

    /* call function for all accessible objects */
    (traverseproc)MrdbCursor_traverse,/* tp_traverse */

    /* delete references to contained objects */
    0, /* tp_clear */

    /* rich comparisons */
    0, /* (richcmpfunc) tp_richcompare */

    /* weak reference enabler */
    0, /* (long) tp_weaklistoffset */

    /* Iterators */
    (getiterfunc)MrdbCursor_iter,
    (iternextfunc)MrdbCursor_iternext,

    /* Attribute descriptor and subclassing stuff */
    (struct PyMethodDef *)MrdbCursor_Methods, /* tp_methods */
    (struct PyMemberDef *)MrdbCursor_Members, /* tp_members */
    MrdbCursor_sets,
    0, /* (struct _typeobject *) tp_base; */
    0, /* (PyObject *) tp_dict */
    0, /* (descrgetfunc) tp_descr_get */
    0, /* (descrsetfunc) tp_descr_set */
    0, /* (long) tp_dictoffset */
    (initproc)MrdbCursor_initialize, /* tp_init */
    PyType_GenericAlloc, //NULL, /* tp_alloc */
    PyType_GenericNew, //NULL, /* tp_new */
    NULL, /* tp_free Low-level free-memory routine */ 
    0, /* (PyObject *) tp_bases */
    0, /* (PyObject *) tp_mro method resolution order */
    0, /* (PyObject *) tp_defined */
};

/* {{{ Mariadb_no_operation
   This function is a stub and just returns Py_None
 */
static PyObject *Mariadb_no_operation(MrdbCursor *self,
        PyObject *args)
{
    Py_INCREF(Py_None);
    return Py_None;
}
/* }}} */

/* {{{ MrdbCursor_clear
   Resets statement attributes  and frees
   associated memory
 */
    static
void MrdbCursor_clear(MrdbCursor *self, uint8_t new_stmt)
{

    if (!self->is_text && self->stmt) {
        mysql_stmt_free_result(self->stmt);

        /* CONPY-52: avoid possible double free */
        self->result= NULL;

        while (!mysql_stmt_next_result(self->stmt))
            mysql_stmt_free_result(self->stmt);

        if (new_stmt)
        {
          mysql_stmt_close(self->stmt);
          self->stmt= mysql_stmt_init(self->connection->mysql);
        }
        else {
            uint32_t val= 0;

            mysql_stmt_attr_set(self->stmt, STMT_ATTR_CB_USER_DATA, 0);
            mysql_stmt_attr_set(self->stmt, STMT_ATTR_CB_PARAM, 0);
            mysql_stmt_attr_set(self->stmt, STMT_ATTR_CB_RESULT, 0);
            mysql_stmt_attr_set(self->stmt, STMT_ATTR_ARRAY_SIZE, &val);
            mysql_stmt_attr_set(self->stmt, STMT_ATTR_PREBIND_PARAMS, &val);
        }

    }

    if (self->is_text)
    {
        if (self->result)
        { 
            mysql_free_result(self->result);
            self->result= 0;
            self->is_text= 0;
        }
        /* clear also pending result sets */
        if (self->connection->mysql)
            while (!mysql_next_result(self->connection->mysql));
    }

    MARIADB_FREE_MEM(self->sequence_fields);
    self->fields= NULL;
    self->row_count= 0;
    self->affected_rows= 0;
    self->param_count= 0;
    MARIADB_FREE_MEM(self->values);
    MARIADB_FREE_MEM(self->bind);
    MARIADB_FREE_MEM(self->statement);
    MARIADB_FREE_MEM(self->value);
    MARIADB_FREE_MEM(self->params);

}
/* }}} */

/* {{{ ma_cursor_close 
   closes the statement handle of current cursor. After call to
   cursor_close the cursor can't be reused anymore
 */
    static
void ma_cursor_close(MrdbCursor *self)
{
    if (!self->is_text && self->stmt)
    {
        /* Todo: check if all the cursor stuff is deleted (when using prepared
           statements this should be handled in mysql_stmt_close) */
        Py_BEGIN_ALLOW_THREADS
        mysql_stmt_close(self->stmt);
        Py_END_ALLOW_THREADS
        self->stmt= NULL;
    }
    MrdbCursor_clear(self, 0);
    if (self->parser)
    {
        MrdbParser_end(self->parser);
        self->parser= NULL;
    }
    self->is_closed= 1;
}

    static
PyObject * MrdbCursor_close(MrdbCursor *self)
{
    ma_cursor_close(self);
    self->is_closed= 1;
    Py_INCREF(Py_None);
    return Py_None;
}
/* }}} */

/*{{{ MrDBCursor_dealloc */
void MrdbCursor_dealloc(MrdbCursor *self)
{
    ma_cursor_close(self);
    Py_TYPE(self)->tp_free((PyObject*)self);
}
/* }}} */

static int Mrdb_GetFieldInfo(MrdbCursor *self)
{
    self->row_number= 0;
    self->row_count= CURSOR_AFFECTED_ROWS(self);

    if (self->field_count)
    {
        if (self->is_text)
        {
            self->result= (self->is_buffered) ? mysql_store_result(self->connection->mysql) :
                mysql_use_result(self->connection->mysql);
            if (!self->result)
            {
                mariadb_throw_exception(self->connection->mysql, NULL, 0, NULL);
                return 1;
            }
        }
        else if (self->is_buffered)
        {
            if (mysql_stmt_store_result(self->stmt))
            {
                mariadb_throw_exception(self->stmt, NULL, 1, NULL);
                return 1;
            }
        }

        self->affected_rows= CURSOR_AFFECTED_ROWS(self);

        self->fields= (self->is_text) ? mysql_fetch_fields(self->result) :
            mariadb_stmt_fetch_fields(self->stmt);

        if (self->is_named_tuple) {
            unsigned int i;
            if (!(self->sequence_fields= (PyStructSequence_Field *)
                        PyMem_RawCalloc(self->field_count + 1,
                            sizeof(PyStructSequence_Field))))
                return 1;
            self->sequence_desc.name= mariadb_named_tuple_name;
            self->sequence_desc.doc= mariadb_named_tuple_desc;
            self->sequence_desc.fields= self->sequence_fields;
            self->sequence_desc.n_in_sequence= self->field_count;


            for (i=0; i < self->field_count; i++)
            {
                self->sequence_fields[i].name= self->fields[i].name;
            }
            self->sequence_type= PyMem_RawCalloc(1,sizeof(PyTypeObject));
            PyStructSequence_InitType(self->sequence_type, &self->sequence_desc);
        }
    }
    return 0;
}

static int MrdbCursor_InitResultSet(MrdbCursor *self)
{
    self->field_count= CURSOR_FIELD_COUNT(self);

    MARIADB_FREE_MEM(self->sequence_fields);
    MARIADB_FREE_MEM(self->values);

    if (self->result)
    {
        mysql_free_result(self->result);
        self->result= NULL;
    }

    if (Mrdb_GetFieldInfo(self))
        return 1;

    if (!(self->values= (PyObject**)PyMem_RawCalloc(self->field_count, sizeof(PyObject *))))
        return 1;
    if (!self->is_text)
        mysql_stmt_attr_set(self->stmt, STMT_ATTR_CB_RESULT, field_fetch_callback);
    return 0;
}

/* {{{ MrdbCursor_execute
   PEP-249 execute() method
 */
static
PyObject *MrdbCursor_execute(MrdbCursor *self,
        PyObject *args,
        PyObject *kwargs)
{
    PyObject *Data= NULL;
    const char *statement= NULL;
    Py_ssize_t statement_len= 0;
    int rc= 0;
    int8_t is_buffered= -1;
    static char *key_words[]= {"", "", "buffered", NULL};
    char errmsg[128];

    MARIADB_CHECK_STMT(self);
    if (PyErr_Occurred())
        return NULL;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs,
                "s#|Ob", key_words, &statement, &statement_len, &Data, &is_buffered))
        return NULL;

    /* If we don't have a prepared cursor, we need to end/free parser */
    if (!self->is_prepared && self->parser)
    {
        MrdbParser_end(self->parser);
        self->parser= NULL;
    }

    if (is_buffered != -1)
      self->is_buffered= is_buffered;

    /* if there are no parameters specified, we execute the statement in text protocol */
    if (!Data && !self->cursor_type)
    {
        /* in case statement was executed before, we need to clear, since we don't use 
           binary protocol */
        MrdbParser_end(self->parser);
        self->parser= NULL;
        MrdbCursor_clear(self, 0);
        Py_BEGIN_ALLOW_THREADS;
        rc= mysql_real_query(self->connection->mysql, statement, (unsigned long)statement_len);
        Py_END_ALLOW_THREADS;
        if (rc)
        {
            mariadb_throw_exception(self->connection->mysql, NULL, 0, NULL);
            goto error;
        }
        self->is_text= 1;
        CURSOR_SET_STATEMENT(self, statement, statement_len);
    }
    else
    {
        uint8_t do_prepare= 1;

        self->is_text= 0;

        if (self->is_prepared && self->statement)
            do_prepare= 0;

        /* if cursor type is not prepared, we need to clear the cursor first */
        if (!self->is_prepared && self->statement)
        {
            uint8_t new_stmt= 1;
            if (!strcmp(self->statement, statement))
              new_stmt= 0;
            MrdbCursor_clear(self, new_stmt);
            MrdbParser_end(self->parser);
            self->parser= NULL;
        }

        if (!self->parser)
        {
            self->parser= MrdbParser_init(statement, statement_len);
            if (MrdbParser_parse(self->parser, 0, errmsg, 128))
            {
                PyErr_SetString(Mariadb_ProgrammingError, errmsg);
                goto error;
            }
            CURSOR_SET_STATEMENT(self, statement, statement_len);
        }

        if (Data)
        {
            if (self->parser->paramstyle == PYFORMAT)
            {
                if (Py_TYPE(Data) != &PyDict_Type)
                {
                    PyErr_SetString(PyExc_TypeError, "argument 2 must be dict");
                    goto error;
                }
            }
            else if (Py_TYPE(Data) != &PyTuple_Type && Py_TYPE(Data) != &PyList_Type)
            {
                PyErr_SetString(PyExc_TypeError, "argument 2 must be tuple!");
                goto error;
            }
            self->array_size= 0;
            self->data= Data;
            if (mariadb_check_execute_parameters(self, Data))
                goto error;

            self->data= Data;

            /* Load values */
            if (mariadb_param_update(self, self->params, 0))
                goto error;
        }
        if (do_prepare)
        {
            mysql_stmt_attr_set(self->stmt, STMT_ATTR_PREBIND_PARAMS, &self->param_count);
            mysql_stmt_attr_set(self->stmt, STMT_ATTR_CB_USER_DATA, (void *)self);
            mysql_stmt_bind_param(self->stmt, self->params);

            Py_BEGIN_ALLOW_THREADS;
            if (!MARIADB_FEATURE_SUPPORTED(self->stmt->mysql, 100206))
            {
                rc= mysql_stmt_prepare(self->stmt, self->parser->statement.str, 
                        (unsigned long)self->parser->statement.length);
                if (!rc)
                    rc= mysql_stmt_execute(self->stmt);
            }
            else
                rc= mariadb_stmt_execute_direct(self->stmt, self->parser->statement.str, 
                        self->parser->statement.length);
            Py_END_ALLOW_THREADS;

            if (rc)
            {
                /* in case statement is not supported via binary protocol, we try
                   to run the statement with text protocol */
                if (mysql_stmt_errno(self->stmt) == ER_UNSUPPORTED_PS)
                {
                    Py_BEGIN_ALLOW_THREADS;
                    self->is_text= 0;
                    rc= mysql_real_query(self->connection->mysql, statement, (unsigned long)statement_len);
                    Py_END_ALLOW_THREADS;

                    if (rc)
                    {
                        mariadb_throw_exception(self->stmt->mysql, NULL, 0, NULL);
                        goto error;
                    }
                    /* if we have a result set, we can't process it - so we will return
                       an error. (XA RECOVER is the only command which returns a result set
                       and can't be prepared) */
                    if (mysql_field_count(self->stmt->mysql))
                    {
                        MYSQL_RES *result;

                        /* we need to clear the result first, otherwise the cursor remains
                           in usuable state (query out of order) */

                        if ((result= mysql_store_result(self->stmt->mysql)))
                            mysql_free_result(result);

                        mariadb_throw_exception(NULL, Mariadb_NotSupportedError, 0, "This command is not supported by MariaDB Connector/Python");
                        goto error;
                    }
                    goto end;
                }
                /* throw exception from statement handle */
                mariadb_throw_exception(self->stmt, NULL, 1, NULL);
                goto error;
            }
        } else {
            /* We are already prepared, so just reexecute statement */
            mysql_stmt_bind_param(self->stmt, self->params);
            Py_BEGIN_ALLOW_THREADS;
            rc= mysql_stmt_execute(self->stmt);
            Py_END_ALLOW_THREADS;
            if (rc)
            {
                mariadb_throw_exception(self->stmt, NULL, 1, NULL);
                goto error;
            }
        }
    }

    if (MrdbCursor_InitResultSet(self))
        goto error;
end:
    MARIADB_FREE_MEM(self->value);
    Py_RETURN_NONE;
error:
    MrdbParser_end(self->parser);
    self->parser= NULL;
    MrdbCursor_clear(self, 0);
    return NULL;
}
/* }}} */

/* {{{ MrdbCursor_fieldcount() */
PyObject *MrdbCursor_fieldcount(MrdbCursor *self)
{
    MARIADB_CHECK_STMT(self);
    if (PyErr_Occurred())
        return NULL;

    return PyLong_FromLong((long)self->field_count);
}
/* }}} */

/* {{{ MrdbCursor_description
   PEP-249 description method()

   Please note that the returned tuple contains eight (instead of
   seven items, since we need the field flag
 */
    static
PyObject *MrdbCursor_description(MrdbCursor *self)
{
    PyObject *obj= NULL;
    unsigned int field_count= self->field_count;

    MARIADB_CHECK_STMT(self);
    if (PyErr_Occurred())
        return NULL;


    if (self->fields && field_count)
    {
        uint32_t i;

        if (!(obj= PyTuple_New(field_count)))
            return NULL;

        for (i=0; i < field_count; i++)
        {
            uint32_t precision= 0;
            uint32_t decimals= 0;
            MY_CHARSET_INFO cs;
            unsigned long display_length;
            long packed_len= 0;

            display_length= self->fields[i].max_length > self->fields[i].length ? 
                            self->fields[i].max_length : self->fields[i].length;
            mysql_get_character_set_info(self->connection->mysql, &cs);
            if (cs.mbmaxlen > 1)
            {
              packed_len= display_length;
              display_length/= cs.mbmaxlen;
            }
            else {
              packed_len= mysql_ps_fetch_functions[self->fields[i].type].pack_len;
            }

            if (self->fields[i].decimals)
            {
                if (self->fields[i].decimals < 31)
                {
                    decimals= self->fields[i].decimals;
                    precision= self->fields[i].length;
                    display_length= precision + 1;
                }
            }

            PyObject *desc;
            if (!(desc= Py_BuildValue("(sIIiIIOI)",
                            self->fields[i].name,
                            self->fields[i].type,
                            display_length,
                            packed_len >= 0 ? packed_len : -1,
                            precision,
                            decimals,
                            PyBool_FromLong(!IS_NOT_NULL(self->fields[i].flags)),
                            self->fields[i].flags)))
            {
                Py_XDECREF(obj);
                mariadb_throw_exception(NULL, Mariadb_OperationalError, 0,
                        "Can't build descriptor record");
                return NULL;
            }
            PyTuple_SetItem(obj, i, desc);
        }
        Py_INCREF(obj);
        return obj;
    }
    Py_INCREF(Py_None);
    return Py_None;
}
/* }}} */

static int MrdbCursor_fetchinternal(MrdbCursor *self)
{
    unsigned int field_count= self->field_count;
    MYSQL_ROW row;
    int rc;
    unsigned int i;

    if (!self->is_text)
    {
        rc= mysql_stmt_fetch(self->stmt);
        if (rc == MYSQL_NO_DATA)
            return 1;
        return 0;
    }

    if (!(row= mysql_fetch_row(self->result)))
    {
        return 1;
    }

    for (i= 0; i < field_count; i++)
    {
        field_fetch_fromtext(self, row[i], i);
    }
    return 0;
}

static PyObject *
MrdbCursor_fetchone(MrdbCursor *self)
{
    PyObject *row;
    uint32_t i;
    unsigned int field_count= self->field_count;

    MARIADB_CHECK_STMT(self);
    if (PyErr_Occurred())
    {
        return NULL;
    }

    if (!field_count)
    {
        mariadb_throw_exception(NULL, Mariadb_ProgrammingError, 0,
                "Cursor doesn't have a result set");
        return NULL;
    }

    if (MrdbCursor_fetchinternal(self))
    {
        Py_INCREF(Py_None);
        return Py_None;
    }

    self->row_number++;
    if (!(row= mariadb_get_sequence_or_tuple(self)))
    {
        return NULL;
    }

    for (i= 0; i < field_count; i++)
    {
        MARIADB_SET_SEQUENCE_OR_TUPLE_ITEM(self, row, i);
    }
    return row;
}

static PyObject *
MrdbCursor_scroll(MrdbCursor *self,
                  PyObject *args,
                  PyObject *kwargs)
{
    char *modestr= NULL;
    PyObject *Pos;
    long position= 0;
    unsigned long long new_position= 0;
    uint8_t mode= 0; /* default: relative */
    char *kw_list[]= {"", "mode", NULL};
    const char *scroll_modes[]= {"relative", "absolute", NULL};


    MARIADB_CHECK_STMT(self);
    if (PyErr_Occurred())
    {
        return NULL;
    }

    if (!self->field_count)
    {
        mariadb_throw_exception(NULL, Mariadb_ProgrammingError, 0,
                "Cursor doesn't have a result set");
        return NULL;
    }

    if (!self->is_buffered)
    {
        mariadb_throw_exception(NULL, Mariadb_ProgrammingError, 0,
                "This method is available only for cursors with buffered result set "
                "or a read only cursor type");
        return NULL;
    }

    if (!PyArg_ParseTupleAndKeywords(args, kwargs,
                "O!|s", kw_list, &PyLong_Type, &Pos, &modestr))
    {
        return NULL;
    }

    if (modestr != NULL)
    {
        while (scroll_modes[mode]) {
            if (!strcmp(scroll_modes[mode], modestr))
                break;
            mode++;
        };
    } 
    else {
        mode= 0;
    }

    if (!scroll_modes[mode]) {
        mariadb_throw_exception(NULL, Mariadb_DataError, 0,
                "Invalid mode '%s'", modestr);
        return NULL;
    }

    if (!(position= PyLong_AsLong(Pos)) && !mode)
    {
        mariadb_throw_exception(NULL, Mariadb_DataError, 0,
                "Invalid position value 0");
        return NULL;
    }

    if (!mode) 
   {
        new_position= self->row_number + position;
        if (new_position < 0 || new_position > CURSOR_NUM_ROWS(self))
        {
            mariadb_throw_exception(NULL, Mariadb_DataError, 0,
                    "Position value is out of range");
            return NULL;
        }
    } 
    else {
        new_position= position; /* absolute */
    }

    if (!self->is_text)
    {
        mysql_stmt_data_seek(self->stmt, new_position);
    }
    else {
        mysql_data_seek(self->result, new_position);
    }

    self->row_number= (unsigned long)new_position;
    Py_INCREF(Py_None);
    return Py_None;
}

PyObject *
MrdbCursor_fetchmany(MrdbCursor *self, 
                     PyObject *args,
                     PyObject *kwargs)
{
    PyObject *List= NULL;
    uint32_t i;
    unsigned long rows= 0;
    static char *kw_list[]= {"size", NULL};
    unsigned int field_count= self->field_count;

    MARIADB_CHECK_STMT(self);
    if (PyErr_Occurred())
    {
        return NULL;
    }

    if (!field_count)
    {
        mariadb_throw_exception(0, Mariadb_ProgrammingError, 0,
                "Cursor doesn't have a result set");
        return NULL;
    }

    if (!PyArg_ParseTupleAndKeywords(args, kwargs,
                "|l:fetchmany", kw_list, &rows))
    {
        return NULL;
    }

    if (!rows)
    {
        rows= self->row_array_size;
    }

    if (!(List= PyList_New(0)))
    {
        return NULL;
    }

    /* if rows=0, return an empty list */
    if (!rows)
    {
        return List;
    }

    for (i=0; i < rows; i++)
    {
        uint32_t j;
        PyObject *Row;
        if (MrdbCursor_fetchinternal(self))
        {
            goto end;
        }
        self->affected_rows= CURSOR_NUM_ROWS(self);
        if (!(Row= mariadb_get_sequence_or_tuple(self)))
        {
            return NULL;
        }
        for (j=0; j < field_count; j++)
        {
            MARIADB_SET_SEQUENCE_OR_TUPLE_ITEM(self, Row, j);
        }
        PyList_Append(List, Row);
    }
end:
    return List;
}

static PyObject *
mariadb_get_sequence_or_tuple(MrdbCursor *self)
{
    if (self->is_named_tuple)
    {
        return PyStructSequence_New(self->sequence_type);
    }
    else {
        return PyTuple_New(self->field_count);
    }
}

static PyObject *
MrdbCursor_fetchall(MrdbCursor *self)
{
    PyObject *List;
    unsigned int field_count= self->field_count;
    MARIADB_CHECK_STMT(self);
    if (PyErr_Occurred())
    {
        return NULL;
    }

    if (!field_count)
    {
        mariadb_throw_exception(NULL, Mariadb_ProgrammingError, 0,
                "Cursor doesn't have a result set");
        return NULL;
    }

    if (!(List= PyList_New(0)))
    {
        return NULL;
    }

    while (!MrdbCursor_fetchinternal(self))
    {
        uint32_t j;
        PyObject *Row;

        self->row_number++;

        if (!(Row= mariadb_get_sequence_or_tuple(self)))
        {
            return NULL;
        }

        for (j=0; j < field_count; j++)
        {
            MARIADB_SET_SEQUENCE_OR_TUPLE_ITEM(self, Row, j)
        }
        PyList_Append(List, Row);
    }
    self->row_count= (self->is_text) ? mysql_num_rows(self->result) : 
        mysql_stmt_num_rows(self->stmt);
    return List;
}

/* MrdbCursor_executemany_fallback
   bulk execution for server < 10.2.6
 */
static uint8_t 
MrdbCursor_executemany_fallback(MrdbCursor *self,
        const char *statement,
        size_t len)
{
    uint32_t i;
    int rc= 0;

    if (mysql_stmt_attr_set(self->stmt, STMT_ATTR_PREBIND_PARAMS, &self->param_count))
    {
        goto error;
    }

    self->row_count= 0;

    for (i=0; i < self->array_size; i++)
    {
        /* Load values */
        if (mariadb_param_update(self, self->params, i))
        {
            return 1;
        }
        if (mysql_stmt_bind_param(self->stmt, self->params))
        {
            goto error;
        }
        Py_BEGIN_ALLOW_THREADS;
        if (i==0)
        {
            rc= mysql_stmt_prepare(self->stmt, self->parser->statement.str, 
                    (unsigned long)self->parser->statement.length);
        }
        if (!rc)
        {
            rc= mysql_stmt_execute(self->stmt);
        }
        Py_END_ALLOW_THREADS;
        if (rc)
        {
            goto error;
        }
        self->row_count++;
    }
    return 0;
error:
    mariadb_throw_exception(self->stmt, NULL, 1, NULL);
    return 1;
}

/* 
Note: When conecting to a server < 10.2.6 this command will be emulated
by executing preparing and executing statement n times (where n is
the number of tuples in list)
*/
static PyObject *
MrdbCursor_executemany(MrdbCursor *self,
                       PyObject *Args)
{
    char *statement= NULL;
    Py_ssize_t statement_len= 0;
    int rc;
    uint8_t do_prepare= 1;
    char errmsg[128];
    MARIADB_CHECK_STMT(self);

    if (PyErr_Occurred())
    {
        return NULL;
    }

    self->data= NULL;

    if (!PyArg_ParseTuple(Args, "s#O!", &statement, &statement_len,
                &PyList_Type, &self->data))
    {
        return NULL;
    }


    if (!self->data)
    {
        PyErr_SetString(PyExc_TypeError, "No data provided");
        return NULL;
    }

    if (self->is_prepared && self->statement)
        do_prepare= 0;

    /* if cursor type is not prepared, we need to clear the cursor first */
    if (!self->is_prepared && self->statement)
    {
        MrdbCursor_clear(self, 0);
        MrdbParser_end(self->parser);
        self->parser= NULL;
    }
    self->is_text= 0;

    if (!self->parser)
    {
        if (!(self->parser= MrdbParser_init(statement, (size_t)statement_len)))
        {
            exit(-1);
        }
        if (MrdbParser_parse(self->parser, 1, errmsg, 128))
        {
            PyErr_SetString(Mariadb_ProgrammingError, errmsg);
            goto error;
        }
        CURSOR_SET_STATEMENT(self, statement, statement_len);
    }

    if (mariadb_check_bulk_parameters(self, self->data))
        goto error;


    /* If the server doesn't support bulk execution (< 10.2.6),
       we need to call a fallback routine */
    if (!MARIADB_FEATURE_SUPPORTED(self->stmt->mysql, 100206))
    {
        if (MrdbCursor_executemany_fallback(self, self->parser->statement.str, 
                    self->parser->statement.length))
            goto error;
        goto end;
    }

    mysql_stmt_attr_set(self->stmt, STMT_ATTR_ARRAY_SIZE, &self->array_size);
    if (do_prepare)
    {
        mysql_stmt_attr_set(self->stmt, STMT_ATTR_PREBIND_PARAMS, &self->param_count);
        mysql_stmt_attr_set(self->stmt, STMT_ATTR_CB_USER_DATA, (void *)self);
        mysql_stmt_attr_set(self->stmt, STMT_ATTR_CB_PARAM, mariadb_param_update);

        mysql_stmt_bind_param(self->stmt, self->params);

        Py_BEGIN_ALLOW_THREADS;
        rc= mariadb_stmt_execute_direct(self->stmt, self->parser->statement.str,
                (unsigned long)self->parser->statement.length);
        Py_END_ALLOW_THREADS;
        if (rc)
        {
            mariadb_throw_exception(self->stmt, NULL, 1, NULL);
            goto error;
        }
    }
    else {
        Py_BEGIN_ALLOW_THREADS;
        rc= mysql_stmt_execute(self->stmt);
        Py_END_ALLOW_THREADS;
        if (rc)
        {
            mariadb_throw_exception(self->stmt, NULL, 1, NULL);
            goto error;
        }
    }
end:
    MARIADB_FREE_MEM(self->values);
    Py_RETURN_NONE;
error:
    MrdbCursor_clear(self, 0);
    MrdbParser_end(self->parser);
    self->parser= NULL;
    return NULL;
}

static PyObject *
MrdbCursor_nextset(MrdbCursor *self)
{
    int rc;
    MARIADB_CHECK_STMT(self);

    if (PyErr_Occurred())
    {
        return NULL;
    }
/* hmmm */
    if (!self->field_count)
    {
        mariadb_throw_exception(NULL, Mariadb_ProgrammingError, 0,
                "Cursor doesn't have a result set");
        return NULL;
    }

    Py_BEGIN_ALLOW_THREADS;
    if (!self->is_text)
        rc= mysql_stmt_next_result(self->stmt);
    else
    {
        if (self->result)
        {
            mysql_free_result(self->result);
            self->result= NULL;
        }
        rc= mysql_next_result(self->connection->mysql);
    }
    Py_END_ALLOW_THREADS;

    if (rc)
    {
        Py_INCREF(Py_None);
        return Py_None;
    }
    if (CURSOR_FIELD_COUNT(self))
    {
        if (MrdbCursor_InitResultSet(self))
        {
            return NULL;
        }
    }
    else {
        self->fields= 0;
    }
    Py_RETURN_TRUE;
}

static PyObject *
Mariadb_row_count(MrdbCursor *self)
{
    int64_t row_count= 0;

    MARIADB_CHECK_STMT(self);
    if (PyErr_Occurred())
    {
        return NULL;
    }

    /* PEP-249 requires to return -1 if the cursor was not executed before */
    if (!self->statement)
    {
        return PyLong_FromLongLong(-1);
    }

    if (self->field_count)
    {
        row_count= CURSOR_NUM_ROWS(self);
    }
    else {
        row_count= self->row_count ? self->row_count : CURSOR_AFFECTED_ROWS(self);
        if (!row_count)
            row_count= -1;
    }
    return PyLong_FromLongLong(row_count);
}

static PyObject *
Mariadb_row_number(MrdbCursor *self)
{
    unsigned int field_count= self->field_count;
    if (!field_count) {
        Py_INCREF(Py_None);
        return Py_None;
    }
    return PyLong_FromLongLong(self->row_number);
}

static PyObject *
MrdbCursor_warnings(MrdbCursor *self)
{
    MARIADB_CHECK_STMT(self);

    return PyLong_FromLong((long)CURSOR_WARNING_COUNT(self));
}

static PyObject *
MrdbCursor_getbuffered(MrdbCursor *self)
{
    if (self->is_buffered)
    {
        Py_RETURN_TRUE;
    }
    Py_RETURN_FALSE;
}

static int
MrdbCursor_setbuffered(MrdbCursor *self, PyObject *arg)
{
    if (!arg || Py_TYPE(arg) != &PyBool_Type)
    {
        PyErr_SetString(PyExc_TypeError, "Argument must be boolean");
        return -1;
    }

    self->is_buffered= PyObject_IsTrue(arg);
    return 0;
}

static PyObject *
MrdbCursor_lastrowid(MrdbCursor *self)
{
    MARIADB_CHECK_STMT(self);
    return PyLong_FromUnsignedLongLong(CURSOR_INSERT_ID(self));
}

/* iterator protocol */

static PyObject *
MrdbCursor_iter(PyObject *self)
{
    MARIADB_CHECK_STMT(((MrdbCursor *)self));
    Py_INCREF(self);
    return self;
}

static PyObject *
MrdbCursor_iternext(PyObject *self)
{
    PyObject *res;

    res= MrdbCursor_fetchone((MrdbCursor *)self);

    if (res && res == Py_None)
    {
        Py_DECREF(res);
        res= NULL;
    }
    return res;
}

static PyObject
*MrdbCursor_closed(MrdbCursor *self)
{
    if (self->is_closed || !self->stmt || self->stmt->mysql == NULL)
        Py_RETURN_TRUE;
    Py_RETURN_FALSE;
}

static PyObject *
MrdbCursor_sp_outparams(MrdbCursor *self)
{
    if (!self->is_closed && self->stmt && 
            self->stmt->mysql && 
            (self->stmt->mysql->server_status & SERVER_PS_OUT_PARAMS))
    {
        Py_RETURN_TRUE;
    }

    Py_RETURN_FALSE;
}

static PyObject *
MrdbCursor_callproc(MrdbCursor *self, PyObject *args)
{
    const char *sp;
    Py_ssize_t sp_len;
    PyObject *data= NULL;
    uint32_t i, param_count= 0;
    char *stmt= NULL;
    size_t stmt_len= 0;
    PyObject *new_args= NULL;
    PyObject *rc= NULL;

    MARIADB_CHECK_STMT(((MrdbCursor *)self));

    if (!PyArg_ParseTuple(args, "s#|O!", &sp, &sp_len,
                &PyTuple_Type, &data))
        return NULL;

    if (data)
        param_count= (uint32_t)PyTuple_Size(data);

    stmt_len= sp_len + 5 + 3 + param_count * 2 + 1;
    if (!(stmt= (char *)PyMem_RawCalloc(1, stmt_len)))
        goto end;
    sprintf(stmt, "CALL %s(", sp);
    for (i=0; i < param_count; i++)
    {
        if (i)
        {
            strcat(stmt, ",");
        }
        strcat(stmt, "?");
    }
    strcat(stmt, ")");

    new_args= PyTuple_New(2);
    PyTuple_SetItem(new_args, 0, PyUnicode_FromString(stmt));
    PyTuple_SetItem(new_args, 1, data);

    rc= MrdbCursor_execute(self, new_args, NULL);
    Py_DECREF(new_args);
end:
    if (stmt)
    {
        PyMem_RawFree(stmt);
    }
    return rc;
}

static PyObject *
MrdbCursor_enter(MrdbCursor *self, PyObject *args __attribute__((unused)))
{
    Py_INCREF(self);
    return (PyObject *)self;
}

static PyObject *
MrdbCursor_exit(MrdbCursor *self, PyObject *args __attribute__((unused)))
{
    PyObject *rc= NULL,
             *tmp= NULL;

    if ((tmp= PyObject_CallMethod((PyObject *)self, "close", "")))
    {
        rc= Py_None;
        Py_INCREF(rc);
    }
    Py_XDECREF(tmp);
    return rc;
}
