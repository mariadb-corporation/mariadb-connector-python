 //  SPDX-License-Identifier: LGPL-2.1-or-later
//  Copyright (c) 2020-2025 MariaDB Corporation Ab

#include <mariadb_python.h>
#include <docs/cursor.h>
#include <datetime.h>

static void
MrdbCursor_finalize(MrdbCursor *self);

static PyObject *
MrdbCursor_close(MrdbCursor *self);

static PyObject *
MrdbCursor_reset(MrdbCursor *self);

static PyObject *
MrdbCursor_nextset(MrdbCursor *self);

static PyObject *
MrdbCursor_execute_binary(MrdbCursor *self);

static PyObject *
MrdbCursor_InitResultSet(MrdbCursor *self);

static PyObject *
MrdbCursor_execute_text(MrdbCursor *self, PyObject *const *args, Py_ssize_t nargs);

static PyObject *
MrdbCursor_check_text_types(MrdbCursor *self);

static PyObject *
MrdbCursor_fetchrows(MrdbCursor *self, PyObject *rows);

static PyObject *
MrdbCursor_set_text_statement(MrdbCursor *self, PyObject *stmt);

static PyObject *
MrdbCursor_set_statement(MrdbCursor *self, PyObject *args);

static PyObject *
MrdbCursor_description(MrdbCursor *self);

static PyObject *
MrdbCursor_fetchone(MrdbCursor *self);

/* Async method declarations - now defined at the end of this file */
static PyObject *MrdbCursor_set_field_count_from_connection(MrdbCursor *self, PyObject *args);
static PyObject *MrdbCursor_readresponse_start(MrdbCursor *self, PyObject *args);
static PyObject *MrdbCursor_readresponse_cont(MrdbCursor *self, PyObject *args);
static PyObject *MrdbCursor_fetch_row_start(MrdbCursor *self);
static PyObject *MrdbCursor_fetch_row_cont(MrdbCursor *self, PyObject *args);
static PyObject *MrdbCursor_prepare_stmt_only(MrdbCursor *self, PyObject *args);
static PyObject *MrdbCursor_stmt_execute_start(MrdbCursor *self, PyObject *args);
static PyObject *MrdbCursor_stmt_execute_cont(MrdbCursor *self, PyObject *args);
static PyObject *MrdbCursor_stmt_fetch_start(MrdbCursor *self);
static PyObject *MrdbCursor_stmt_fetch_cont(MrdbCursor *self, PyObject *args);

/* Shared fetch function - used by both sync and async cursors */
int MrdbCursor_fetchinternal(MrdbCursor *self);

/* Prepared statement cache helpers */
static PyObject *MrdbCursor_detach_stmt(MrdbCursor *self);
static PyObject *MrdbCursor_attach_stmt(MrdbCursor *self, PyObject *capsule);
static PyObject *MrdbCursor_close_stmt_no_close(MrdbCursor *self);

static PyObject *
MrdbCursor_seek(MrdbCursor *self,
                PyObject *offset);

static PyObject *
MrdbCursor_execute_bulk(MrdbCursor *self);

void
field_fetch_fromtext(MrdbCursor *self, char *data, unsigned int column);

static PyObject *
MrdbCursor_readresponse(MrdbCursor *self);

PyObject *MrdbCursor_clear_result(MrdbCursor *self);
static void ma_cursor_close(MrdbCursor *self);

void
field_fetch_callback(void *data, unsigned int column, unsigned char **row);
static PyObject *mariadb_get_sequence_or_tuple(MrdbCursor *self);

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

static char *mariadb_named_tuple_name= "mariadb_c.Row";
static char *mariadb_named_tuple_desc= "Named tupled row";
static PyObject *Mariadb_row_count(MrdbCursor *self);
static PyObject *Mariadb_row_number(MrdbCursor *self);
static PyObject *MrdbCursor_warnings(MrdbCursor *self);
static PyObject *MrdbCursor_closed(MrdbCursor *self);
static PyObject *MrdbCursor_metadata(MrdbCursor *self);


static PyGetSetDef MrdbCursor_sets[]=
{
    {"description", (getter)MrdbCursor_description, NULL,
        cursor_description__doc__, NULL},
    {"metadata", (getter)MrdbCursor_metadata, NULL,
        cursor_metadata__doc__, NULL},
    {"rowcount", (getter)Mariadb_row_count, NULL,
        NULL, NULL},
    {"warnings", (getter)MrdbCursor_warnings, NULL,
        cursor_warnings__doc__, NULL},
    {"closed", (getter)MrdbCursor_closed, NULL,
        cursor_closed__doc__, NULL},
    {"rownumber", (getter)Mariadb_row_number, NULL,
        cursor_rownumber__doc__, NULL},
    {NULL}
};

static PyMethodDef MrdbCursor_Methods[] =
{
    /* PEP-249 methods */
    {"close", (PyCFunction)MrdbCursor_close,
        METH_NOARGS,
        cursor_close__doc__},
    {"fetchone", (PyCFunction)MrdbCursor_fetchone,
        METH_NOARGS,
        cursor_fetchone__doc__,},
    {"fetchrows", (PyCFunction)MrdbCursor_fetchrows,
        METH_O,
        NULL},
    {"_nextset", (PyCFunction)MrdbCursor_nextset,
        METH_NOARGS,
        cursor_nextset__doc__},
    {"next", (PyCFunction)MrdbCursor_fetchone,
        METH_NOARGS,
        cursor_next__doc__},
    /* internal helper functions */
    {"_check_text_types", (PyCFunction) MrdbCursor_check_text_types,
        METH_NOARGS,
        NULL},
    {"_reset", (PyCFunction)MrdbCursor_reset,
        METH_NOARGS,
        NULL},
    {"_seek", (PyCFunction)MrdbCursor_seek,
        METH_O,
        NULL},
    {"_initresult", (PyCFunction)MrdbCursor_InitResultSet,
        METH_NOARGS,
        NULL},
    {"_set_field_count_from_connection", (PyCFunction)MrdbCursor_set_field_count_from_connection,
        METH_NOARGS,
        "Set field_count from connection for async"},
    {"_async_readresponse_start", (PyCFunction)MrdbCursor_readresponse_start,
        METH_NOARGS,
        "Start non-blocking read response"},
    {"_async_readresponse_cont", (PyCFunction)MrdbCursor_readresponse_cont,
        METH_VARARGS,
        "Continue non-blocking read response"},
    {"_async_fetch_row_start", (PyCFunction)MrdbCursor_fetch_row_start,
        METH_NOARGS,
        "Start non-blocking row fetch"},
    {"_async_fetch_row_cont", (PyCFunction)MrdbCursor_fetch_row_cont,
        METH_VARARGS,
        "Continue non-blocking row fetch"},
    {"_prepare_stmt_only", (PyCFunction)MrdbCursor_prepare_stmt_only,
        METH_NOARGS,
        "Prepare statement without executing (shared)"},
    {"_async_stmt_execute_start", (PyCFunction)MrdbCursor_stmt_execute_start,
        METH_NOARGS,
        "Start non-blocking prepared statement execution"},
    {"_async_stmt_execute_cont", (PyCFunction)MrdbCursor_stmt_execute_cont,
        METH_VARARGS,
        "Continue non-blocking prepared statement execution"},
    {"_async_stmt_fetch_start", (PyCFunction)MrdbCursor_stmt_fetch_start,
        METH_NOARGS,
        "Start non-blocking prepared statement fetch"},
    {"_async_stmt_fetch_cont", (PyCFunction)MrdbCursor_stmt_fetch_cont,
        METH_VARARGS,
        "Continue non-blocking prepared statement fetch"},
    {"_detach_stmt", (PyCFunction)MrdbCursor_detach_stmt,
        METH_NOARGS,
        "Detach MYSQL_STMT into a PyCapsule for cache storage"},
    {"_attach_stmt", (PyCFunction)MrdbCursor_attach_stmt,
        METH_O,
        "Attach a cached MYSQL_STMT PyCapsule to this cursor"},
    {"_close_stmt_no_close", (PyCFunction)MrdbCursor_close_stmt_no_close,
        METH_NOARGS,
        "Free local MYSQL_STMT without sending COM_STMT_CLOSE"},
    {"_set_text_statement", (PyCFunction)MrdbCursor_set_text_statement,
        METH_O,
        NULL},
    {"_set_statement", (PyCFunction)MrdbCursor_set_statement,
        METH_VARARGS,
        NULL},
    {"_sync_readresponse", (PyCFunction)MrdbCursor_readresponse,
        METH_NOARGS,
         NULL},
    {"_sync_execute_text", (PyCFunction)MrdbCursor_execute_text,
        METH_FASTCALL,
        NULL},
    {"_execute_binary", (PyCFunction)MrdbCursor_execute_binary,
        METH_NOARGS,
        NULL},
    {"_execute_bulk", (PyCFunction)MrdbCursor_execute_bulk,
        METH_NOARGS,
        NULL},
    {"_clear_result", (PyCFunction)MrdbCursor_clear_result,
        METH_NOARGS,
        NULL},
    {NULL} /* always last */
};

