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

static void Mariadb_Cursor_dealloc(Mariadb_Cursor *self);
static PyObject *Mariadb_Cursor_close(Mariadb_Cursor *self);
static PyObject *Mariadb_Cursor_rowcount(Mariadb_Cursor *self);
static PyObject *Mariadb_Cursor_execute(Mariadb_Cursor *self,
                                 PyObject *Args);
static PyObject *Mariadb_Cursor_nextset(Mariadb_Cursor *self);
static PyObject *Mariadb_Cursor_executemany(Mariadb_Cursor *self,
                                     PyObject *Args);
static PyObject *Mariadb_Cursor_description(Mariadb_Cursor *self);
static PyObject *Mariadb_Cursor_fetchall(Mariadb_Cursor *self);
static PyObject *Mariadb_Cursor_fetchone(Mariadb_Cursor *self);
static PyObject *Mariadb_Cursor_fetchmany(Mariadb_Cursor *self,
                                     PyObject *Args);
static PyObject *Mariadb_Cursor_fieldcount(Mariadb_Cursor *self);
void field_fetch_callback(void *data, unsigned int column, unsigned char **row);

/* todo: write more documentation, this is just a placeholder */
static char mariadb_cursor_documentation[] =
"Returns a MariaDB cursor object";


static PyMethodDef Mariadb_Cursor_Methods[] =
{
  /* PEP-249 methods */
  {"close", (PyCFunction)Mariadb_Cursor_close,
    METH_NOARGS,
    "Closes an open Cursor"},
  {"description", (PyCFunction)Mariadb_Cursor_description,
    METH_NOARGS,
    "Returns sequences with result column information."},
  {"execute", (PyCFunction)Mariadb_Cursor_execute,
     METH_VARARGS,
     "Executes a SQL statement"},
  {"executemany", (PyCFunction)Mariadb_Cursor_executemany,
     METH_VARARGS,
     "Executes a SQL statement by passing a list of values"},
  {"fetchall", (PyCFunction)Mariadb_Cursor_fetchall,
    METH_NOARGS,
    "Fetches all rows of a result set"},
  {"fetchone", (PyCFunction)Mariadb_Cursor_fetchone,
    METH_NOARGS,
    "Fetches the next row of a result set"},
  {"fetchmany", (PyCFunction)Mariadb_Cursor_fetchmany,
    METH_VARARGS,
    "Fetches multiple rows of a result set"},
  {"fieldcount", (PyCFunction)Mariadb_Cursor_fieldcount,
    METH_NOARGS,
    "Returns number of columns in current result set"},
  {"nextset", (PyCFunction)Mariadb_Cursor_nextset,
   METH_NOARGS,
   "Will make the cursor skip to the next available result set, discarding any remaining rows from the current set."},
  {"rowcount", (PyCFunction)Mariadb_Cursor_rowcount,
     METH_NOARGS,
     "Returns the number of rows for last DQL statement (like SELECT, SHOW) or the number of affected rows from last DML statement (UPDATE, INSERT, DELETE)"},
  {NULL} /* always last */
};

static struct PyMemberDef Mariadb_Cursor_Members[] =
{
  {"lastrowid",
   T_LONG,
   offsetof(Mariadb_Cursor, lastrowid),
   READONLY,
   "row id of the last modified (inserted) row"},
  {"arraysize",
   T_LONG,
   offsetof(Mariadb_Cursor, row_array_size),
   0,
   "the number of rows to fetch"},
   {NULL}
};

PyObject * Mariadb_Cursor_initialize(Mariadb_Connection *self)
{
  Mariadb_Cursor *c= (Mariadb_Cursor *)PyType_GenericAlloc(&Mariadb_Cursor_Type, 0);

  if (!c)
    return 0;

	if (!(c->stmt = mysql_stmt_init(self->mysql)))
  {
		Py_DECREF(c);
		return NULL;
	}

  c->array_size= 1;
	return (PyObject *) c;
}

static int Mariadb_Cursor_traverse(
	Mariadb_Cursor *self,
	visitproc visit,
	void *arg)
{
	return 0;
}

