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

#include <mariadb_python.h>

static void MrdbCursor_dealloc(MrdbCursor *self);
static PyObject *MrdbCursor_close(MrdbCursor *self);
static PyObject *MrdbCursor_execute(MrdbCursor *self,
                                 PyObject *args, PyObject *kwargs);
static PyObject *MrdbCursor_nextset(MrdbCursor *self);
static PyObject *MrdbCursor_executemany(MrdbCursor *self,
                                     PyObject *args);
static PyObject *MrdbCursor_description(MrdbCursor *self);
static PyObject *MrdbCursor_fetchall(MrdbCursor *self);
static PyObject *MrdbCursor_fetchone(MrdbCursor *self);
static PyObject *MrdbCursor_fetchmany(MrdbCursor *self,
                                     PyObject *args,
                                     PyObject *kwargs);
static PyObject *MrdbCursor_scroll(MrdbCursor *self,
                                       PyObject *args,
                                       PyObject *kwargs);
static PyObject *MrdbCursor_fieldcount(MrdbCursor *self);
void field_fetch_callback(void *data, unsigned int column, unsigned char **row);
static PyObject *mariadb_get_sequence_or_tuple(MrdbCursor *self);

/* todo: write more documentation, this is just a placeholder */
static char mariadb_cursor_documentation[] =
"Returns a MariaDB cursor object";

#define MARIADB_SET_SEQUENCE_OR_TUPLE_ITEM(self, row, column)\
if ((self)->is_named_tuple)\
  PyStructSequence_SET_ITEM((row), (column), (self)->values[(column)]);\
else\
  PyTuple_SET_ITEM((row), (column), (self)->values[(column)]);\


static char *mariadb_named_tuple_name= "Row";
static char *mariadb_named_tuple_desc= "Named tupled row";
static PyObject *Mariadb_no_operation(MrdbCursor *,
                                      PyObject *);
static PyObject *Mariadb_row_count(MrdbCursor *self);
static PyObject *MrdbCursor_warnings(MrdbCursor *self);

static PyGetSetDef MrdbCursor_sets[]=
{
  {"rowcount", (getter)Mariadb_row_count, NULL, "doc", NULL},
  {"warnings", (getter)MrdbCursor_warnings, NULL,
   "Number of warnings which were produced from last execute() call", NULL},
  {NULL}
};

static PyMethodDef MrdbCursor_Methods[] =
{
  /* PEP-249 methods */
  {"close", (PyCFunction)MrdbCursor_close,
    METH_NOARGS,
    "Closes an open Cursor"},
  {"execute", (PyCFunction)MrdbCursor_execute,
     METH_VARARGS | METH_KEYWORDS,
     "Executes a SQL statement"},
  {"executemany", (PyCFunction)MrdbCursor_executemany,
     METH_VARARGS,
     "Executes a SQL statement by passing a list of values"},
  {"fetchall", (PyCFunction)MrdbCursor_fetchall,
    METH_NOARGS,
    "Fetches all rows of a result set"},
  {"fetchone", (PyCFunction)MrdbCursor_fetchone,
    METH_NOARGS,
    "Fetches the next row of a result set"},
  {"fetchmany", (PyCFunction)MrdbCursor_fetchmany,
    METH_VARARGS | METH_KEYWORDS,
    "Fetches multiple rows of a result set"},
  {"fieldcount", (PyCFunction)MrdbCursor_fieldcount,
    METH_NOARGS,
    "Returns number of columns in current result set"},
  {"nextset", (PyCFunction)MrdbCursor_nextset,
   METH_NOARGS,
   "Will make the cursor skip to the next available result set, discarding any remaining rows from the current set."},
  {"setinputsizes", (PyCFunction)Mariadb_no_operation,
    METH_VARARGS,
    "Required by PEP-249. Does nothing in MariaDB Connector/Python"},
  {"setoutputsize", (PyCFunction)Mariadb_no_operation,
    METH_VARARGS,
    "Required by PEP-249. Does nothing in MariaDB Connector/Python"},
  {"callproc", (PyCFunction)Mariadb_no_operation,
    METH_VARARGS,
    "Required by PEP-249. Does nothing in MariaDB Connector/Python, use the execute method with syntax 'CALL {procedurename}' instead"},
  {"next", (PyCFunction)MrdbCursor_fetchone,
    METH_NOARGS,
    "Return the next row from the currently executing SQL statement using the same semantics as .fetchone()."},
  {"scroll", (PyCFunction)MrdbCursor_scroll,
    METH_VARARGS | METH_KEYWORDS,
    "Scroll the cursor in the result set to a new position according to mode"},
  {NULL} /* always last */
};