static struct PyMemberDef MrdbCursor_Members[] =
{
    {"statement",
        T_STRING,
        offsetof(MrdbCursor, statement),
        READONLY,
        cursor_statement__doc__},
    {"_reprepare",
        T_UINT,
        offsetof(MrdbCursor, reprepare),
        0,
        MISSING_DOC},
    {"_text",
        T_BOOL,
        offsetof(MrdbCursor, is_text),
        0,
        MISSING_DOC},
    {"_resulttype",
        T_UINT,
        offsetof(MrdbCursor, result_format),
        0,
        MISSING_DOC},
    {"paramcount",
        T_UINT,
        offsetof(MrdbCursor, paramcount),
        READONLY,
        cursor_paramcount__doc__},
    {"_data",
        T_OBJECT,
        offsetof(MrdbCursor, data),
        0,
        MISSING_DOC},
    {"_cursor_type",
        T_ULONG,
        offsetof(MrdbCursor, cursor_type),
        0,
        MISSING_DOC},
    {"buffered",
        T_BOOL,
        offsetof(MrdbCursor, is_buffered),
        0,
        cursor_buffered__doc__},
    {"arraysize",
        T_LONG,
        offsetof(MrdbCursor, row_array_size),
        0,
        cursor_arraysize__doc__},
    {"field_count",
        T_UINT,
        offsetof(MrdbCursor, field_count),
        READONLY,
        cursor_field_count__doc__},
    {"affected_rows",
        T_ULONGLONG,
        offsetof(MrdbCursor, affected_rows),
        READONLY,
        "This property is deprecated - use rowcount instead."},
    {"_rownumber",
        T_ULONGLONG,
        offsetof(MrdbCursor, row_number),
        0,
        NULL},
    {"insert_id",
        T_UINT,
        offsetof(MrdbCursor, lastrow_id),
        READONLY,
        "returns the ID generated by a query on a table with a column " \
        "having the AUTO_INCREMENT attribute or the value for the last "\
        "usage of LAST_INSERT_ID()"},
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
static int
MrdbCursor_init_fields(MrdbCursor *self)
{
    /* Initialize all fields to NULL/0 */
    self->connection = NULL;
    self->stmt = NULL;
    self->result = NULL;
    self->data = NULL;
    self->array_size = 0;
    self->row_array_size = 0;
    self->paraminfo = NULL;
    self->value = NULL;
    self->params = NULL;
    self->bind = NULL;
    self->fields = NULL;
    self->statement = NULL;
    self->statement_len = 0;
    self->paramcount = 0;
    self->is_text = 0;
    self->values = NULL;
    self->sequence_fields = NULL;
    self->sequence_type = NULL;
    self->prefetch_rows = 0;
    self->cursor_type = 0;
    self->affected_rows = 0;
    self->field_count = 0;
    self->row_count = 0;
    self->lastrow_id = 0;
    self->row_number = 0;
    self->result_format = 0;
    self->is_buffered = 0;
    self->fetched = 0;
    self->closed = 0;
    self->reprepare = 0;
    self->paramstyle = 0;
    self->weakreflist = NULL;
    return 0;
}

static int MrdbCursor_initialize(MrdbCursor *self, PyObject *args,
        PyObject *kwargs)
{
    char *key_words[]= {"", "prefetch_size", "cursor_type",
                        "binary", "named_tuple", "dictionary", "buffered", NULL};
    PyObject *connection;
    unsigned long cursor_type= 0,
                  prefetch_rows= 0;
    int is_binary= 0,
        named_tuple= 0,
        dictionary= 0,
        buffered= 1;

    if (!self)
        return -1;

    /* Initialize all fields first */
    MrdbCursor_init_fields(self);

    if (!PyArg_ParseTupleAndKeywords(args, kwargs,
                "O!|kkippp", key_words, &MrdbConnection_Type, &connection,
                &prefetch_rows, &cursor_type, &is_binary,
                &named_tuple, &dictionary, &buffered))
        return -1;

    /* Set result format based on named_tuple and dictionary parameters */
    if (named_tuple) {
        self->result_format = RESULT_NAMED_TUPLE;
    } else if (dictionary) {
        self->result_format = RESULT_DICTIONARY;
    } else {
        self->result_format = RESULT_TUPLE;
    }

    /* Set buffered flag */
    self->is_buffered = buffered;

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
    self->connection = (MrdbConnection *)connection;

    self->is_text= 0;
    self->stmt= NULL;
    self->cursor_type = cursor_type;
    self->prefetch_rows= prefetch_rows;
    self->row_array_size= 1;

    return 0;
}
/* }}} */

static int MrdbCursor_traverse(
        MrdbCursor *self,
        visitproc visit,
        void *arg)
{
    Py_VISIT(self->connection);
    Py_VISIT(self->data);
    Py_VISIT(self->sequence_type);
    // Visit all values in the values array
    if (self->values && self->field_count > 0) {
        for (uint32_t i = 0; i < self->field_count; i++) {
            Py_VISIT(self->values[i]);
        }
    }

    // Visit all PyObject values in the MrdbParamValue array
    if (self->value && self->paramcount > 0) {
        for (uint32_t i = 0; i < self->paramcount; i++) {
            Py_VISIT(self->value[i].value);
        }
    }

    return 0;
}

static int MrdbCursor_tpclear(MrdbCursor *self)
{
    if (self->connection)
        Py_CLEAR(self->connection);
    if (self->data)
        Py_CLEAR(self->data);
    if (self->sequence_type)
        Py_CLEAR(self->sequence_type);
    // Clear all values in the values array
    if (self->values && self->field_count > 0) {
        for (uint32_t i = 0; i < self->field_count; i++) {
            Py_CLEAR(self->values[i]);
        }
    }

    // Clear all PyObject values in the MrdbParamValue array
    if (self->value && self->paramcount > 0) {
        for (uint32_t i = 0; i < self->paramcount; i++) {
            Py_CLEAR(self->value[i].value);
        }
    }

    return 0;
}

static PyObject *MrdbCursor_repr(MrdbCursor *self)
{
    char cobj_repr[384];

    if (!self->closed)
        snprintf(cobj_repr, 384, "<mariadb_c.cursor at %p>", self);
    else
        snprintf(cobj_repr, 384, "<mariadb_c.cursor (closed) at %p>",
                self);
    return PyUnicode_FromString(cobj_repr);
}

static void MrdbCursor_dealloc(PyObject *obj)
{
  MrdbCursor *self = (MrdbCursor *)obj;
  ma_cursor_close(self);
  MrdbCursor_tpclear(self);
  Py_TYPE(self)->tp_free((PyObject *)self);
}

PyTypeObject MrdbCursor_Type =
{
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "mariadb_c.cursor",
    .tp_basicsize= (Py_ssize_t)sizeof(MrdbCursor),
    .tp_repr= (reprfunc)MrdbCursor_repr,
    .tp_flags= Py_TPFLAGS_DEFAULT | Py_TPFLAGS_HAVE_GC | Py_TPFLAGS_BASETYPE,
    .tp_doc= mariadb_cursor_documentation,
    .tp_new= PyType_GenericNew,
    .tp_alloc= PyType_GenericAlloc,
    .tp_traverse= (traverseproc)MrdbCursor_traverse,/* tp_traverse */
    .tp_methods= (struct PyMethodDef *)MrdbCursor_Methods,
    .tp_members= (struct PyMemberDef *)MrdbCursor_Members,
    .tp_getset= MrdbCursor_sets,
    .tp_init= (initproc)MrdbCursor_initialize,
    .tp_dealloc= MrdbCursor_dealloc,
    .tp_clear = (inquiry)MrdbCursor_tpclear,
    .tp_free = PyObject_GC_Del,
    .tp_finalize= (destructor)MrdbCursor_finalize,
    .tp_weaklistoffset = 0
};

static void MrdbCursor_clearstmt(MrdbCursor *self)
{
  if (self->statement)
    MARIADB_FREE_MEM(self->statement);
  self->statement = NULL;
  self->statement_len = 0;
  self->paramcount = 0;
  self->is_text = 0;
}

/* {{{ MrdbCursor_clear_result(MrdbCursor *self)
   clear pending result sets
*/
PyObject *MrdbCursor_clear_result(MrdbCursor *self)
{
    if (!self->is_text &&
        self->stmt)
    {
        /* free current result */
        if (mysql_stmt_field_count(self->stmt))
        {
            mysql_stmt_free_result(self->stmt);
        }
        /* check if there are more pending result sets */
        while (mysql_stmt_next_result(self->stmt) == 0)
        {
            if (mysql_stmt_field_count(self->stmt))
            {
                mysql_stmt_free_result(self->stmt);
            }
        }
    } else if (self->is_text)
    {
        /* free current result - drain remaining rows first if it exists
         * (even if is_buffered is now True, the result might have been created as unbuffered, so we must drain it) */
        if (self->result)
        {
            while (mysql_fetch_row(self->result))
            {
            }
            mysql_free_result(self->result);
        }
        /* clear pending result sets */
        if (self->connection && self->connection->mysql)
        {
            while (mysql_more_results(self->connection->mysql))
            {
                MYSQL_RES *res;
                if (mysql_next_result(self->connection->mysql) != 0)
                    break;
                if ((res= mysql_use_result(self->connection->mysql)))
                {
                    while (mysql_fetch_row(res))
                    {
                    }
                    mysql_free_result(res);
                }
            }

            /* Clear Python-level active cursor tracking */
            PyObject *active = PyObject_GetAttrString((PyObject *)self->connection, "_active_streaming_result");
            const char *field_name = "_active_streaming_result";
            
            if (!active || PyErr_Occurred()) {
                PyErr_Clear();
                active = PyObject_GetAttrString((PyObject *)self->connection, "_active_async_cursor");
                field_name = "_active_async_cursor";
            }
            
            if (active && active != Py_None && active == (PyObject *)self) {
                PyObject_SetAttrString((PyObject *)self->connection, field_name, Py_None);
            }
            Py_XDECREF(active);
        }
    }
    /* CONPY-52: Avoid possible double free */
    self->result= NULL;
    Py_RETURN_NONE;
}

static void MrdbCursor_FreeValues(MrdbCursor *self)
{
  uint32_t i;
  if (!self->value)
    return;
  for (i= 0; i < self->paramcount; i++)
    if (self->value[i].free_me)
      MARIADB_FREE_MEM(self->value[i].buffer);
  MARIADB_FREE_MEM(self->value);
}

static void MrdbCursor_FreeResultValues(MrdbCursor *self)
{
  if (self->values && self->field_count > 0) {
    for (uint32_t i = 0; i < self->field_count; i++) {
      Py_CLEAR(self->values[i]);
    }
  }
  MARIADB_FREE_MEM(self->values);
}

/* {{{ MrdbCursor_clear
   Resets statement attributes  and frees
   associated memory
 */
static
void MrdbCursor_clear(MrdbCursor *self, uint8_t new_stmt)
{
    /* clear pending result sets */
    MrdbCursor_clear_result(self);

    if (!self->is_text && self->stmt) {
        if (new_stmt)
        {
          mysql_stmt_close(self->stmt);
          self->stmt= mysql_stmt_init(self->connection->mysql);
        }
        else {
            uint32_t val= 0;

            mysql_stmt_reset(self->stmt);

            /* we need to unset array size only */
            mysql_stmt_attr_set(self->stmt, STMT_ATTR_ARRAY_SIZE, &val);
        }

    }
    self->fetched= 0;

    if (self->sequence_fields)
    {
        MARIADB_FREE_MEM(self->sequence_fields);
    }
    self->fields= NULL;
    self->row_count= 0;
    self->affected_rows= 0;
    MrdbCursor_FreeValues(self);
    MrdbCursor_clearstmt(self);
    MrdbCursor_FreeResultValues(self);
    MARIADB_FREE_MEM(self->bind);
    MARIADB_FREE_MEM(self->value);
    MARIADB_FREE_MEM(self->params);
}
/* }}} */

static void ma_set_result_column_value(MrdbCursor *self, PyObject *row, uint32_t column)
{
    PyObject *value;

    /* Ensure values array exists and column value is valid */
    if (!self->values || !self->values[column]) {
        value = Py_None;
        Py_INCREF(value);
    } else {
        value = self->values[column];
        /* INCREF to keep object alive after self->values is cleared */
        Py_INCREF(value);
    }

    switch (self->result_format) {
        case RESULT_NAMED_TUPLE:
            PyStructSequence_SET_ITEM(row, column, value);
            break;
        case RESULT_DICTIONARY:
            PyDict_SetItemString(row, self->fields[column].name, value);
            Py_DECREF(value); /* CONPY-119 */
            break;
        default:
            PyTuple_SET_ITEM(row, column, value);
            break;
    }
}

static
void ma_cursor_reset(MrdbCursor *self)
{
    if (!self->closed)
    {
        MrdbCursor_clear_result(self);
        if (!self->is_text && self->stmt)
        {
            /* Todo: check if all the cursor stuff is deleted (when using prepared
               statements this should be handled in mysql_stmt_close) */
            Py_BEGIN_ALLOW_THREADS;
            mysql_stmt_close(self->stmt);
            Py_END_ALLOW_THREADS;
            self->stmt= NULL;
        }
        MrdbCursor_clear(self, 0);

        MrdbCursor_clearstmt(self);
    }
}

/* {{{ ma_cursor_close
   closes the statement handle of current cursor. After call to
   cursor_close the cursor can't be reused anymore
 */
static
void ma_cursor_close(MrdbCursor *self)
{
    ma_cursor_reset(self);

    /* Clear Python-level active cursor tracking */
    if (self->connection) {
        PyObject *active = PyObject_GetAttrString((PyObject *)self->connection, "_active_streaming_result");
        const char *field_name = "_active_streaming_result";
        
        if (!active || PyErr_Occurred()) {
            PyErr_Clear();
            active = PyObject_GetAttrString((PyObject *)self->connection, "_active_async_cursor");
            field_name = "_active_async_cursor";
        }
        
        if (active && active != Py_None && active == (PyObject *)self) {
            PyObject_SetAttrString((PyObject *)self->connection, field_name, Py_None);
        }
        Py_XDECREF(active);
    }

    self->closed= 1;
}

static PyObject * MrdbCursor_reset(MrdbCursor *self)
{
    ma_cursor_reset(self);
    Py_RETURN_NONE;
}

static
PyObject * MrdbCursor_close(MrdbCursor *self)
{
    ma_cursor_close(self);
    Py_RETURN_NONE;
}
/* }}} */

/* {{{ MrdbCursor_Finalize */
static void MrdbCursor_finalize(MrdbCursor *self)
{
    if (self->connection && self->connection->mysql)
        ma_cursor_close(self);
}
/* }}} */

static int Mrdb_GetFieldInfo(MrdbCursor *self)
{
    self->row_number= 0;

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

            if (!self->is_buffered) {
                /* Set Python-level active cursor tracking */
                /* Try sync field first, if it doesn't exist try async field */
                PyObject *test = PyObject_GetAttrString((PyObject *)self->connection, "_active_streaming_result");
                if (test || !PyErr_Occurred()) {
                    Py_XDECREF(test);
                    if (PyObject_SetAttrString((PyObject *)self->connection, "_active_streaming_result", (PyObject *)self) < 0) {
                        return 1;
                    }
                } else {
                    PyErr_Clear();
                    if (PyObject_SetAttrString((PyObject *)self->connection, "_active_async_cursor", (PyObject *)self) < 0) {
                        return 1;
                    }
                }
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

        if (self->result_format == RESULT_NAMED_TUPLE) {
            unsigned int i;
            PyStructSequence_Desc sequence_desc;

            if (!(self->sequence_fields= (PyStructSequence_Field *)
                        PyMem_RawCalloc(self->field_count + 1,
                            sizeof(PyStructSequence_Field)))) {
                PyErr_SetString(PyExc_MemoryError, "Failed to allocate memory for sequence fields");
                return 1;
            }
            sequence_desc.name= mariadb_named_tuple_name;
            sequence_desc.doc= mariadb_named_tuple_desc;
            sequence_desc.fields= self->sequence_fields;
            sequence_desc.n_in_sequence= self->field_count;


            for (i=0; i < self->field_count; i++)
            {
                self->sequence_fields[i].name= self->fields[i].name;
            }
            self->sequence_type= PyStructSequence_NewType(&sequence_desc);
            if (!self->sequence_type) {
                PyMem_RawFree(self->sequence_fields);
                self->sequence_fields = NULL;
                return 1;
            }
#if PY_VERSION_HEX < 0x03070000
            self->sequence_type->tp_flags|= Py_TPFLAGS_HEAPTYPE;
#endif
        }
    }
    return 0;
}

PyObject *MrdbCursor_InitResultSet(MrdbCursor *self)
{
    MARIADB_FREE_MEM(self->sequence_fields);
    MrdbCursor_FreeResultValues(self);

    if (self->result)
    {
        mysql_free_result(self->result);
        self->result= NULL;
    }

    if (self->field_count)
    {
        if (Mrdb_GetFieldInfo(self))
        {
            return NULL;
        }

        if (!(self->values= (PyObject**)PyMem_RawCalloc(self->field_count, sizeof(PyObject *)))) {
            PyErr_SetString(PyExc_MemoryError, "Failed to allocate memory for cursor values");
            return NULL;
        }
        if (!self->is_text)
            mysql_stmt_attr_set(self->stmt, STMT_ATTR_CB_RESULT, field_fetch_callback);

        self->row_count= CURSOR_NUM_ROWS(self);
        self->affected_rows= 0;
    } else {
      self->row_count= self->affected_rows= CURSOR_AFFECTED_ROWS(self);
    }
    self->lastrow_id= CURSOR_INSERT_ID(self);

    Py_RETURN_NONE;
}

static int Mrdb_execute_direct(MrdbCursor *self, 
                               const char *statement,
                               size_t statement_len)
{
   int rc;

   Py_BEGIN_ALLOW_THREADS;
   long ext_caps;

   mariadb_get_infov(self->connection->mysql,
                      MARIADB_CONNECTION_EXTENDED_SERVER_CAPABILITIES, &ext_caps);
   
   /* clear pending result sets */
   MrdbCursor_clear_result(self);

   /* if stmt is already prepared */
   if (!self->reprepare)
   {
       rc= mysql_stmt_execute(self->stmt);
       goto end;
   }

   /* execute_direct was implemented together with bulk operations, so we need
      to check if MARIADB_CLIENT_STMT_BULK_OPERATIONS is set in extended server
      capabilities */
   if (!(ext_caps &
        (MARIADB_CLIENT_STMT_BULK_OPERATIONS >> 32)))
   {
       if (!(rc= mysql_stmt_prepare(self->stmt, statement, (unsigned long)statement_len)))
       {
           rc= mysql_stmt_execute(self->stmt);
       }
   } else {
       rc= mariadb_stmt_execute_direct(self->stmt, statement, statement_len);
   }
end:
   Py_END_ALLOW_THREADS;
   return rc;
}

/* {{{ MrdbCursor_metadata */
static PyObject *MrdbCursor_metadata(MrdbCursor *self)
{
    uint32_t i;
    PyObject *dict = NULL;
    const char *keys[14]= {"catalog", "schema", "field", "org_field", "table",
                           "org_table", "type", "charset", "length",
                           "max_length", "decimals", "flags", "ext_type_or_format"};
    PyObject *tuple[14]= {0};
    Mrdb_ExtFieldType *ext_field_type= NULL;

    if (!self->field_count)
        Py_RETURN_NONE;

    if (PyErr_Occurred())
        return NULL;

    for (i=0; i < 13; i++)
      if (!(tuple[i] = PyTuple_New(self->field_count)))
        goto error;


    for (i=0; i < self->field_count; i++)
    {
      PyTuple_SetItem(tuple[0], i, PyUnicode_FromString(self->fields[i].catalog));
      PyTuple_SetItem(tuple[1], i, PyUnicode_FromString(self->fields[i].db));
      PyTuple_SetItem(tuple[2], i, PyUnicode_FromString(self->fields[i].name));
      PyTuple_SetItem(tuple[3], i, PyUnicode_FromString(self->fields[i].org_name));
      PyTuple_SetItem(tuple[4], i, PyUnicode_FromString(self->fields[i].table));
      PyTuple_SetItem(tuple[5], i, PyUnicode_FromString(self->fields[i].org_table));
      PyTuple_SetItem(tuple[6], i, PyLong_FromLong((long)self->fields[i].type));
      PyTuple_SetItem(tuple[7], i, PyLong_FromLong((long)self->fields[i].charsetnr));
      PyTuple_SetItem(tuple[8], i, PyLong_FromLongLong((long long)self->fields[i].max_length));
      PyTuple_SetItem(tuple[9], i, PyLong_FromLongLong((long long)self->fields[i].length));
      PyTuple_SetItem(tuple[10], i, PyLong_FromLong((long)self->fields[i].decimals));
      PyTuple_SetItem(tuple[11], i, PyLong_FromLong((long)self->fields[i].flags));

      if ((ext_field_type= mariadb_extended_field_type(&self->fields[i])))
          PyTuple_SetItem(tuple[12], i, PyLong_FromLong((long)ext_field_type->ext_type));
      else
          PyTuple_SetItem(tuple[12], i, PyLong_FromLong((long)EXT_TYPE_NONE));
    }

    if (!(dict =PyDict_New()))
        goto error;

    for (i=0; i < 13; i++)
    {
        if (PyDict_SetItem(dict, PyUnicode_FromString(keys[i]), tuple[i]))
            goto error;
        Py_DECREF(tuple[i]);
        tuple[i]= NULL;
    }
    return dict;
error:
    for (i=0; i < 13; i++)
        if (tuple[i])
            Py_DECREF(tuple[i]);
    if (dict)
        Py_DECREF(dict);
    return NULL;
}
/* }}}*/

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
            PyObject *desc;
            Mrdb_ExtFieldType *ext_field_type= mariadb_extended_field_type(&self->fields[i]);