PyTypeObject Mariadb_Cursor_Type =
{
  PyVarObject_HEAD_INIT(NULL, 0)
	"mariadb.connection.cursor",
	sizeof(Mariadb_Cursor),
	0,
	(destructor)Mariadb_Cursor_dealloc, /* tp_dealloc */
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
	mariadb_cursor_documentation, /* tp_doc Documentation string */

	/* call function for all accessible objects */
	(traverseproc)Mariadb_Cursor_traverse,/* tp_traverse */

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
	(struct PyMethodDef *)Mariadb_Cursor_Methods, /* tp_methods */
	(struct PyMemberDef *)Mariadb_Cursor_Members, /* tp_members */
	0, /* (struct getsetlist *) tp_getset; */
	0, /* (struct _typeobject *) tp_base; */
	0, /* (PyObject *) tp_dict */
	0, /* (descrgetfunc) tp_descr_get */
	0, /* (descrsetfunc) tp_descr_set */
	0, /* (long) tp_dictoffset */
	(initproc)Mariadb_Cursor_initialize, /* tp_init */
	PyType_GenericAlloc, //NULL, /* tp_alloc */
	PyType_GenericNew, //NULL, /* tp_new */
	NULL, /* tp_free Low-level free-memory routine */ 
	0, /* (PyObject *) tp_bases */
	0, /* (PyObject *) tp_mro method resolution order */
	0, /* (PyObject *) tp_defined */
};

static uint8_t Mariadb_Cursor_isprepared(Mariadb_Cursor *self,
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

static
void Mariadb_Cursor_clear(Mariadb_Cursor *self)
{
  if (self->stmt) { 
    uint32_t val= 0;
    mysql_stmt_attr_set(self->stmt, STMT_ATTR_USER_DATA, 0);
    mysql_stmt_attr_set(self->stmt, STMT_ATTR_PARAM_READ, 0);
    mysql_stmt_attr_set(self->stmt, STMT_ATTR_FIELD_FETCH_CALLBACK, 0);
    mysql_stmt_attr_set(self->stmt, STMT_ATTR_ARRAY_SIZE, &val);
    mysql_stmt_attr_set(self->stmt, STMT_ATTR_PREBIND_PARAMS, &val);
  }
  MARIADB_FREE_MEM(self->fields);
  MARIADB_FREE_MEM(self->values);
  MARIADB_FREE_MEM(self->bind);
  MARIADB_FREE_MEM(self->statement);
  MARIADB_FREE_MEM(self->values);
  MARIADB_FREE_MEM(self->params);
}

static
void ma_cursor_close(Mariadb_Cursor *self)
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
  Mariadb_Cursor_clear(self);
}

static
PyObject * Mariadb_Cursor_close(Mariadb_Cursor *self)
{
  ma_cursor_close(self);
  Py_INCREF(Py_None);
  return Py_None;
}

void Mariadb_Cursor_dealloc(Mariadb_Cursor *self)
{
	ma_cursor_close(self);
  Py_TYPE(self)->tp_free((PyObject*)self);
}

static
PyObject *Mariadb_Cursor_execute(Mariadb_Cursor *self,
                                 PyObject *Args)
{
  PyObject *Data= NULL;
  const char *statement= NULL;
  int statement_len= 0;

  MARIADB_CHECK_STMT(self);
  if (PyErr_Occurred())
    return NULL;

  if (!PyArg_ParseTuple(Args, "s#|O!", &statement, &statement_len,
                        &PyTuple_Type, &Data))
    return NULL;

  /* Check if statement is already prepared */
  if (!(self->is_prepared= Mariadb_Cursor_isprepared(self, statement, statement_len)))
  {
    Mariadb_Cursor_clear(self);
    self->statement= PyMem_RawMalloc(statement_len);
    memcpy(self->statement, statement, statement_len);
    mysql_stmt_attr_set(self->stmt, STMT_ATTR_USER_DATA, 0);
    mysql_stmt_attr_set(self->stmt, STMT_ATTR_PARAM_READ, 0);
    mysql_stmt_attr_set(self->stmt, STMT_ATTR_FIELD_FETCH_CALLBACK, 0);
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

    if (mariadb_stmt_execute_direct(self->stmt, statement, statement_len))
    {
      mariadb_throw_exception(self->stmt, Mariadb_InterfaceError, 1, NULL);
      goto error;
    }
  } else {
    if (mysql_stmt_execute(self->stmt))
    {
      mariadb_throw_exception(self->stmt, Mariadb_InterfaceError, 1, NULL);
      goto error;
    }
    self->lastrowid= mysql_stmt_insert_id(self->stmt);
  }

  if (mysql_stmt_field_count(self->stmt))
  {
    MYSQL_RES *res= mysql_stmt_result_metadata(self->stmt);
    MYSQL_FIELD *fields= mysql_fetch_fields(res);
    if (!(self->fields= (MYSQL_FIELD *)PyMem_RawCalloc(mysql_stmt_field_count(self->stmt), sizeof(MYSQL_FIELD))))
      goto error;
    memcpy(self->fields, fields, sizeof(MYSQL_FIELD) * mysql_stmt_field_count(self->stmt));
    memcpy(self->fields, fields, sizeof(MYSQL_FIELD) * mysql_stmt_field_count(self->stmt));
    mysql_free_result(res);
    if (!(self->values= (PyObject**)PyMem_RawCalloc(mysql_stmt_field_count(self->stmt), sizeof(PyObject *))))
    {
      PyMem_RawFree(self->fields);
      goto error;
    }
    mysql_stmt_attr_set(self->stmt, STMT_ATTR_FIELD_FETCH_CALLBACK, field_fetch_callback);
  }
  MARIADB_FREE_MEM(self->value);
  Py_RETURN_NONE;
error:
  Mariadb_Cursor_clear(self);
  return NULL;
}

