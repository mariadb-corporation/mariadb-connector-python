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
MrdbCursor_nextset(MrdbCursor *self);

static PyObject *
MrdbCursor_execute_binary(MrdbCursor *self);

static PyObject *
MrdbCursor_InitResultSet(MrdbCursor *self);

static PyObject *
MrdbCursor_execute_text(MrdbCursor *self, PyObject *args);

static PyObject *
MrdbCursor_fetchrows(MrdbCursor *self, PyObject *args);

static PyObject *
MrdbCursor_parse(MrdbCursor *self, PyObject *args);

static PyObject *
MrdbCursor_description(MrdbCursor *self);

static PyObject *
MrdbCursor_fetchone(MrdbCursor *self);

static PyObject *
MrdbCursor_seek(MrdbCursor *self,
                PyObject *args);

static PyObject *
MrdbCursor_execute_bulk(MrdbCursor *self);

void
field_fetch_fromtext(MrdbCursor *self, char *data, unsigned int column);

static PyObject *
MrdbCursor_readresponse(MrdbCursor *self);

PyObject *MrdbCursor_clear_result(MrdbCursor *self);

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
    ((a)->parseinfo.is_text ? mysql_field_count((a)->connection->mysql) : (a)->stmt ? mysql_stmt_field_count((a)->stmt) : 0)

#define CURSOR_WARNING_COUNT(a)\
    (((a)->parseinfo.is_text) ? (long)mysql_warning_count((a)->connection->mysql) : ((a)->stmt) ? (long)mysql_stmt_warning_count((a)->stmt) : 0L)

#define CURSOR_AFFECTED_ROWS(a)\
    (int64_t)((a)->parseinfo.is_text ? mysql_affected_rows((a)->connection->mysql) : (a)->stmt ? mysql_stmt_affected_rows((a)->stmt) : 0)

#define CURSOR_INSERT_ID(a)\
    ((a)->parseinfo.is_text ? mysql_insert_id((a)->connection->mysql) : (a)->stmt ? mysql_stmt_insert_id((a)->stmt) : 0)

#define CURSOR_NUM_ROWS(a)\
    ((a)->parseinfo.is_text ? mysql_num_rows((a)->result) : (a)->stmt ? mysql_stmt_num_rows((a)->stmt) : 0)

static char *mariadb_named_tuple_name= "mariadb.Row";
static char *mariadb_named_tuple_desc= "Named tupled row";
static PyObject *Mariadb_row_count(MrdbCursor *self);
static PyObject *Mariadb_row_number(MrdbCursor *self);
static PyObject *MrdbCursor_warnings(MrdbCursor *self);
static PyObject *MrdbCursor_closed(MrdbCursor *self);