            display_length= self->fields[i].max_length > self->fields[i].length ? 
                            self->fields[i].max_length : self->fields[i].length;
            mysql_get_character_set_info(self->connection->mysql, &cs);
            if (cs.mbmaxlen > 1)
            {
                packed_len= display_length;
                display_length/= cs.mbmaxlen;
            } else {
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

            if (ext_field_type)
            {
                if (ext_field_type->ext_type == EXT_TYPE_JSON)
                    self->fields[i].type= MYSQL_TYPE_JSON;
            }
            if (!(desc= Py_BuildValue("(sIIiIIOIsss)",
                            self->fields[i].name,
                            self->fields[i].type,
                            display_length,
                            packed_len >= 0 ? packed_len : -1,
                            precision,
                            decimals,
                            PyBool_FromLong(!IS_NOT_NULL(self->fields[i].flags)),
                            self->fields[i].flags,
                            self->fields[i].table,
                            self->fields[i].org_name,
                            self->fields[i].org_table)))
            {
                Py_XDECREF(obj);
                mariadb_throw_exception(NULL, Mariadb_OperationalError, 0,
                         "Can't build descriptor record");
                return NULL;
            }
            PyTuple_SetItem(obj, i, desc);
        }
        return obj;
    }
    Py_RETURN_NONE;
}
/* }}} */