static
PyObject *Mariadb_Cursor_rowcount(Mariadb_Cursor *self)
{
  MARIADB_CHECK_STMT(self);

  if (PyErr_Occurred())
    return NULL;
  if (mysql_stmt_field_count(self->stmt))
    return PyLong_FromLongLong(mysql_stmt_num_rows(self->stmt));
  else
    return PyLong_FromLongLong(mysql_stmt_affected_rows(self->stmt));
}

PyObject *Mariadb_Cursor_fieldcount(Mariadb_Cursor *self)
{
  MARIADB_CHECK_STMT(self);
  if (PyErr_Occurred())
    return NULL;

  return PyLong_FromLong((long)mysql_stmt_field_count(self->stmt));
}

static
PyObject *Mariadb_Cursor_description(Mariadb_Cursor *self)
{
  MARIADB_CHECK_STMT(self);
  if (PyErr_Occurred())
    return NULL;

  if (self->fields)
  {
    PyObject *obj;
    uint32_t i;

    if (!(obj= PyTuple_New(mysql_stmt_field_count(self->stmt))))
      return NULL;

    for (i=0; i < mysql_stmt_field_count(self->stmt); i++)
    {
      PyObject *desc;
      if (!(desc= Py_BuildValue("(siiiiiii)",
                                self->fields[i].name,
                                (long)self->fields[i].type,
                                (long)self->fields[i].max_length,
                                (long)self->fields[i].length,
                                (long)self->fields[i].length,
                                (long)self->fields[i].decimals,
                                (long)!IS_NOT_NULL(self->fields[i].flags),
                                (long)self->fields[i].flags)))
      {
        Py_XDECREF(obj);
        return NULL;
      }
      PyTuple_SET_ITEM(obj, i, desc);
    }
    return obj;
  }
  return NULL;
}

static
PyObject *Mariadb_Cursor_fetchone(Mariadb_Cursor *self)
{
  PyObject *row;
  uint32_t i;

  MARIADB_CHECK_STMT(self);
  if (PyErr_Occurred())
    return NULL;

  if (!mysql_stmt_field_count(self->stmt))
  {
    mariadb_throw_exception(self->stmt, Mariadb_InterfaceError, 1,
                            "Cursor doesn't have a result set");
    return NULL;
  }

  if (mysql_stmt_fetch(self->stmt))
  {
    Py_INCREF(Py_None);
    return Py_None;
  }
  if (!(row= PyTuple_New(mysql_stmt_field_count(self->stmt))))
    return NULL;
  for (i= 0; i < mysql_stmt_field_count(self->stmt); i++)
  {
    PyTuple_SET_ITEM(row, i, self->values[i]);
  }
  return row;
}

static
PyObject *Mariadb_Cursor_fetchmany(Mariadb_Cursor *self, PyObject *Args)
{
  PyObject *RowNr= NULL,
           *List= NULL;
  uint32_t i,rows;

  MARIADB_CHECK_STMT(self);
  if (PyErr_Occurred())
    return NULL;

  if (!mysql_stmt_field_count(self->stmt))
  {
    mariadb_throw_exception(self->stmt, Mariadb_InterfaceError, 1,
                            "Cursor doesn't have a result set");
    return NULL;
  }

  if (!PyArg_ParseTuple(Args, "|O!", &PyLong_Type, &RowNr))
    return NULL;

  rows= (RowNr) ? PyLong_AsLong(RowNr) : self->row_array_size;

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
    if (!(Row= PyTuple_New(mysql_stmt_field_count(self->stmt))))
      return NULL;
    for (j=0; j < mysql_stmt_field_count(self->stmt); j++)
      PyTuple_SET_ITEM(Row, j, self->values[j]);
    PyList_Append(List, Row);
  }