static struct PyMemberDef MrdbCursor_Members[] =
{
  {"connection",
   T_OBJECT,
   offsetof(MrdbCursor, connection),
   READONLY,
   "Reference to the connection object on which the cursor was created"},
  {"statement",
   T_STRING,
   offsetof(MrdbCursor, statement),
   READONLY,
   "The last executed statement"},
  {"description",
    T_OBJECT,
    offsetof(MrdbCursor, description),
    READONLY,
    "This read-only attribute is a sequence of 8-item sequences. Each of these sequences contains information describing one result column"},
  {"lastrowid",
   T_LONG,
   offsetof(MrdbCursor, lastrowid),
   READONLY,
   "row id of the last modified (inserted) row"},
  {"buffered",
   T_BYTE,
   offsetof(MrdbCursor, is_buffered),
   0,
   "Stores the entire result set in memory"},
  {"rownumber",
   T_LONG,
   offsetof(MrdbCursor, row_number),
   READONLY,
   "Current row number in result set"},
  {"arraysize",
   T_LONG,
   offsetof(MrdbCursor, row_array_size),
   0,
   "the number of rows to fetch"},
   {NULL}
};

/* {{{ MrdbCursor_initialize
   Cursor initialization

   Optional keywprds:
     named_tuple (Boolean): return rows as named tuple instead of tuple
     prefetch_size:         Prefetch size for readonly cursors
     cursor_type:           Type of cursor: CURSOR_TYPE_READONLY or CURSOR_TYPE_NONE (default)
*/
static int MrdbCursor_initialize(MrdbCursor *self, PyObject *args,
                                     PyObject *kwargs)
{
  char *key_words[]= {"", "named_tuple", "prefetch_size", "cursor_type", NULL};
  PyObject *connection;
  uint8_t is_named_tuple= 0;
  unsigned long cursor_type= 0,
                prefetch_rows= 0;

  if (!self)
    return -1;

  if (!PyArg_ParseTupleAndKeywords(args, kwargs,
        "O!|bkk", key_words, &MrdbConnection_Type, &connection,
        &is_named_tuple, &prefetch_rows, &cursor_type))

  Py_INCREF(connection);
  self->connection= (MrdbConnection *)connection;
  self->is_buffered= self->connection->is_buffered;

  if (cursor_type != CURSOR_TYPE_READ_ONLY &&
      cursor_type != CURSOR_TYPE_NO_CURSOR)
  {
    mariadb_throw_exception(NULL, Mariadb_DataError, 0,
                            "Invalid value %ld for cursor_type", cursor_type);
    return -1;
  }

	if (!(self->stmt = mysql_stmt_init(self->connection->mysql)))
  {
    mariadb_throw_exception(self->connection->mysql, Mariadb_OperationalError, 0, NULL);
		return -1;
	}

  self->cursor_type= cursor_type;
  self->prefetch_rows= prefetch_rows;
  self->is_named_tuple= is_named_tuple;
  self->row_array_size= 1;

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
	"mariadb.cursor",
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
	0, /* (getiterfunc) tp_iter */
	0, /* (iternextfunc) tp_iternext */

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

/* {{{ MrdbCursor_isprepared
  If the same statement was executed before, we don't need to
  reprepare it and can just execute it.
*/
static uint8_t MrdbCursor_isprepared(MrdbCursor *self,
                                     const char *statement,
                                     size_t statement_len)
{
  if (self->statement)
  {
    if (!memcmp(statement, self->statement, statement_len))
    {
      enum mysql_stmt_state state;
      mysql_stmt_attr_get(self->stmt, STMT_ATTR_STATE, &state);
      if (state >= MYSQL_STMT_PREPARED)
        return 1;
    }
  }
  return 0;
}
/* }}} */

/* {{{ MrdbCursor_clear
   Resets statement attributes  and frees
   associated memory
*/
static
void MrdbCursor_clear(MrdbCursor *self)
{
  if (self->stmt) { 
    uint32_t val= 0;
    mysql_stmt_attr_set(self->stmt, STMT_ATTR_USER_DATA, 0);
    mysql_stmt_attr_set(self->stmt, STMT_ATTR_PARAM_READ, 0);
    mysql_stmt_attr_set(self->stmt, STMT_ATTR_FIELD_FETCH_CALLBACK, 0);
    mysql_stmt_attr_set(self->stmt, STMT_ATTR_ARRAY_SIZE, &val);
    mysql_stmt_attr_set(self->stmt, STMT_ATTR_PREBIND_PARAMS, &val);
  }

  MARIADB_FREE_MEM(self->sequence_fields);
  MARIADB_FREE_MEM(self->fields);
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
  if (self->stmt)
  {
    /* Todo: check if all the cursor stuff is deleted (when using prepared
       statemnts this should be handled in mysql_close) */
    Py_BEGIN_ALLOW_THREADS
    mysql_stmt_close(self->stmt);
    Py_END_ALLOW_THREADS
    self->stmt= NULL;
  }
  MrdbCursor_clear(self);
}

static
PyObject * MrdbCursor_close(MrdbCursor *self)
{
  ma_cursor_close(self);
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
  int statement_len= 0;
  int rc= 0;
  uint8_t is_buffered= 0;
  static char *key_words[]= {"", "", "buffered", NULL};

  MARIADB_CHECK_STMT(self);
  if (PyErr_Occurred())
    return NULL;

  if (!PyArg_ParseTupleAndKeywords(args, kwargs,
        "s#|O!$b", key_words, &statement, &statement_len, &PyTuple_Type, &Data,
        &is_buffered))
    return NULL;

  /* defaukt was set to 0 before */
  self->is_buffered= is_buffered;

  /* Check if statement is already prepared */
  if (!(self->is_prepared= MrdbCursor_isprepared(self, statement, statement_len)))
  {
    MrdbCursor_clear(self);
    self->statement= PyMem_RawMalloc(statement_len + 1);
    strncpy(self->statement, statement, statement_len);
    self->statement[statement_len]= 0;
  }

  if (Data)
  {
    self->array_size= 0;
    self->data= Data;
    if (mariadb_check_execute_parameters(self, Data))
      goto error;

    self->data= Data;

    /* Load values */
    if (mariadb_param_update(self, self->params, 0))
      goto error;
  }
  if (!self->is_prepared)
  {
    mysql_stmt_attr_set(self->stmt, STMT_ATTR_PREBIND_PARAMS, &self->param_count);
    mysql_stmt_attr_set(self->stmt, STMT_ATTR_USER_DATA, (void *)self);
    mysql_stmt_bind_param(self->stmt, self->params);

    Py_BEGIN_ALLOW_THREADS;
    if (!MARIADB_FEATURE_SUPPORTED(self->stmt->mysql, 100206))
    {
      rc= mysql_stmt_prepare(self->stmt, statement, statement_len);
      if (!rc)
        rc= mysql_stmt_execute(self->stmt);
    }
    else
      rc= mariadb_stmt_execute_direct(self->stmt, statement, statement_len);
    Py_END_ALLOW_THREADS;

    if (rc)
    {
      /* in case statement is not supported via binary protocol, we try
         to run the statement with text protocol */
      if (mysql_stmt_errno(self->stmt) == ER_UNSUPPORTED_PS)
      {
        Py_BEGIN_ALLOW_THREADS;
        rc= mysql_real_query(self->stmt->mysql, statement, statement_len);
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
    Py_BEGIN_ALLOW_THREADS;
    rc= mysql_stmt_execute(self->stmt);
    Py_END_ALLOW_THREADS;
    if (rc)
    {
      mariadb_throw_exception(self->stmt, NULL, 1, NULL);
      goto error;
    }
  }
  /* save insert id */
  self->lastrowid= mysql_stmt_insert_id(self->stmt);

  /* reset row number */
  self->row_number= 0;
  if (mysql_stmt_field_count(self->stmt))
  {
    MYSQL_RES *res= mysql_stmt_result_metadata(self->stmt);
    MYSQL_FIELD *fields= mysql_fetch_fields(res);

    if (self->is_buffered)
    {
      if (mysql_stmt_store_result(self->stmt))
      {
        mariadb_throw_exception(self->stmt, NULL, 1, NULL);
        goto error;
      }
      self->affected_rows= mysql_stmt_num_rows(self->stmt);
    }

    /* store metadata field information */
    if (!(self->fields= (MYSQL_FIELD *)PyMem_RawCalloc(mysql_stmt_field_count(self->stmt), sizeof(MYSQL_FIELD))))
      goto error;
    memcpy(self->fields, fields, sizeof(MYSQL_FIELD) * mysql_stmt_field_count(self->stmt));
    mysql_free_result(res);
    if (self->is_named_tuple) {
      uint32_t i;
      if (!(self->sequence_fields= (PyStructSequence_Field *)
             PyMem_RawCalloc(mysql_stmt_field_count(self->stmt) + 1,
                             sizeof(PyStructSequence_Field))))
        goto error;
      self->sequence_desc.name= mariadb_named_tuple_name;
      self->sequence_desc.doc= mariadb_named_tuple_desc;
      self->sequence_desc.fields= self->sequence_fields;
      self->sequence_desc.n_in_sequence= mysql_stmt_field_count(self->stmt);

      for (i=0; i < mysql_stmt_field_count(self->stmt); i++)
      {
        self->sequence_fields[i].name= self->fields[i].name;
      }
      self->sequence_type= PyMem_RawCalloc(1,sizeof(PyTypeObject));
      PyStructSequence_InitType(self->sequence_type, &self->sequence_desc);
    }
    if (!(self->values= (PyObject**)PyMem_RawCalloc(mysql_stmt_field_count(self->stmt), sizeof(PyObject *))))
      goto error;
    mysql_stmt_attr_set(self->stmt, STMT_ATTR_FIELD_FETCH_CALLBACK, field_fetch_callback);
    self->description= MrdbCursor_description(self);
  }
  else {
    Py_INCREF(Py_None);
    self->description= Py_None;
  }
end:
  MARIADB_FREE_MEM(self->value);
  Py_RETURN_NONE;
error:
  MrdbCursor_clear(self);
  return NULL;
}
/* }}} */

/* {{{ MrdbCursor_fieldcount() */
PyObject *MrdbCursor_fieldcount(MrdbCursor *self)
{
  MARIADB_CHECK_STMT(self);
  if (PyErr_Occurred())
    return NULL;

  return PyLong_FromLong((long)mysql_stmt_field_count(self->stmt));
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

  MARIADB_CHECK_STMT(self);
  if (PyErr_Occurred())
    return NULL;

  if (self->fields && mysql_stmt_field_count(self->stmt))
  {
    uint32_t i;

    if (!(obj= PyTuple_New(mysql_stmt_field_count(self->stmt))))
      return NULL;

    for (i=0; i < mysql_stmt_field_count(self->stmt); i++)
    {
      PyObject *desc;
      if (!(desc= Py_BuildValue("(sIIIIIII)",
                                self->fields[i].name,
                                self->fields[i].type,
                                self->fields[i].max_length,
                                self->fields[i].length,
                                self->fields[i].length,
                                self->fields[i].decimals,
                                !IS_NOT_NULL(self->fields[i].flags),
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

/* {{{ MrdbCursor_fetchone
   PEP-249 fetchone() method
*/
static
PyObject *MrdbCursor_fetchone(MrdbCursor *self)
{
  PyObject *row;
  uint32_t i;

  MARIADB_CHECK_STMT(self);
  if (PyErr_Occurred())
    return NULL;

  if (!mysql_stmt_field_count(self->stmt))
  {
    mariadb_throw_exception(NULL, Mariadb_ProgrammingError, 0,
                            "Cursor doesn't have a result set");
    return NULL;
  }
  if (mysql_stmt_fetch(self->stmt))
  {
    Py_INCREF(Py_None);
    return Py_None;
  }
  self->row_number++;
  if (!(row= mariadb_get_sequence_or_tuple(self)))
    return NULL;
  for (i= 0; i < mysql_stmt_field_count(self->stmt); i++)
  {
    MARIADB_SET_SEQUENCE_OR_TUPLE_ITEM(self, row, i);
  }
  return row;
}
/* }}} */

/* {{{ MrdbCursor_scroll
   PEP-249: (optional) scroll() method

   Parameter: value
              mode=[relative(default),absolute]

   Todo: support for forward only cursor
*/
static
PyObject *MrdbCursor_scroll(MrdbCursor *self, PyObject *args,
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
    return NULL;

  if (!mysql_stmt_field_count(self->stmt))
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
    return NULL;

  if (!(position= PyLong_AsLong(Pos)))
  {
    mariadb_throw_exception(NULL, Mariadb_DataError, 0,
                            "Invalid position value 0");
    return NULL;
  }

  if (modestr != NULL)
  {
    while (scroll_modes[mode]) {
      if (!strcmp(scroll_modes[mode], modestr))
        break;
      mode++;
    };
  } else
    mode= 0;

  if (!scroll_modes[mode]) {
    mariadb_throw_exception(NULL, Mariadb_DataError, 0,
                            "Invalid mode '%s'", modestr);
    return NULL;
  }

  if (!mode) {
    new_position= self->row_number + position;
    if (new_position < 0 || new_position > mysql_stmt_num_rows(self->stmt))
    {
      mariadb_throw_exception(NULL, Mariadb_DataError, 0,
                            "Position value is out of range");
      return NULL;
    }
  } else
    new_position= position; /* absolute */

  mysql_stmt_data_seek(self->stmt, new_position);
  self->row_number= new_position;
  Py_INCREF(Py_None);
  return Py_None;
}
/*}}}*/

/* {{{ MrdbCursor_fetchmany
    PEP-249 fetchmany() method

    Optional parameters: size
*/
static
PyObject *MrdbCursor_fetchmany(MrdbCursor *self, PyObject *args,
                                   PyObject *kwargs)
{
  PyObject *List= NULL;
  uint32_t i;
  unsigned long rows= 0;
  static char *kw_list[]= {"size", NULL};

  MARIADB_CHECK_STMT(self);
  if (PyErr_Occurred())
    return NULL;

  if (!mysql_stmt_field_count(self->stmt))
  {
    mariadb_throw_exception(0, Mariadb_ProgrammingError, 0,
                            "Cursor doesn't have a result set");
    return NULL;
  }

  if (!PyArg_ParseTupleAndKeywords(args, kwargs,
    "|l:fetchmany", kw_list, &rows))
    return NULL;

  if (!rows)
    rows= self->row_array_size;
  if (!(List= PyList_New(0)))
    return NULL;

  /* if rows=0, return an empty list */
  if (!rows)
    return List;

  for (i=0; i < rows; i++)
  {
    uint32_t j;
    PyObject *Row;
    if (mysql_stmt_fetch(self->stmt))
      goto end;
    self->affected_rows= mysql_stmt_num_rows(self->stmt);
    if (!(Row= mariadb_get_sequence_or_tuple(self)))
      return NULL;
    for (j=0; j < mysql_stmt_field_count(self->stmt); j++)
      MARIADB_SET_SEQUENCE_OR_TUPLE_ITEM(self, Row, j);
    PyList_Append(List, Row);
  }
end:
  return List;
}

static PyObject *mariadb_get_sequence_or_tuple(MrdbCursor *self)
{
  if (self->is_named_tuple)
    return PyStructSequence_New(self->sequence_type);
  else
    return PyTuple_New(mysql_stmt_field_count(self->stmt));
}
/* }}} */

/* {{{ MrdbCursor_fetchall()
    PEP-249 fetchall() method */
static
PyObject *MrdbCursor_fetchall(MrdbCursor *self)
{
  PyObject *List;
  MARIADB_CHECK_STMT(self);
  if (PyErr_Occurred())
    return NULL;

  if (!mysql_stmt_field_count(self->stmt))
  {
    mariadb_throw_exception(NULL, Mariadb_ProgrammingError, 0,
                            "Cursor doesn't have a result set");
    return NULL;
  }

  if (!(List= PyList_New(0)))
    return NULL;
  while (!mysql_stmt_fetch(self->stmt))
  {
    uint32_t j;
    PyObject *Row;

    self->row_number++;

    if (!(Row= mariadb_get_sequence_or_tuple(self)))
      return NULL;

    for (j=0; j < mysql_stmt_field_count(self->stmt); j++)
    {
      MARIADB_SET_SEQUENCE_OR_TUPLE_ITEM(self, Row, j)
    }
    PyList_Append(List, Row);
  }
  self->affected_rows= mysql_stmt_num_rows(self->stmt);
  return List;
}
/* }}} */

/* {{{ MrdbCursor_executemany_fallback
   bulk execution for server < 10.2.6
*/
static
uint8_t MrdbCursor_executemany_fallback(MrdbCursor *self,
                                            const char *statement,
                                            size_t len)
{
  uint32_t i;

  if (mysql_stmt_attr_set(self->stmt, STMT_ATTR_PREBIND_PARAMS, &self->param_count))
    goto error;

  for (i=0; i < self->array_size; i++)
  {
    int rc= 0;
    /* Load values */
    if (mariadb_param_update(self, self->params, i))
      return 1;
    if (mysql_stmt_bind_param(self->stmt, self->params))
      goto error;
    Py_BEGIN_ALLOW_THREADS;
    if (i==0)
      rc= mysql_stmt_prepare(self->stmt, statement, len);
    if (!rc)
      rc= mysql_stmt_execute(self->stmt);
    Py_END_ALLOW_THREADS;
    if (rc)
      goto error;
  }
  return 0;
error:
  mariadb_throw_exception(self->stmt, NULL, 1, NULL);
  return 1;
}
/* }}} */

/* {{{ MrdbCursor_executemany
   PEP-249 executemany() method

   Paramter: A List of one or more tuples

   Note: When conecting to a server < 10.2.6 this command will be emulated
         by executing preparing and executing statement n times (where n is
         the number of tuples in list)
*/
PyObject *MrdbCursor_executemany(MrdbCursor *self,
                                     PyObject *Args)
{
  const char *statement= NULL;
  int statement_len= 0;
  int rc;

  MARIADB_CHECK_STMT(self);
  if (PyErr_Occurred())
    return NULL;

  self->data= NULL;

  if (!PyArg_ParseTuple(Args, "s#O!", &statement, &statement_len,
                        &PyList_Type, &self->data))
    return NULL;

  if (!(self->is_prepared= MrdbCursor_isprepared(self, statement, statement_len)))
  {
    MrdbCursor_clear(self);
    self->statement= PyMem_RawMalloc(statement_len + 1);
    strncpy(self->statement, statement, statement_len);
    self->statement[statement_len]= 0;
  }

  if (mariadb_check_bulk_parameters(self, self->data))
    goto error;

  /* If the server doesn't support bulk execution (< 10.2.6),
     we need to call a fallback routine */
  if (!MARIADB_FEATURE_SUPPORTED(self->stmt->mysql, 100206))
  {
    if (MrdbCursor_executemany_fallback(self, statement, statement_len))
      goto error;
    goto end;
  }

  mysql_stmt_attr_set(self->stmt, STMT_ATTR_ARRAY_SIZE, &self->array_size);
  if (!self->is_prepared)
  {
    mysql_stmt_attr_set(self->stmt, STMT_ATTR_PREBIND_PARAMS, &self->param_count);
    mysql_stmt_attr_set(self->stmt, STMT_ATTR_USER_DATA, (void *)self);
    mysql_stmt_attr_set(self->stmt, STMT_ATTR_PARAM_READ, mariadb_param_update);

    mysql_stmt_bind_param(self->stmt, self->params);

    Py_BEGIN_ALLOW_THREADS;
    rc= mariadb_stmt_execute_direct(self->stmt, statement, statement_len);
    Py_END_ALLOW_THREADS;
    if (rc)
    {
      mariadb_throw_exception(self->stmt, NULL, 1, NULL);
      goto error;
    }
  } else {
    Py_BEGIN_ALLOW_THREADS;
    rc= mysql_stmt_execute(self->stmt);
    Py_END_ALLOW_THREADS;
    if (rc)
    {
      mariadb_throw_exception(self->stmt, NULL, 1, NULL);
      goto error;
    }
  }
  self->lastrowid= mysql_stmt_insert_id(self->stmt);
end:
  MARIADB_FREE_MEM(self->values);
  Py_RETURN_NONE;
error:
  MrdbCursor_clear(self);
  return NULL;
}
/* }}} */

/* {{{ MrdbCursor_nextset
   PEP-249: Optional nextset() method
*/
PyObject *MrdbCursor_nextset(MrdbCursor *self)
{
  MARIADB_CHECK_STMT(self);
  int rc;
  if (PyErr_Occurred())
    return NULL;

  if (!mysql_stmt_field_count(self->stmt))
  {
    mariadb_throw_exception(NULL, Mariadb_ProgrammingError, 0,
                            "Cursor doesn't have a result set");
    return NULL;
  }

  Py_BEGIN_ALLOW_THREADS;
  rc= mysql_stmt_next_result(self->stmt);
  Py_END_ALLOW_THREADS;
  if (rc)
  {
    Py_INCREF(Py_None);
    return Py_None;
  }
  Py_RETURN_TRUE;
}
/* }}} */

/* {{{ Mariadb_row_count
   PEP-249: rowcount attribute
*/
static PyObject *Mariadb_row_count(MrdbCursor *self)
{
  int64_t row_count;

  MARIADB_CHECK_STMT(self);
  if (PyErr_Occurred())
    return NULL;

  if (mysql_stmt_field_count(self->stmt))
    row_count= (int64_t)mysql_stmt_num_rows(self->stmt);
  else
    row_count= (mysql_stmt_affected_rows(self->stmt) > 0) ?
                (int64_t)mysql_stmt_affected_rows(self->stmt) : -1;
  return PyLong_FromLongLong(row_count);
}
/* }}} */

static PyObject *MrdbCursor_warnings(MrdbCursor *self)
{
  MARIADB_CHECK_STMT(self);

  return PyLong_FromLong((long)mysql_stmt_warning_count(self->stmt));
}