int MrdbCursor_fetchinternal(MrdbCursor *self)
{
    unsigned int field_count= self->field_count;
    MYSQL_ROW row;
    int rc;
    unsigned int i;

    self->fetched= 1;

    if (!self->is_text)
    {
        rc= mysql_stmt_fetch(self->stmt);
        if (rc == MYSQL_NO_DATA)
            return 1;
        return 0;
    }

    if (!(row= mysql_fetch_row(self->result)))
    {
        if (!self->is_buffered)
        {
            /* Clear Python-level active cursor tracking */
            if (self->connection) {
                PyObject *active = PyObject_GetAttrString((PyObject *)self->connection, "_active_streaming_result");
                const char *field_name = "_active_streaming_result";
                
                if (!active || PyErr_Occurred()) {
                    PyErr_Clear();
                    active = PyObject_GetAttrString((PyObject *)self->connection, "_active_async_cursor");
                    field_name = "_active_async_cursor";
                }
                
                if (active && active != Py_None && active == (PyObject *)self) {
                    PyObject_SetAttrString((PyObject *)self->connection, field_name, Py_None);
                }
                Py_XDECREF(active);
            }
            if (self->result)
            {
                mysql_free_result(self->result);
                self->result = NULL;
            }
        }
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

    /* Check if cursor is closed */
    if (self->closed)
    {
        mariadb_throw_exception(NULL, Mariadb_ProgrammingError, 0,
                "Cursor is closed");
        return NULL;
    }

    if (self->cursor_type == CURSOR_TYPE_READ_ONLY)
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
        Py_RETURN_NONE;
    }

    self->row_number++;
    if (!(row= mariadb_get_sequence_or_tuple(self)))
    {
        return NULL;
    }

    for (i= 0; i < field_count; i++)
    {
        ma_set_result_column_value(self, row, i);
    }
    return row;
}

static PyObject *MrdbCursor_seek(MrdbCursor *self, PyObject *pos)
{
    uint64_t new_position= 0;

    if (!CHECK_TYPE_NO_NONE(pos, &PyLong_Type)) {
        PyErr_SetString(PyExc_TypeError, "Parameter must be an integer value");
        return NULL;
    }

    new_position= (uint64_t)PyLong_AsUnsignedLongLong(pos);

    Py_BEGIN_ALLOW_THREADS;
    if (self->is_text)
        mysql_data_seek(self->result, new_position);
    else
        mysql_stmt_data_seek(self->stmt, new_position);
    Py_END_ALLOW_THREADS;

    Py_RETURN_NONE;
}

