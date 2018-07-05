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

void Mariadb_dealloc(Mariadb_Connection *self);

static PyObject *Mariadb_Connection_cursor(Mariadb_Connection *self,
                                           PyObject *args,
                                           PyObject *kwargs);
/* todo: write more documentation, this is just a placeholder */
static char mariadb_connection_documentation[] =
"Returns a MariaDB connection object";

static PyMethodDef Mariadb_Connection_Methods[] =
{
  /* PEP-249 methods */
  {"close", (PyCFunction)Mariadb_close,
    METH_NOARGS,
    "Closes the connection"},
  {"connect", (PyCFunction)Mariadb_connect,
     METH_VARARGS | METH_KEYWORDS,
     "Connect with a Mariadb server"},
  {"commit", (PyCFunction)Mariadb_commit,
     METH_NOARGS,
     "Commits the current transaction"},
  {"rollback", (PyCFunction)Mariadb_rollback,
     METH_NOARGS,
     "Rolls back the current transaction"},
  {"cursor", (PyCFunction)Mariadb_Connection_cursor,
     METH_VARARGS | METH_KEYWORDS,
     "Creates a new cursor"},
  /* additional methods */
  {
    "affected_rows",
    (PyCFunction)Mariadb_affected_rows,
    METH_NOARGS,
    "Returns the number of affected rows by the last operation if the operation was an 'upsert' (INSERT, UPDATE, DELETE or REPLACE) statement" 
  },
  {
    "auto_commit",
    (PyCFunction)Mariadb_autocommit,
    METH_VARARGS,
    "Toggles autocommit mode on or off"
  },
  {NULL} /* alwa+ys last */
};

static struct PyMemberDef Mariadb_Connection_Members[] =
{
  {NULL} /* always last */
};

static int
Mariadb_Connection_Initialize(Mariadb_Connection *self,
                              PyObject *args,
                              PyObject *dsnargs)
{
  /* Todo: we need to support all dsn parameters, the current
           implementation is just a small subset.
  */
  char *host= NULL, *user= NULL, *password= NULL, *schema= NULL,
       *socket= NULL, *init_command= NULL, *default_file= NULL,
       *default_group= NULL, *local_infile= NULL,
       *ssl_key= NULL, *ssl_cert= NULL, *ssl_ca= NULL, *ssl_capath= NULL,
       *ssl_crl= NULL, *ssl_crlpath= NULL, *ssl_cipher= NULL;
  unsigned int client_flags= 0, port= 0;
  unsigned int connect_timeout=0, read_timeout=0, write_timeout=0,
      compress= 0, ssl_verify_cert= 0;

  static char *dsn_keys[]= {
    "host", "user", "password", "database", "port", "socket",
    "connect_timeout", "read_timeout", "write_timeout",
    "local_infile", "compress", "init_command",
    "default_file", "default_group",
    "ssl_key", "ssl_ca", "ssl_cert", "ssl_crl",
    "ssl_cipher", "ssl_capath", "ssl_crlpath",
    "ssl_verify_cert",
    "client_flags"
  };

  if (!PyArg_ParseTupleAndKeywords(args, dsnargs,
        "|ssssisiiiiissssssssssii:connect",
        dsn_keys,
        &host, &user, &password, &schema, &port, &socket,
        &connect_timeout, &read_timeout, &write_timeout,
        &local_infile, &compress, &init_command,
        &default_file, &default_group,
        &ssl_key, &ssl_ca, &ssl_cert, &ssl_crl,
        &ssl_cipher, &ssl_capath, &ssl_crlpath,
        &ssl_verify_cert,
        &client_flags))
    return -1;

  if (!(self->mysql= mysql_init(NULL)))
  {
    mariadb_throw_exception(self->mysql, Mariadb_InterfaceError, 0, 
    "Can't allocate memory for connection");
    return -1;
  }

  /* read defaults from configuration file(s) */
  if (default_file)
    mysql_optionsv(self->mysql, MYSQL_READ_DEFAULT_FILE, default_file);
  if (default_group)
    mysql_optionsv(self->mysql, MYSQL_READ_DEFAULT_GROUP, default_group);

  /* set timeouts */
  if (connect_timeout)
    mysql_optionsv(self->mysql, MYSQL_OPT_CONNECT_TIMEOUT, &connect_timeout);
  if (read_timeout)
    mysql_optionsv(self->mysql, MYSQL_OPT_READ_TIMEOUT, &read_timeout);
  if (write_timeout)
    mysql_optionsv(self->mysql, MYSQL_OPT_WRITE_TIMEOUT, &write_timeout);

  /* set TLS/SSL options */
  if (ssl_key || ssl_ca || ssl_cert || ssl_capath || ssl_cipher)
    mysql_ssl_set(self->mysql, (const char *)ssl_key,
                         (const char *)ssl_cert,
                         (const char *)ssl_ca,
                         (const char *)ssl_capath,
                         (const char *)ssl_cipher);
  if (ssl_crl)
    mysql_optionsv(self->mysql, MYSQL_OPT_SSL_CRL, ssl_crl);
  if (ssl_crlpath)
    mysql_optionsv(self->mysql, MYSQL_OPT_SSL_CRLPATH, ssl_crlpath);
  if (ssl_verify_cert)
    mysql_optionsv(self->mysql, MYSQL_OPT_SSL_VERIFY_SERVER_CERT, (unsigned char *) &ssl_verify_cert);

  if (!mysql_real_connect(self->mysql, host, user, password, schema, port,
                          socket, client_flags))
  {
    mariadb_throw_exception(self->mysql, Mariadb_InterfaceError, 0, NULL);
    return -1;
  }
  return 0;
}