static PyGetSetDef MrdbCursor_sets[]=
{
    {"description", (getter)MrdbCursor_description, NULL,
        cursor_description__doc__, NULL},
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
        METH_VARARGS,
        NULL},
    {"_nextset", (PyCFunction)MrdbCursor_nextset,
        METH_NOARGS,
        cursor_nextset__doc__},
    {"next", (PyCFunction)MrdbCursor_fetchone,
        METH_NOARGS,
        cursor_next__doc__},
    /* internal helper functions */
    {"_seek", (PyCFunction)MrdbCursor_seek,
        METH_VARARGS,
        NULL},
    {"_initresult", (PyCFunction)MrdbCursor_InitResultSet,
        METH_NOARGS,
        NULL},
    {"_parse", (PyCFunction)MrdbCursor_parse,
        METH_VARARGS,
        NULL},
    {"_readresponse", (PyCFunction)MrdbCursor_readresponse,
        METH_NOARGS,
         NULL},
    {"_execute_text", (PyCFunction)MrdbCursor_execute_text,
        METH_VARARGS,
        NULL},
    {"_execute_binary", (PyCFunction)MrdbCursor_execute_binary,
        METH_NOARGS,
        NULL},
    {"_execute_bulk", (PyCFunction)MrdbCursor_execute_bulk,
        METH_NOARGS,
        NULL},
    {"_initresult", (PyCFunction)MrdbCursor_InitResultSet,
        METH_NOARGS,
        NULL},
    {"_readresponse", (PyCFunction)MrdbCursor_readresponse,
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
        offsetof(MrdbCursor, parseinfo.statement),
        READONLY,
        cursor_statement__doc__},
    {"_paramstyle",
        T_UINT,
        offsetof(MrdbCursor, parseinfo.paramstyle),
        READONLY,
        MISSING_DOC},
    {"_reprepare",
        T_UINT,
        offsetof(MrdbCursor, reprepare),
        0,
        MISSING_DOC},
    {"_command",
        T_BYTE,
        offsetof(MrdbCursor, parseinfo.command),
        0,
        MISSING_DOC},
    {"_text",
        T_BOOL,
        offsetof(MrdbCursor, parseinfo.is_text),
        0,
        MISSING_DOC},
    {"_paramlist",
        T_OBJECT,
        offsetof(MrdbCursor, parseinfo.paramlist),
        READONLY,
        MISSING_DOC},
    {"_resulttype",
        T_UINT,
        offsetof(MrdbCursor, result_format),
        0,
        MISSING_DOC},
    {"_keys",
        T_OBJECT,
        offsetof(MrdbCursor, parseinfo.keys),
        READONLY,
        MISSING_DOC},
    {"paramcount",
        T_UINT,
        offsetof(MrdbCursor, parseinfo.paramcount),
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
static int MrdbCursor_initialize(MrdbCursor *self, PyObject *args,
        PyObject *kwargs)
{
    char *key_words[]= {"", "prefetch_size", "cursor_type", 
                        "prepared", "binary", NULL};
    PyObject *connection;
    unsigned long cursor_type= 0,
                  prefetch_rows= 0;
    uint8_t is_prepared= 0;
    uint8_t is_binary= 0;

    if (!self)
        return -1;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs,
                "O!|kkii", key_words, &MrdbConnection_Type, &connection,
                &prefetch_rows, &cursor_type, &is_prepared, &is_binary))
        return -1;

    if (!((MrdbConnection *)connection)->mysql)
    {
        mariadb_throw_exception(NULL, Mariadb_ProgrammingError, 0,
                "Connection isn't valid anymore");
        return -1;
    }

    if (self->cursor_type != CURSOR_TYPE_READ_ONLY &&
        self->cursor_type != CURSOR_TYPE_NO_CURSOR)
    {
        mariadb_throw_exception(NULL, Mariadb_DataError, 0,
                "Invalid value %ld for cursor_type", cursor_type);
        return -1;
    }

    self->connection= (MrdbConnection *)connection;

    self->is_prepared= is_prepared;
    self->parseinfo.is_text= 0;
    self->stmt= NULL;

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
    return 0;
}

static PyObject *MrdbCursor_repr(MrdbCursor *self)
{
    char cobj_repr[384];

    if (!self->closed)
        snprintf(cobj_repr, 384, "<mariadb.cursor at %p>", self);
    else
        snprintf(cobj_repr, 384, "<mariadb.cursor (closed) at %p>",
                self);
    return PyUnicode_FromString(cobj_repr);
}