static PyObject *
mariadb_get_sequence_or_tuple(MrdbCursor *self)
{
    switch (self->result_format)
    {
        case RESULT_NAMED_TUPLE:
            return PyStructSequence_New(self->sequence_type);
        case RESULT_DICTIONARY:
            return PyDict_New();
        default:
            return PyTuple_New(self->field_count);
    }
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

    if (!self->is_text)
    {
        if (!self->stmt)
            Py_RETURN_NONE;
        Py_BEGIN_ALLOW_THREADS;
        rc= mysql_stmt_next_result(self->stmt);
        Py_END_ALLOW_THREADS;
    }
    else
    {
        if (self->result)
        {
            mysql_free_result(self->result);
            self->result= NULL;
        }
        Py_BEGIN_ALLOW_THREADS;
        rc= mysql_next_result(self->connection->mysql);
        Py_END_ALLOW_THREADS;
    }

    if (rc)
    {
        Py_RETURN_NONE;
    }
    if ((self->field_count= CURSOR_FIELD_COUNT(self)))
    {
        if (!MrdbCursor_InitResultSet(self))
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
    if (!self->statement)
        return PyLong_FromLongLong(-1);
    if (self->field_count)
        return PyLong_FromLongLong(self->row_count);
    return PyLong_FromLongLong(CURSOR_AFFECTED_ROWS(self));
}

static PyObject *
Mariadb_row_number(MrdbCursor *self)
{
    if (!self->field_count) {
        Py_RETURN_NONE;
    }
    return PyLong_FromLongLong(self->row_number);
}

static PyObject *
MrdbCursor_warnings(MrdbCursor *self)
{
    MARIADB_CHECK_STMT(self);

    return PyLong_FromLong((long)CURSOR_WARNING_COUNT(self));
}

static PyObject
*MrdbCursor_closed(MrdbCursor *self)
{
    if (self->closed || self->connection->mysql == NULL)
        Py_RETURN_TRUE;
    Py_RETURN_FALSE;
}

/* Stores the statement string and sets is_text=1, without sending.
   Used by the async path which cannot merge into _sync_execute_text. */
static PyObject *
MrdbCursor_set_text_statement(MrdbCursor *self, PyObject *stmt)
{
    const char *statement;
    Py_ssize_t statement_len = 0;

    statement = PyUnicode_AsUTF8AndSize(stmt, &statement_len);
    if (!statement)
        return NULL;

    if (!(self->statement &&
          self->statement_len == (size_t)statement_len &&
          memcmp(self->statement, statement, statement_len) == 0))
    {
        if (self->statement)
            PyMem_RawFree(self->statement);
        self->statement = PyMem_RawCalloc(statement_len + 1, 1);
        if (!self->statement)
            return PyErr_NoMemory();
        memcpy(self->statement, statement, statement_len);
        self->statement_len = statement_len;
    }
    self->is_text = 1;
    Py_RETURN_NONE;
}

/* Lightweight statement setter for binary protocol.
   Stores the statement string and param count without parsing. */
static PyObject *
MrdbCursor_set_statement(MrdbCursor *self, PyObject *args)
{
    PyObject *stmt;
    uint32_t paramcount = 0;
    const char *statement = NULL;
    Py_ssize_t statement_len = 0;

    if (!PyArg_ParseTuple(args, "O|I", &stmt, &paramcount))
        return NULL;

    statement = (char *)PyUnicode_AsUTF8AndSize(stmt, &statement_len);
    if (!statement)
        return NULL;

    if (self->statement)
    {
        uint32_t old_paramcount = self->paramcount;
        MrdbCursor_clearstmt(self);
        if (paramcount != old_paramcount)
        {
            MARIADB_FREE_MEM(self->params);
            MrdbCursor_FreeValues(self);
            MrdbCursor_FreeResultValues(self);
            MARIADB_FREE_MEM(self->bind);
        }
    }

    self->statement = PyMem_RawCalloc(statement_len + 1, 1);
    if (!self->statement)
        return PyErr_NoMemory();
    memcpy(self->statement, statement, statement_len);
    self->statement_len = statement_len;
    self->paramcount = paramcount;
    self->is_text = 0;

    Py_RETURN_NONE;
}

static PyObject *
MrdbCursor_execute_binary(MrdbCursor *self)
{
    int rc;
    unsigned char *buf= NULL;
    size_t buflen;
    MYSQL *db;

    MARIADB_CHECK_CONNECTION(self->connection, NULL);

    db = self->connection->mysql;
    ma_connection_consume_active_result(self->connection, self);
    if (!self->stmt &&
        !(self->stmt= mysql_stmt_init(self->connection->mysql)))
    {
        mariadb_throw_exception(self->connection->mysql, NULL, 0, NULL);
        goto error;
    }

    /* CONPY-164: reset array_size */
    self->array_size= 0;
    mysql_stmt_attr_set(self->stmt, STMT_ATTR_ARRAY_SIZE, &self->array_size);

    if (self->data && self->paramcount)
    {
        if (mariadb_check_execute_parameters(self, self->data))
            goto error;

        /* Load values */
        if (mariadb_param_update(self, self->params, 0))
            goto error;
    }

    if (self->reprepare)
    {
        mysql_stmt_attr_set(self->stmt, STMT_ATTR_CURSOR_TYPE, &self->cursor_type);
        mysql_stmt_attr_set(self->stmt, STMT_ATTR_PREBIND_PARAMS, &self->paramcount);
        mysql_stmt_attr_set(self->stmt, STMT_ATTR_CB_USER_DATA, (void *)self);
    }

    if (self->paramcount)
        mysql_stmt_bind_param(self->stmt, self->params);

    if (!(buf= self->connection->mysql->methods->db_execute_generate_request(self->stmt, &buflen, 1)))
        goto error;

    if ((rc= Mrdb_execute_direct(self, self->statement, self->statement_len)))
    {
        mariadb_throw_exception(self->stmt, NULL, 1, NULL);
        goto error;
    }
    
    self->field_count= mysql_stmt_field_count(self->stmt);
    Py_RETURN_NONE;

error:
    return NULL;
}

/* _sync_execute_text(sql_to_send [, original_statement])
   Sends the query AND stores the statement for cursor.statement + sets is_text=1.
   - sql_to_send: str or bytes — the (possibly substituted) SQL to send over the wire.
   - original_statement: optional str — the original SQL template for cursor.statement.
     If omitted (no params case), sql_to_send is used for both. */
static PyObject *
MrdbCursor_execute_text(MrdbCursor *self, PyObject *const *args, Py_ssize_t nargs)
{
    int rc;
    MYSQL *db;
    char *send_buf;
    Py_ssize_t send_len = 0;

    if (nargs < 1 || nargs > 2)
    {
        PyErr_SetString(PyExc_TypeError,
                        "_sync_execute_text requires 1 or 2 arguments");
        return NULL;
    }

    MARIADB_CHECK_CONNECTION(self->connection, NULL);

    PyObject *stmt = args[0];
    if (Py_TYPE(stmt) == &PyUnicode_Type)
    {
        send_buf = (char *)PyUnicode_AsUTF8AndSize(stmt, &send_len);
    } else if (Py_TYPE(stmt) == &PyBytes_Type)
    {
        PyBytes_AsStringAndSize(stmt, &send_buf, &send_len);
    }
    else {
        PyErr_SetString(PyExc_TypeError,
                        "First argument must be a string or bytes");
        return NULL;
    }

    /* Store original statement for cursor.statement property.
       If a second arg is given use it; otherwise derive from the first. */
    {
        const char *store_buf;
        Py_ssize_t store_len;

        if (nargs == 2)
        {
            store_buf = PyUnicode_AsUTF8AndSize(args[1], &store_len);
            if (!store_buf)
                return NULL;
        } else if (Py_TYPE(stmt) == &PyUnicode_Type)
        {
            store_buf = send_buf;
            store_len = send_len;
        } else {
            store_buf = NULL;
            store_len = 0;
        }

        if (store_buf)
        {
            /* Fast path: same statement already stored — skip alloc */
            if (!(self->statement &&
                  self->statement_len == (size_t)store_len &&
                  memcmp(self->statement, store_buf, store_len) == 0))
            {
                if (self->statement)
                    PyMem_RawFree(self->statement);
                self->statement = PyMem_RawCalloc(store_len + 1, 1);
                if (!self->statement)
                    return PyErr_NoMemory();
                memcpy(self->statement, store_buf, store_len);
                self->statement_len = store_len;
            }
        }
        self->is_text = 1;
    }

    db = self->connection->mysql;
    ma_connection_consume_active_result(self->connection, self);

    Py_BEGIN_ALLOW_THREADS;
    rc = mysql_send_query(db, send_buf, (long)send_len);
    Py_END_ALLOW_THREADS;

    if (rc)
    {
        mariadb_throw_exception(db, NULL, 0, NULL);
        return NULL;
    }
    Py_RETURN_NONE;
}

static PyObject *
MrdbCursor_readresponse(MrdbCursor *self)
{
    int rc;
    MYSQL *db;

    MARIADB_CHECK_CONNECTION(self->connection, NULL);

    db= self->connection->mysql;

    if (self->is_text)
    {
        Py_BEGIN_ALLOW_THREADS;
        rc= db->methods->db_read_query_result(db);
        Py_END_ALLOW_THREADS;

        if (rc)
        {
          mariadb_throw_exception(db, NULL, 0, NULL);
          return NULL;
        }
        self->field_count= mysql_field_count(self->connection->mysql);
    }
    Py_RETURN_NONE;
}

static PyObject *
MrdbCursor_execute_bulk(MrdbCursor *self)
{
    int rc;
    unsigned char *buf= NULL;
    size_t buflen;

    MARIADB_CHECK_STMT(self);

    if (PyErr_Occurred())
    {
        return NULL;
    }

    if (!self->data)
    {
        PyErr_SetString(PyExc_TypeError, "No data provided");
        return NULL;
    }

    ma_connection_consume_active_result(self->connection, self);

    if (!self->stmt)
    {
        if (!(self->stmt= mysql_stmt_init(self->connection->mysql)))
        {
            mariadb_throw_exception(self->connection->mysql, NULL, 0, NULL);
            goto error;
        }
    }
    if (mariadb_check_bulk_parameters(self, self->data))
        goto error;

    /* If the server doesn't support bulk execution (< 10.2.6),
       we need to call a fallback routine */
    if (self->reprepare)
    {
      mysql_stmt_attr_set(self->stmt, STMT_ATTR_PREBIND_PARAMS, &self->paramcount);
      mysql_stmt_attr_set(self->stmt, STMT_ATTR_CB_USER_DATA, (void *)self);
      mysql_stmt_attr_set(self->stmt, STMT_ATTR_CB_PARAM, mariadb_param_update);
    }
    mysql_stmt_attr_set(self->stmt, STMT_ATTR_ARRAY_SIZE, &self->array_size);

    mysql_stmt_bind_param(self->stmt, self->params);

    if (!(buf= self->connection->mysql->methods->db_execute_generate_request(self->stmt, &buflen, 1)))
    {
        mariadb_throw_exception(self->stmt, NULL, 1, NULL);
        goto error;
    }

    if ((rc= Mrdb_execute_direct(self, self->statement, self->statement_len)))
    {
         mariadb_throw_exception(self->stmt, NULL, 1, NULL);
         goto error;
    }

    if ((self->field_count= CURSOR_FIELD_COUNT(self)))
    {
        if (!MrdbCursor_InitResultSet(self))
        {
            return NULL;
        }
    } else
    {
      self->affected_rows= CURSOR_AFFECTED_ROWS(self);
      self->lastrow_id= CURSOR_INSERT_ID(self);
      MrdbCursor_FreeResultValues(self);
    }
    Py_RETURN_NONE;
error:
    MrdbCursor_clear(self, 0);
    return NULL;
}

static PyObject *
MrdbCursor_fetchrows(MrdbCursor *self, PyObject *rows)
{
    PyObject *List;
    unsigned int field_count= self->field_count;
    uint64_t row_count;

    MARIADB_CHECK_STMT_FETCH(self);

    if (!field_count)
    {
        mariadb_throw_exception(NULL, Mariadb_ProgrammingError, 0,
                "Cursor doesn't have a result set");
        return NULL;
    }

    if (!CHECK_TYPE_NO_NONE(rows, &PyLong_Type)) {
        PyErr_SetString(PyExc_TypeError, "Parameter must be an integer value");
        return NULL;
    }

    row_count= (uint64_t)PyLong_AsLongLong(rows);

    if (!(List= PyList_New(0)))
    {
        return NULL;
    }

    for (uint64_t i=0; i < row_count && !MrdbCursor_fetchinternal(self); i++)
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
            ma_set_result_column_value(self, Row, j);
        }
        PyList_Append(List, Row);
        /* CONPY-99: Decrement Row to prevent memory leak */
        Py_DECREF(Row);
    }
    self->row_count = self->row_number;
    return List;
}