static int Mariadb_Connection_traverse(
	Mariadb_Connection *self,
	visitproc visit,
	void *arg)
{
	return 0;
}

PyTypeObject Mariadb_Connection_Type = {
  PyVarObject_HEAD_INIT(NULL, 0)
	"mariadb.connection",
	sizeof(Mariadb_Connection),
	0,
	(destructor)Mariadb_dealloc, /* tp_dealloc */
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
	mariadb_connection_documentation, /* tp_doc Documentation string */

	/* call function for all accessible objects */
	(traverseproc)Mariadb_Connection_traverse, /* tp_traverse */

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
	(struct PyMethodDef *)Mariadb_Connection_Methods, /* tp_methods */
	(struct PyMemberDef *)Mariadb_Connection_Members, /* tp_members */
	0, /* (struct getsetlist *) tp_getset; */
	0, /* (struct _typeobject *) tp_base; */
	0, /* (PyObject *) tp_dict */
	0, /* (descrgetfunc) tp_descr_get */
	0, /* (descrsetfunc) tp_descr_set */
	0, /* (long) tp_dictoffset */
	(initproc)Mariadb_Connection_Initialize, /* tp_init */
	PyType_GenericAlloc, //NULL, /* tp_alloc */
	PyType_GenericNew, //NULL, /* tp_new */
	NULL, /* tp_free Low-level free-memory routine */ 
	0, /* (PyObject *) tp_bases */
	0, /* (PyObject *) tp_mro method resolution order */
	0, /* (PyObject *) tp_defined */
};

PyObject *
Mariadb_connect(
	PyObject *self,
	PyObject *args,
	PyObject *kwargs)
{
  Mariadb_Connection *c;

  if (!(c= (Mariadb_Connection *)PyType_GenericAlloc(&Mariadb_Connection_Type, 1)))
    return NULL;

  if (Mariadb_Connection_Initialize(c, args, kwargs))
  {
    Py_DECREF(c);
    return NULL;
  }
	return (PyObject *) c;
}

/* destructor of MariaDB Connection object */
void
Mariadb_dealloc(Mariadb_Connection *self)
{
  if (self)
  {
    if (self->mysql)
    {
      Py_BEGIN_ALLOW_THREADS
      mysql_close(self->mysql);
      Py_END_ALLOW_THREADS
    }
    Py_TYPE(self)->tp_free((PyObject*)self);
	}
}

PyObject *Mariadb_close(Mariadb_Connection *self)
{
  MARIADB_CHECK_CONNECTION(self);
  /* Todo: check if all the cursor stuff is deleted (when using prepared
     statemnts this should be handled in mysql_close) */
  Py_BEGIN_ALLOW_THREADS
  mysql_close(self->mysql);
  Py_END_ALLOW_THREADS
  self->mysql= NULL;
  Py_INCREF(Py_None);
  return Py_None;
}

static PyObject *Mariadb_Connection_cursor(Mariadb_Connection *self,
                                           PyObject *args,
                                           PyObject *kwargs)
{
  PyObject *cursor= NULL;
  PyObject *conn = NULL;

  conn= Py_BuildValue("(O)", self);
  cursor= PyObject_Call((PyObject *)&Mariadb_Cursor_Type, conn, kwargs);
  return cursor;
}