PyTypeObject MrdbCursor_Type =
{
    PyVarObject_HEAD_INIT(NULL, 0)
    "mariadb.cursor",
    sizeof(MrdbCursor),
    0,
    (destructor)MrdbCursor_dealloc, /* tp_dealloc */
    0, /*tp_print*/
    0, /* tp_getattr */
    0, /* tp_setattr */
    0, /* PyAsyncMethods * */
    (reprfunc)MrdbCursor_repr, /* tp_repr */

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
    0,
    0,

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

void MrdbCursor_clearparseinfo(MrdbParseInfo *parseinfo)
{
  if (parseinfo->statement)
    MARIADB_FREE_MEM(parseinfo->statement);
  Py_XDECREF(parseinfo->keys);
  if (parseinfo->paramlist)
    Py_XDECREF(parseinfo->paramlist);
  memset(parseinfo, 0, sizeof(MrdbParseInfo));
}

/* {{{ MrdbCursor_clear_result(MrdbCursor *self)
   clear pending result sets
*/
PyObject *MrdbCursor_clear_result(MrdbCursor *self)
{
    if (!self->parseinfo.is_text &&
        self->stmt)
    {
        /* free current result */
        if (mysql_stmt_field_count(self->stmt))
            mysql_stmt_free_result(self->stmt);

        /* check if there are more pending result sets */
        while (mysql_stmt_next_result(self->stmt) == 0)
        {
            if (mysql_stmt_field_count(self->stmt))
                mysql_stmt_free_result(self->stmt);
        }
    } else if (self->parseinfo.is_text)
    {
        /* free current result */
        if (self->result)
        {
            mysql_free_result(self->result);
        }
        /* clear pending result sets */
        if (self->connection->mysql)
        {
            do {
                MYSQL_RES *res;
                if ((res= mysql_use_result(self->connection->mysql)))
                    mysql_free_result(res);
            } while (!mysql_next_result(self->connection->mysql));
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
  for (i= 0; i < self->parseinfo.paramcount; i++)
    if (self->value[i].free_me)
      MARIADB_FREE_MEM(self->value[i].buffer);
  MARIADB_FREE_MEM(self->value);
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

    if (!self->parseinfo.is_text && self->stmt) {
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
    MrdbCursor_clearparseinfo(&self->parseinfo);
    MARIADB_FREE_MEM(self->values);
    MARIADB_FREE_MEM(self->bind);
    MARIADB_FREE_MEM(self->statement);
    MARIADB_FREE_MEM(self->value);
    MARIADB_FREE_MEM(self->params);
}
/* }}} */

static void ma_set_result_column_value(MrdbCursor *self, PyObject *row, uint32_t column)
{
    switch (self->result_format) {
        case RESULT_NAMED_TUPLE:
            PyStructSequence_SET_ITEM(row, column, self->values[column]);
            break;
        case RESULT_DICTIONARY:
            PyDict_SetItemString(row, self->fields[column].name, self->values[column]); 
            Py_DECREF(self->values[column]); /* CONPY-119 */
            break;
        default:
            PyTuple_SET_ITEM(row, column, (self)->values[column]);
    }
}


/* {{{ ma_cursor_close 
   closes the statement handle of current cursor. After call to
   cursor_close the cursor can't be reused anymore
 */
static
void ma_cursor_close(MrdbCursor *self)
{
    if (!self->closed)
    {
        MrdbCursor_clear_result(self);
        if (!self->parseinfo.is_text && self->stmt)
        {
            /* Todo: check if all the cursor stuff is deleted (when using prepared
               statements this should be handled in mysql_stmt_close) */
            MARIADB_BEGIN_ALLOW_THREADS(self->connection);
            mysql_stmt_close(self->stmt);
            MARIADB_END_ALLOW_THREADS(self->connection);
            self->stmt= NULL;
        }
        MrdbCursor_clear(self, 0);

        if (!self->parseinfo.is_text && self->stmt)
        {
            mysql_stmt_close(self->stmt);
            self->stmt= NULL;
        }

        MrdbCursor_clearparseinfo(&self->parseinfo);
        self->closed= 1;
    }
}

static
PyObject * MrdbCursor_close(MrdbCursor *self)
{
    ma_cursor_close(self);
    Py_RETURN_NONE;
}
/* }}} */

/*{{{ MrDBCursor_dealloc */
void MrdbCursor_dealloc(MrdbCursor *self)
{
    if (self->connection && self->connection->mysql)
        ma_cursor_close(self);
    Py_TYPE(self)->tp_free((PyObject*)self);
}
/* }}} */

static int Mrdb_GetFieldInfo(MrdbCursor *self)
{
    self->row_number= 0;

    if (self->field_count)
    {
        if (self->parseinfo.is_text)
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

        self->fields= (self->parseinfo.is_text) ? mysql_fetch_fields(self->result) :
            mariadb_stmt_fetch_fields(self->stmt);

        if (self->result_format == RESULT_NAMED_TUPLE) {
            unsigned int i;
            PyStructSequence_Desc sequence_desc;

            if (!(self->sequence_fields= (PyStructSequence_Field *)
                        PyMem_RawCalloc(self->field_count + 1,
                            sizeof(PyStructSequence_Field))))
                return 1;
            sequence_desc.name= mariadb_named_tuple_name;
            sequence_desc.doc= mariadb_named_tuple_desc;
            sequence_desc.fields= self->sequence_fields;
            sequence_desc.n_in_sequence= self->field_count;


            for (i=0; i < self->field_count; i++)
            {
                self->sequence_fields[i].name= self->fields[i].name;
            }
            self->sequence_type= PyStructSequence_NewType(&sequence_desc);
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
    MARIADB_FREE_MEM(self->values);

    if (self->result)
    {
        mysql_free_result(self->result);
        self->result= NULL;
    }

    if (Mrdb_GetFieldInfo(self))
        return NULL;

    if (!(self->values= (PyObject**)PyMem_RawCalloc(self->field_count, sizeof(PyObject *))))
        return NULL;
    if (!self->parseinfo.is_text)
        mysql_stmt_attr_set(self->stmt, STMT_ATTR_CB_RESULT, field_fetch_callback);

    if (self->field_count)
    {
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

   MARIADB_BEGIN_ALLOW_THREADS(self->connection);
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
   MARIADB_END_ALLOW_THREADS(self->connection);
   return rc;
}

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
            enum enum_extended_field_type ext_type= mariadb_extended_field_type(&self->fields[i]);

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

            if (ext_type == EXT_TYPE_JSON)
                self->fields[i].type= MYSQL_TYPE_JSON;

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

static int MrdbCursor_fetchinternal(MrdbCursor *self)
{
    unsigned int field_count= self->field_count;
    MYSQL_ROW row;
    int rc;
    unsigned int i;

    self->fetched= 1;

    if (!self->parseinfo.is_text)
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

static PyObject *MrdbCursor_seek(MrdbCursor *self, PyObject *args)
{
    uint64_t new_position;    

    if (!PyArg_ParseTuple(args, "K", &new_position))
    {
        return NULL;
    }
    MARIADB_BEGIN_ALLOW_THREADS(self->connection);
    if (self->parseinfo.is_text)
        mysql_data_seek(self->result, new_position);
    else
        mysql_stmt_data_seek(self->stmt, new_position);
    MARIADB_END_ALLOW_THREADS(self->connection);

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

    MARIADB_BEGIN_ALLOW_THREADS(self->connection);
    if (!self->parseinfo.is_text)
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
    MARIADB_END_ALLOW_THREADS(self->connection);

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
    if (!self->parseinfo.statement)
        return PyLong_FromLongLong(-1);
    if (self->field_count)
        return PyLong_FromLongLong(CURSOR_NUM_ROWS(self));
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

static PyObject *
MrdbCursor_parse(MrdbCursor *self, PyObject *args)
{
    const char *statement= NULL;
    Py_ssize_t statement_len= 0;
    MrdbParser *parser= NULL;
    char errmsg[128];
    uint32_t old_paramcount= 0;

    if (self->parseinfo.statement)
    {
      old_paramcount= self->parseinfo.paramcount;
      MrdbCursor_clearparseinfo(&self->parseinfo);
    }
 
    if (!PyArg_ParseTuple(args, "s#|Ob", &statement, &statement_len))
    {
        return NULL;
    }

    if (!(parser= MrdbParser_init(self->connection->mysql, statement, statement_len)))
    {
        mariadb_throw_exception(NULL, Mariadb_ProgrammingError, 0,
                "Can't initialize parser.");
        return NULL;
    }

    if (MrdbParser_parse(parser, 0, errmsg, 128))
    {
        MrdbParser_end(parser);
        PyErr_SetString(Mariadb_ProgrammingError, errmsg);
        return NULL;
    }

    /* cleanup and save some parser stuff */
    if (parser->param_count && parser->param_count != old_paramcount)
    {
      MARIADB_FREE_MEM(self->params);
      MrdbCursor_FreeValues(self);
      MARIADB_FREE_MEM(self->values);
      MARIADB_FREE_MEM(self->bind);
    }
    self->parseinfo.paramcount= parser->param_count;
    self->parseinfo.paramstyle= parser->paramstyle;
    if (self->parseinfo.statement)
        PyMem_RawFree(self->parseinfo.statement);
    self->parseinfo.statement=  PyMem_RawCalloc(parser->statement.length + 1, 1);
    memcpy(self->parseinfo.statement, parser->statement.str, parser->statement.length);
    self->parseinfo.statement_len= parser->statement.length;
    self->parseinfo.paramlist= parser->param_list;
    parser->param_list= NULL;
    self->parseinfo.is_text= (parser->command == SQL_NONE || parser->command == SQL_OTHER);
    self->parseinfo.command= parser->command;

    if (parser->paramstyle == PYFORMAT && parser->keys)
    {
        PyObject *tmp= PyTuple_New(parser->param_count);
        for (uint32_t i= 0; i < parser->param_count; i++)
        {
            PyObject *key;
            key= PyUnicode_FromString(parser->keys[i].str);
            PyTuple_SetItem(tmp, i, key);
        }
        self->parseinfo.keys= tmp;
    }
    MrdbParser_end(parser);

    Py_RETURN_NONE;
}

static PyObject *
MrdbCursor_execute_binary(MrdbCursor *self)
{
    int rc;
    unsigned char *buf= NULL;
    size_t buflen;

    MARIADB_CHECK_CONNECTION(self->connection, NULL);

    if (!self->stmt &&
        !(self->stmt= mysql_stmt_init(self->connection->mysql)))
    {
        mariadb_throw_exception(self->connection->mysql, NULL, 0, NULL);
        goto error;
    }

    /* CONPY-164: reset array_size */
    self->array_size= 0;
    mysql_stmt_attr_set(self->stmt, STMT_ATTR_ARRAY_SIZE, &self->array_size);

    if (self->data && self->parseinfo.paramcount)
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
        mysql_stmt_attr_set(self->stmt, STMT_ATTR_PREBIND_PARAMS, &self->parseinfo.paramcount);
        mysql_stmt_attr_set(self->stmt, STMT_ATTR_CB_USER_DATA, (void *)self);
    }

    if (self->parseinfo.paramcount)
        mysql_stmt_bind_param(self->stmt, self->params);

    if (!(buf= self->connection->mysql->methods->db_execute_generate_request(self->stmt, &buflen, 1)))
        goto error;

    if ((rc= Mrdb_execute_direct(self, self->parseinfo.statement, self->parseinfo.statement_len)))
    {
        mariadb_throw_exception(self->connection->mysql, NULL, 0, NULL);
        goto error;
    }
    
    self->field_count= mysql_stmt_field_count(self->stmt);
    Py_RETURN_NONE;

error:
    return NULL;
}

static PyObject *
MrdbCursor_execute_text(MrdbCursor *self, PyObject *args)
{
    int rc;
    MYSQL *db;
    char *statement;
    size_t statement_len;

    MARIADB_CHECK_CONNECTION(self->connection, NULL);

    if (!PyArg_ParseTuple(args, "s#", &statement, &statement_len))
    {
        return NULL;
    }

    db= self->connection->mysql;

    MARIADB_BEGIN_ALLOW_THREADS(self->connection);
    rc= mysql_send_query(db, statement, (long)statement_len);
    MARIADB_END_ALLOW_THREADS(self->connection);

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

    if (self->parseinfo.is_text)
    {
        MARIADB_BEGIN_ALLOW_THREADS(self->connection);
        rc= db->methods->db_read_query_result(db);
        MARIADB_END_ALLOW_THREADS(self->connection);

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
      mysql_stmt_attr_set(self->stmt, STMT_ATTR_PREBIND_PARAMS, &self->parseinfo.paramcount);
      mysql_stmt_attr_set(self->stmt, STMT_ATTR_CB_USER_DATA, (void *)self);
      mysql_stmt_attr_set(self->stmt, STMT_ATTR_CB_PARAM, mariadb_param_update);
    }
    mysql_stmt_attr_set(self->stmt, STMT_ATTR_ARRAY_SIZE, &self->array_size);

    mysql_stmt_bind_param(self->stmt, self->params);

    if (!(buf= self->connection->mysql->methods->db_execute_generate_request(self->stmt, &buflen, 1)))
        goto error;

    if ((rc= Mrdb_execute_direct(self, self->parseinfo.statement, self->parseinfo.statement_len)))
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
      MARIADB_FREE_MEM(self->values);
    }
    Py_RETURN_NONE;
error:
    MrdbCursor_clear(self, 0);
    return NULL;
}

static PyObject *
MrdbCursor_fetchrows(MrdbCursor *self, PyObject *args)
{
    PyObject *List;
    unsigned int field_count= self->field_count;
    uint64_t row_count;

    MARIADB_CHECK_STMT(self);

    if (!PyArg_ParseTuple(args, "K", &row_count))
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
    self->row_count= CURSOR_NUM_ROWS(self);
    return List;
}