static PyObject *
MrdbCursor_check_text_types(MrdbCursor *self)
{
  PyDateTime_IMPORT;
  Py_ssize_t ofs= 0;
  Py_ssize_t i;
  PyObject *obj;

  if (!self->data)
    Py_RETURN_NONE;

  if (PyDict_Check(self->data))
    Py_RETURN_NONE;

  for (i=0; i < PySequence_Size(self->data); i++)
  {
    if (PyTuple_Check(self->data))
       obj= PyTuple_GetItem(self->data, i);
    else
       obj= ListOrTuple_GetItem(self->data, i);
    if (PyBytes_Check(obj) ||
        PyByteArray_Check(obj) ||
        PyDate_Check(obj) ||
        PyTime_Check(obj))
      Py_RETURN_TRUE;
    /* Check for array.array (buffer objects that aren't bytes/bytearray) */
    {
      const char *tp_name = Py_TYPE(obj)->tp_name;
      if (tp_name && strcmp(tp_name, "array.array") == 0)
        Py_RETURN_TRUE;
    }
  }
  Py_RETURN_NONE;
}


/* Forward declarations for functions from mariadb_cursor.c */
extern PyObject *mariadb_get_sequence_or_tuple(MrdbCursor *self);
extern void ma_set_result_column_value(MrdbCursor *self, PyObject *row, uint32_t column);
extern void field_fetch_fromtext(MrdbCursor *self, char *data, unsigned int column);
extern int MrdbCursor_fetchinternal(MrdbCursor *self);

/* Fast path optimization: Cache common wait status values to reduce allocations */
static PyObject *wait_status_cache[8] = {NULL};

/* Initialize wait_status cache - call this during module initialization */
void MrdbCursor_init_wait_status_cache(void)
{
    for (int i = 0; i < 8; i++) {
        if (!wait_status_cache[i]) {
            wait_status_cache[i] = PyLong_FromLong(i);
        }
    }
}

/* Helper for async cursors to set field_count from connection */
PyObject *
MrdbCursor_set_field_count_from_connection(MrdbCursor *self, PyObject *args)
{
    MARIADB_CHECK_CONNECTION(self->connection, NULL);

    self->is_text = 1;

    /* Set field_count from connection
       Note: For stored procedures, mysql_field_count() returns 0 because it returns
       the field count of the CALL statement itself, not the first result set.
       In this case, Mrdb_GetFieldInfo() will still try to get the result and will
       update field_count if a result is available. */
    self->field_count = mysql_field_count(self->connection->mysql);

    Py_RETURN_NONE;
}

/* Async readresponse methods - non-blocking version of _readresponse */
static PyObject *
MrdbCursor_readresponse_start(MrdbCursor *self, PyObject *args)
{
    int status;
    int rc;
    MYSQL *db;

    MARIADB_CHECK_CONNECTION(self->connection, NULL);

    if (!self->is_text) {
        /* Only for text protocol */
        Py_RETURN_NONE;
    }

    db = self->connection->mysql;

    /* Start non-blocking read of query result */
    Py_BEGIN_ALLOW_THREADS;
    status = mysql_read_query_result_start(&rc, db);
    Py_END_ALLOW_THREADS;

    if (status == 0) {
        /* Completed immediately */
        if (rc) {
            mariadb_throw_exception(db, NULL, 0, NULL);
            return NULL;
        }
        self->field_count = mysql_field_count(self->connection->mysql);
        Py_RETURN_NONE;
    }

    /* Return status to indicate we need to wait */
    return PyLong_FromLong(status);
}

PyObject *
MrdbCursor_readresponse_cont(MrdbCursor *self, PyObject *args)
{
    int wait_status;
    int status;
    int rc;
    MYSQL *db;

    if (!PyArg_ParseTuple(args, "i", &wait_status))
        return NULL;

    MARIADB_CHECK_CONNECTION(self->connection, NULL);

    if (!self->is_text) {
        /* Only for text protocol */
        Py_RETURN_NONE;
    }

    db = self->connection->mysql;

    /* Continue non-blocking read of query result */
    Py_BEGIN_ALLOW_THREADS;
    status = mysql_read_query_result_cont(&rc, db, wait_status);
    Py_END_ALLOW_THREADS;

    if (status == 0) {
        /* Completed */
        if (rc) {
            mariadb_throw_exception(db, NULL, 0, NULL);
            return NULL;
        }
        self->field_count = mysql_field_count(self->connection->mysql);
        Py_RETURN_NONE;
    }

    /* Return status to indicate we need to continue waiting */
    return PyLong_FromLong(status);
}