end:
  return List;
}

static
PyObject *Mariadb_Cursor_fetchall(Mariadb_Cursor *self)
{
  PyObject *List;

  MARIADB_CHECK_STMT(self);
  if (PyErr_Occurred())
    return NULL;

  if (!mysql_stmt_field_count(self->stmt))
  {
    mariadb_throw_exception(self->stmt, Mariadb_InterfaceError, 1,
                            "Cursor doesn't have a result set");
    return NULL;
  }

  if (!(List= PyList_New(0)))
    return NULL;

  while (!mysql_stmt_fetch(self->stmt))
  {
    uint32_t j;
    PyObject *Row;
    if (!(Row= PyTuple_New(mysql_stmt_field_count(self->stmt))))
      return NULL;
    for (j=0; j < mysql_stmt_field_count(self->stmt); j++)
      PyTuple_SET_ITEM(Row, j, self->values[j]);
    PyList_Append(List, Row);
  }
  return List;
}


/**
*/
static
uint8_t Mariadb_Cursor_executemany_fallback(Mariadb_Cursor *self,
                                            const char *statement,
                                            size_t len)
{
  uint32_t i;

  if (mysql_stmt_attr_set(self->stmt, STMT_ATTR_PREBIND_PARAMS, &self->param_count))
    goto error;

  for (i=0; i < self->array_size; i++)
  {
    int rc;
    /* Load values */
    if (mariadb_param_update(self, self->params, i))
      return 1;
    if (mysql_stmt_bind_param(self->stmt, self->params))
      goto error;
    if (i==0)
      rc= mariadb_stmt_execute_direct(self->stmt, statement, len);
    else
      rc= mysql_stmt_execute(self->stmt);
    if (rc)
      goto error;
  }
  return 0;
error:
  mariadb_throw_exception(self->stmt, Mariadb_InterfaceError, 1, NULL);
  return 1;
}

PyObject *Mariadb_Cursor_executemany(Mariadb_Cursor *self,
                                     PyObject *Args)
{
  const char *statement= NULL;
  int statement_len= 0;

  MARIADB_CHECK_STMT(self);
  if (PyErr_Occurred())
    return NULL;

  self->data= NULL;

  if (!PyArg_ParseTuple(Args, "s#O!", &statement, &statement_len,
                        &PyList_Type, &self->data))
    return NULL;

  if (!(self->is_prepared= Mariadb_Cursor_isprepared(self, statement, statement_len)))
  {
    Mariadb_Cursor_clear(self);
    self->statement= PyMem_RawMalloc(statement_len);
    memcpy(self->statement, statement, statement_len);
  }

  if (mariadb_check_bulk_parameters(self, self->data))
    goto error;

  /* If the server doesn't support bulk execution (< 10.2.6),
     we need to call a fallback routine */
  if (!MARIADB_FEATURE_SUPPORTED(self->stmt->mysql, 100206))
  {
    if (Mariadb_Cursor_executemany_fallback(self, statement, statement_len))
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

    if (mariadb_stmt_execute_direct(self->stmt, statement, statement_len))
    {
      mariadb_throw_exception(self->stmt, Mariadb_DatabaseError, 1, NULL);
      goto error;
    }
  } else {
    if (mysql_stmt_execute(self->stmt))
    {
      mariadb_throw_exception(self->stmt, Mariadb_DatabaseError, 1, NULL);
      goto error;
    }
  }
  self->lastrowid= mysql_stmt_insert_id(self->stmt);
end:
  MARIADB_FREE_MEM(self->values);
  Py_RETURN_NONE;
error:
  Mariadb_Cursor_clear(self);
  return NULL;
}

static
PyObject *Mariadb_Cursor_nextset(Mariadb_Cursor *self)
{
  MARIADB_CHECK_STMT(self);
  if (PyErr_Occurred())
    return NULL;

  if (!mysql_stmt_field_count(self->stmt))
  {
    mariadb_throw_exception(self->stmt, Mariadb_InterfaceError, 1,
                            "Cursor doesn't have a result set");
    return NULL;
  }

  if (mysql_stmt_next_result(self->stmt))
  {
    Py_INCREF(Py_None);
    return Py_None;
  }
  Py_RETURN_TRUE;
}