/* Async fetch methods - reuse field_fetch_fromtext for type conversion */
PyObject *
MrdbCursor_fetch_row_cont(MrdbCursor *self, PyObject *args)
{
    MYSQL_ROW row;
    int wait_status;
    int status;
    unsigned int i;

    if (!PyArg_ParseTuple(args, "i", &wait_status))
        return NULL;

    if (!self->result) {
        PyErr_SetString(PyExc_RuntimeError, "No result set available");
        return NULL;
    }

    /* Continue non-blocking row fetch */
    Py_BEGIN_ALLOW_THREADS;
    status = mysql_fetch_row_cont(&row, self->result, wait_status);
    Py_END_ALLOW_THREADS;

    if (status == 0 && !row) {
        /* No more rows */
        Py_RETURN_NONE;
    }

    if (status == 0) {
        /* Row fetched - use field_fetch_fromtext for type conversion */
        PyObject *tuple = mariadb_get_sequence_or_tuple(self);
        if (!tuple)
            return NULL;

        for (i = 0; i < self->field_count; i++) {
            field_fetch_fromtext(self, row[i], i);
            if (PyErr_Occurred()) {
                Py_DECREF(tuple);
                return NULL;
            }
            ma_set_result_column_value(self, tuple, i);
        }
        return tuple;
    }

    /* Return status to indicate we need to continue waiting */
    return PyLong_FromLong(status);
}

/* Prepare statement for async execution (synchronous, but fast - no network I/O) */
PyObject *
MrdbCursor_prepare_stmt_only(MrdbCursor *self, PyObject *args)
{
    int rc;

    MARIADB_CHECK_CONNECTION(self->connection, NULL);

    /* Initialize statement if needed */
    if (!self->stmt && !(self->stmt = mysql_stmt_init(self->connection->mysql)))
    {
        mariadb_throw_exception(self->connection->mysql, NULL, 0, NULL);
        return NULL;
    }

    /* Reset array_size */
    self->array_size = 0;
    mysql_stmt_attr_set(self->stmt, STMT_ATTR_ARRAY_SIZE, &self->array_size);

    /* Check and load parameters if present */
    if (self->data && self->paramcount)
    {
        if (mariadb_check_execute_parameters(self, self->data))
            return NULL;

        if (mariadb_param_update(self, self->params, 0))
            return NULL;
    }

    /* Set statement attributes if repreparing */
    if (self->reprepare)
    {
        mysql_stmt_attr_set(self->stmt, STMT_ATTR_CURSOR_TYPE, &self->cursor_type);
        mysql_stmt_attr_set(self->stmt, STMT_ATTR_PREBIND_PARAMS, &self->paramcount);
        mysql_stmt_attr_set(self->stmt, STMT_ATTR_CB_USER_DATA, (void *)self);
    }

    /* Bind parameters */
    if (self->paramcount)
        mysql_stmt_bind_param(self->stmt, self->params);

    /* Clear pending result sets */
    MrdbCursor_clear_result(self);

    /* LIMITATION: mysql_stmt_prepare() is synchronous (no async version in MariaDB C API)
     * For non-BULK servers, we must call it here and accept the event loop blocking.
     * For BULK servers, execute_direct handles preparation asynchronously.
     *
     * This is acceptable because:
     * 1. Statement preparation is typically fast (SQL parsing + metadata)
     * 2. BULK-capable servers (MariaDB 10.2+) use async execute_direct instead
     * 3. The bulk of network I/O happens during execute and fetch, which are async
     */
    if (self->reprepare)
    {
        rc = mysql_stmt_prepare(self->stmt, self->statement,
                                (unsigned long)self->statement_len);
        if (rc)
        {
            mariadb_throw_exception(self->stmt, NULL, 1, NULL);
            return NULL;
        }

        /* Set field count after preparation */
        self->field_count = mysql_stmt_field_count(self->stmt);
    }

    Py_RETURN_NONE;
}

/* Async prepared statement execution methods */
PyObject *
MrdbCursor_stmt_execute_start(MrdbCursor *self, PyObject *args)
{
    int status;
    int rc;

    if (!self->stmt) {
        PyErr_SetString(PyExc_RuntimeError, "No prepared statement available");
        return NULL;
    }

    MARIADB_CHECK_CONNECTION(self->connection, NULL);

    /* Start non-blocking prepared statement execution */
    Py_BEGIN_ALLOW_THREADS;
    status = mysql_stmt_execute_start(&rc, self->stmt);
    Py_END_ALLOW_THREADS;

    if (status == 0) {
        /* FAST PATH: Completed immediately - no event loop trip needed */
        if (rc) {
            mariadb_throw_exception(self->stmt, NULL, 1, NULL);
            return NULL;
        }
        /* Set field count after execution */
        self->field_count = mysql_stmt_field_count(self->stmt);
        Py_RETURN_NONE;
    }

    /* Need to wait - return cached status object if possible */
    if (status > 0 && status < 8 && wait_status_cache[status]) {
        Py_INCREF(wait_status_cache[status]);
        return wait_status_cache[status];
    }

    return PyLong_FromLong(status);
}

PyObject *
MrdbCursor_stmt_execute_cont(MrdbCursor *self, PyObject *args)
{
    int wait_status;
    int status;
    int rc;

    if (!PyArg_ParseTuple(args, "i", &wait_status))
        return NULL;

    if (!self->stmt) {
        PyErr_SetString(PyExc_RuntimeError, "No prepared statement available");
        return NULL;
    }

    MARIADB_CHECK_CONNECTION(self->connection, NULL);

    /* Continue non-blocking statement execution */
    Py_BEGIN_ALLOW_THREADS;
    status = mysql_stmt_execute_cont(&rc, self->stmt, wait_status);
    Py_END_ALLOW_THREADS;

    if (status == 0) {
        /* Completed */
        if (rc) {
            mariadb_throw_exception(self->stmt, NULL, 1, NULL);
            return NULL;
        }
        /* Set field count after execution completes */
        self->field_count = mysql_stmt_field_count(self->stmt);
        Py_RETURN_NONE;
    }

    /* Return status to indicate we need to continue waiting */
    return PyLong_FromLong(status);
}

/* Async text protocol fetch methods */
PyObject *
MrdbCursor_fetch_row_start(MrdbCursor *self)
{
    MYSQL_ROW row;
    int status;
    unsigned int i;

    if (!self) {
        PyErr_SetString(PyExc_RuntimeError, "Cursor object is NULL");
        return NULL;
    }

    if (!self->connection) {
        PyErr_SetString(PyExc_RuntimeError, "Cursor connection is NULL");
        return NULL;
    }

    if (!self->result) {
        PyErr_SetString(PyExc_RuntimeError, "No result set available");
        return NULL;
    }

    if (!self->values) {
        PyErr_SetString(PyExc_RuntimeError, "Cursor not properly initialized - values array is NULL");
        return NULL;
    }

    /* Fetch row from result set */
    Py_BEGIN_ALLOW_THREADS;
    row = mysql_fetch_row(self->result);
    Py_END_ALLOW_THREADS;

    if (!row) {
        /* No more rows */
        Py_RETURN_NONE;
    }

    /* Mark that we've fetched data */
    self->fetched = 1;

    /* Convert row data from text format and store in self->values */
    for (i = 0; i < self->field_count; i++) {
        field_fetch_fromtext(self, row[i], i);
        if (PyErr_Occurred()) {
            return NULL;
        }
    }

    /* Create tuple/sequence to hold the row */
    PyObject *tuple = mariadb_get_sequence_or_tuple(self);
    if (!tuple)
        return NULL;

    /* Copy converted values from self->values to the tuple */
    for (i = 0; i < self->field_count; i++) {
        ma_set_result_column_value(self, tuple, i);
    }

    return tuple;
}

PyObject *
MrdbCursor_stmt_fetch_start(MrdbCursor *self)
{
    int status;
    int rc;

    if (!self->stmt) {
        PyErr_SetString(PyExc_RuntimeError, "No prepared statement available");
        return NULL;
    }

    MARIADB_CHECK_CONNECTION(self->connection, NULL);

    /* Start non-blocking prepared statement fetch */
    Py_BEGIN_ALLOW_THREADS;
    status = mysql_stmt_fetch_start(&rc, self->stmt);
    Py_END_ALLOW_THREADS;

    if (status == 0) {
        /* FAST PATH: Completed immediately - no event loop trip needed */
        if (rc == 0 || rc == MYSQL_DATA_TRUNCATED) {
            /* Row fetched successfully - data is already in self->values via callbacks */
            self->fetched = 1;

            /* Create tuple/sequence to hold the row */
            PyObject *tuple = mariadb_get_sequence_or_tuple(self);
            if (!tuple)
                return NULL;

            /* Copy converted values from self->values to the tuple */
            unsigned int i;
            for (i = 0; i < self->field_count; i++) {
                ma_set_result_column_value(self, tuple, i);
            }

            return tuple;
        } else if (rc == MYSQL_NO_DATA) {
            /* No more rows */
            Py_RETURN_NONE;
        } else {
            /* Error */
            mariadb_throw_exception(self->stmt, NULL, 1, NULL);
            return NULL;
        }
    }

    /* Need to wait - return cached status object if possible */
    if (status > 0 && status < 8 && wait_status_cache[status]) {
        Py_INCREF(wait_status_cache[status]);
        return wait_status_cache[status];
    }

    return PyLong_FromLong(status);
}

PyObject *
MrdbCursor_stmt_fetch_cont(MrdbCursor *self, PyObject *args)
{
    int wait_status;
    int status;
    int rc;

    if (!PyArg_ParseTuple(args, "i", &wait_status))
        return NULL;

    if (!self->stmt) {
        PyErr_SetString(PyExc_RuntimeError, "No prepared statement available");
        return NULL;
    }

    MARIADB_CHECK_CONNECTION(self->connection, NULL);

    /* Continue non-blocking statement fetch */
    Py_BEGIN_ALLOW_THREADS;
    status = mysql_stmt_fetch_cont(&rc, self->stmt, wait_status);
    Py_END_ALLOW_THREADS;

    if (status == 0) {
        /* Completed */
        if (rc == MYSQL_NO_DATA) {
            /* No more rows */
            Py_RETURN_NONE;
        }
        if (rc && rc != MYSQL_DATA_TRUNCATED) {
            mariadb_throw_exception(self->stmt, NULL, 1, NULL);
            return NULL;
        }

        /* Row fetched successfully - data is already in self->values via callbacks */
        self->fetched = 1;

        /* Create tuple/sequence to hold the row */
        PyObject *tuple = mariadb_get_sequence_or_tuple(self);
        if (!tuple)
            return NULL;

        /* Copy converted values from self->values to the tuple */
        unsigned int i;
        for (i = 0; i < self->field_count; i++) {
            ma_set_result_column_value(self, tuple, i);
        }

        return tuple;
    }

    /* Return status to indicate we need to continue waiting */
    return PyLong_FromLong(status);
}

/* Capsule destructor — called only if the capsule is GC'd without being attached */
static void
MrdbCursor_stmt_capsule_destructor(PyObject *capsule)
{
    MYSQL_STMT *stmt = (MYSQL_STMT *)PyCapsule_GetPointer(capsule, "MYSQL_STMT");
    if (stmt)
        mysql_stmt_close(stmt);
}

/* _detach_stmt(): drain results, wrap self->stmt in a PyCapsule, set stmt=NULL.
 * Does NOT call mysql_stmt_reset() to avoid a round-trip to the server. */
static PyObject *
MrdbCursor_detach_stmt(MrdbCursor *self)
{
    PyObject *capsule;

    if (!self->stmt)
        Py_RETURN_NONE;

    /* Drain any pending result sets to prevent "Commands out of sync" */
    Py_BEGIN_ALLOW_THREADS;
    if (mysql_stmt_field_count(self->stmt))
        mysql_stmt_free_result(self->stmt);
    while (mysql_stmt_next_result(self->stmt) == 0)
    {
        if (mysql_stmt_field_count(self->stmt))
            mysql_stmt_free_result(self->stmt);
    }
    Py_END_ALLOW_THREADS;

    capsule = PyCapsule_New((void *)self->stmt, "MYSQL_STMT",
                            MrdbCursor_stmt_capsule_destructor);
    if (!capsule)
        return NULL;

    self->stmt = NULL;
    return capsule;
}

/* _attach_stmt(capsule): unwrap MYSQL_STMT* from capsule, assign to self->stmt.
 * Always updates STMT_ATTR_CB_USER_DATA so the callback pointer is never stale. */
static PyObject *
MrdbCursor_attach_stmt(MrdbCursor *self, PyObject *capsule)
{
    MYSQL_STMT *stmt;

    if (!PyCapsule_CheckExact(capsule)) {
        PyErr_SetString(PyExc_TypeError, "_attach_stmt: expected a PyCapsule");
        return NULL;
    }

    stmt = (MYSQL_STMT *)PyCapsule_GetPointer(capsule, "MYSQL_STMT");
    if (!stmt)
        return NULL;

    /* Invalidate the destructor so the capsule no longer owns the stmt */
    if (PyCapsule_SetDestructor(capsule, NULL) < 0)
        return NULL;

    /* Close any existing stmt on this cursor */
    if (self->stmt) {
        Py_BEGIN_ALLOW_THREADS;
        mysql_stmt_close(self->stmt);
        Py_END_ALLOW_THREADS;
    }

    self->stmt = stmt;

    /* Always refresh CB_USER_DATA to prevent stale pointer segfault */
    mysql_stmt_attr_set(self->stmt, STMT_ATTR_CB_USER_DATA, (void *)self);

    Py_RETURN_NONE;
}

/* _close_stmt_no_close(): drain pending results, then free the local
 * MYSQL_STMT* without sending COM_STMT_CLOSE to the server.
 * Achieved by zeroing stmt_id before mysql_stmt_close(). */
static PyObject *
MrdbCursor_close_stmt_no_close(MrdbCursor *self)
{
    if (!self->stmt)
        Py_RETURN_NONE;

    Py_BEGIN_ALLOW_THREADS;
    /* Drain any pending result sets */
    if (mysql_stmt_field_count(self->stmt))
        mysql_stmt_free_result(self->stmt);
    while (mysql_stmt_next_result(self->stmt) == 0)
    {
        if (mysql_stmt_field_count(self->stmt))
            mysql_stmt_free_result(self->stmt);
    }
    /* Zero stmt_id so net_stmt_close() skips COM_STMT_CLOSE */
    self->stmt->stmt_id = 0;
    mysql_stmt_close(self->stmt);
    Py_END_ALLOW_THREADS;

    self->stmt = NULL;
    Py_RETURN_NONE;
}

/* Method definitions for async cursor methods */
PyMethodDef MrdbCursor_AsyncMethods[] = {
    {"_set_field_count_from_connection", (PyCFunction)MrdbCursor_set_field_count_from_connection,
        METH_NOARGS,
        "Set field_count from connection for async"},
    {"readresponse_start", (PyCFunction)MrdbCursor_readresponse_start,
        METH_NOARGS,
        "Start non-blocking read response"},
    {"readresponse_cont", (PyCFunction)MrdbCursor_readresponse_cont,
        METH_VARARGS,
        "Continue non-blocking read response"},
    {"fetch_row_start", (PyCFunction)MrdbCursor_fetch_row_start,
        METH_NOARGS,
        "Start non-blocking row fetch"},
    {"fetch_row_cont", (PyCFunction)MrdbCursor_fetch_row_cont,
        METH_VARARGS,
        "Continue non-blocking row fetch"},
    {"stmt_execute_start", (PyCFunction)MrdbCursor_stmt_execute_start,
        METH_NOARGS,
        "Start non-blocking prepared statement execution"},
    {"stmt_execute_cont", (PyCFunction)MrdbCursor_stmt_execute_cont,
        METH_VARARGS,
        "Continue non-blocking prepared statement execution"},
    {"stmt_fetch_start", (PyCFunction)MrdbCursor_stmt_fetch_start,
        METH_NOARGS,
        "Start non-blocking prepared statement fetch"},
    {"stmt_fetch_cont", (PyCFunction)MrdbCursor_stmt_fetch_cont,
        METH_VARARGS,
        "Continue non-blocking prepared statement fetch"},
    {"_detach_stmt", (PyCFunction)MrdbCursor_detach_stmt,
        METH_NOARGS,
        "Detach MYSQL_STMT into a PyCapsule for cache storage"},
    {"_attach_stmt", (PyCFunction)MrdbCursor_attach_stmt,
        METH_O,
        "Attach a cached MYSQL_STMT PyCapsule to this cursor"},
    {"_close_stmt_no_close", (PyCFunction)MrdbCursor_close_stmt_no_close,
        METH_NOARGS,
        "Free local MYSQL_STMT without sending COM_STMT_CLOSE"},
    {NULL, NULL, 0, NULL}  /* Sentinel */
};
