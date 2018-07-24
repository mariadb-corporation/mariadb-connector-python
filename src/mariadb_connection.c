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

void MrdbConnection_dealloc(MrdbConnection *self);

static PyObject *MrdbConnection_cursor(MrdbConnection *self,
                                           PyObject *args,
                                           PyObject *kwargs);
/* todo: write more documentation, this is just a placeholder */
static char mariadb_connection_documentation[] =
"Returns a MariaDB connection object";

static PyObject *MrdbConnection_exception(PyObject *self, void *closure);
#define GETTER_EXCEPTION(name, exception)\
{ name,MrdbConnection_exception, NULL, "doc", &exception }
static PyObject *MrdbConnection_getid(MrdbConnection *self, void *closure);
static PyObject *MrdbConnection_getuser(MrdbConnection *self, void *closure);
static PyObject *MrdbConnection_getreconnect(MrdbConnection *self,
                                             void *closure);
static int MrdbConnection_setreconnect(MrdbConnection *self,
                                       PyObject *args,
                                       void *closure);
static PyObject *MrdbConnection_getdb(MrdbConnection *self, void *closure);
static int MrdbConnection_setdb(MrdbConnection *self, PyObject *arg, void *closure);
static PyObject *MrdbConnection_escape_string(MrdbConnection *self,
                                              PyObject *args);
static PyObject *MrdbConnection_server_version(MrdbConnection *self);
static PyObject *MrdbConnection_server_info(MrdbConnection *self);

static PyObject *MrdbConnection_warnings(MrdbConnection *self);
static PyGetSetDef MrdbConnection_sets[]=
{
  {"connection_id", (getter)MrdbConnection_getid, NULL, "connection id", NULL},
  {"database", (getter)MrdbConnection_getdb, (setter)MrdbConnection_setdb, "database in use", NULL},
  {"auto_reconnect", (getter)MrdbConnection_getreconnect,
                     (setter)MrdbConnection_setreconnect,
                     "reconnect automatically if connection dropped", NULL},
  {"user", (getter)MrdbConnection_getuser, NULL, "user nane", NULL},
  {"warnings", (getter)MrdbConnection_warnings, NULL, "number of warnings which were produced from last running connection command", NULL},
  {"server_version", (getter)MrdbConnection_server_version, NULL,
    "Numeric version of connected server. The form of the version number is "
    "VERSION_MAJOR * 10000 + VERSION_MINOR * 100 + VERSION_PATCH",
    NULL},
  {"server_info", (getter)MrdbConnection_server_info, NULL, "Name and version of connected server", NULL},
  GETTER_EXCEPTION("Error", Mariadb_Error),
  GETTER_EXCEPTION("Warning", Mariadb_Warning),
  GETTER_EXCEPTION("InterfaceError", Mariadb_InterfaceError),
  GETTER_EXCEPTION("ProgrammingError", Mariadb_ProgrammingError),
  GETTER_EXCEPTION("IntegrityError", Mariadb_IntegrityError),
  GETTER_EXCEPTION("DatabaseError", Mariadb_DatabaseError),
  GETTER_EXCEPTION("NotSupportedError", Mariadb_NotSupportedError),
  GETTER_EXCEPTION("InternalError", Mariadb_InternalError),
  GETTER_EXCEPTION("OperationalError", Mariadb_OperationalError),
  {NULL}
};
static PyMethodDef MrdbConnection_Methods[] =
{
  /* PEP-249 methods */
  {"close", (PyCFunction)MrdbConnection_close,
    METH_NOARGS,
    "Closes the connection"},
  {"connect", (PyCFunction)MrdbConnection_connect,
     METH_VARARGS | METH_KEYWORDS,
     "Connect with a Mariadb server"},
  {"commit", (PyCFunction)MrdbConnection_commit,
     METH_NOARGS,
     "Commits the current transaction"},
  {"rollback", (PyCFunction)MrdbConnection_rollback,
     METH_NOARGS,
     "Rolls back the current transaction"},
  {"cursor", (PyCFunction)MrdbConnection_cursor,
     METH_VARARGS | METH_KEYWORDS,
     "Creates a new cursor"},
    /*TPC methods */
  {"tpc_begin",
    (PyCFunction)MrdbConnection_tpc_begin,
    METH_VARARGS,
    "Begins a TPC transaction with the given transaction ID xid."},
  {"tpc_commit",
    (PyCFunction)MrdbConnection_tpc_commit,
    METH_VARARGS,
    "When called with no arguments, .tpc_commit() commits a TPC transaction "
    "previously prepared with .tpc_prepare()."
    "If .tpc_commit() is called prior to .tpc_prepare(), a single phase commit "
    "is performed. A transaction manager may choose to do this if only a "
    "single resource is participating in the global transaction."
    "When called with a transaction ID xid, the database commits the given "
    "transaction. If an invalid transaction ID is provided, a ProgrammingError "
    "will be raised. This form should be called outside of a transaction, and "
    "is intended for use in recovery."},
  {"tpc_prepare",
    (PyCFunction)MrdbConnection_tpc_prepare,
    METH_NOARGS,
    "Performs the first phase of a transaction started with .tpc_begin()"},
  {"tpc_recover",
    (PyCFunction)MrdbConnection_tpc_recover,
    METH_NOARGS,
    "Shows information about all PREPARED transactions"},
  {"tpc_rollback",
    (PyCFunction)MrdbConnection_tpc_rollback,
    METH_VARARGS,
    "When called with no arguments, .tpc_rollback() rolls back a TPC "
    "transaction. It may be called before or after .tpc_prepare()."
    "When called with a transaction ID xid, it rolls back the given "
    "transaction."},
  {"xid",
    (PyCFunction)MrdbConnection_xid,
    METH_VARARGS,
    "Returns a transaction ID object suitable for passing to the .tpc_*() "
    "methods of this connection" },
  /* additional methods */
  {
    "auto_commit",
    (PyCFunction)MrdbConnection_autocommit,
    METH_VARARGS,
    "Toggles autocommit mode on or off"
  },
  { "ping",
    (PyCFunction)MrdbConnection_ping,
    METH_NOARGS,
    "Checks whether the connection to the database server is working. "
    "If it has gone down, and the reconnect option was set, an automatic "
    "reconnect is attempted."
  },
  { "change_user",
    (PyCFunction)MrdbConnection_change_user,
    METH_VARARGS,
    "Changes the user and default database of the current connection. "
    "In order to successfully change users a valid username and password "
    "parameters must be provided and that user must have sufficient "
    "permissions to access the desired database. If for any reason "
    "authorization fails, the current user authentication will remain."
  },
  { "kill",
    (PyCFunction)MrdbConnection_kill,
    METH_VARARGS,
    "This function is used to ask the server to kill a MariaDB thread "
    "specified by the processid parameter. This value must be retrieved "
    "by SHOW PROCESSLIST."
  },
  { "reconnect",
    (PyCFunction)MrdbConnection_reconnect,
    METH_NOARGS,
    "tries to reconnect to a server in case the connection died due to timeout "
    "or other errors. It uses the same credentials which were specified in "
    "connect() method."
  },
  { "reset",
    (PyCFunction)MrdbConnection_reset,
    METH_NOARGS,
    "Resets the current connection and clears session state and pending "
    "results. Open cursors will become invalid and cannot be used anymore."
  },
  { "escape_string",
    (PyCFunction)MrdbConnection_escape_string,
    METH_VARARGS,
    "This function is used to create a legal SQL string that you can use in "
    "an SQL statement. The given string is encoded to an escaped SQL string."
  },
  {NULL} /* alwa+ys last */
};

static struct PyMemberDef MrdbConnection_Members[] =
{
  {"character_set",
   T_OBJECT,
   offsetof(MrdbConnection, charset),
   READONLY,
   "Client character set"},
  {"collation",
   T_OBJECT,
   offsetof(MrdbConnection, collation),
   READONLY,
   "Client character set collation"},
  {"dsn",
   T_OBJECT,
   offsetof(MrdbConnection, dsn),
   READONLY,
   "Data source name (dsn)"},
  {"server_port",
   T_INT,
   offsetof(MrdbConnection, port),
   READONLY,
   "Database server TCP/IP port"},
  {"unix_socket",
   T_OBJECT,
   offsetof(MrdbConnection, unix_socket),
   READONLY,
   "Unix socket name"},
  {"server_name",
   T_OBJECT,
   offsetof(MrdbConnection, host),
   READONLY,
   "Name or address of database server"},
  {"tls_cipher",
   T_OBJECT,
   offsetof(MrdbConnection, tls_cipher),
   READONLY,
   "TLS cipher suite in used by connection"},
  {"tls_version",
   T_OBJECT,
   offsetof(MrdbConnection, tls_version),
   READONLY,
   "TLS protocol version used by connection"},
  {NULL} /* always last */
};

static void Mrdb_ConnAttrStr(MYSQL *mysql, PyObject **obj, enum mariadb_value attr)
{
  char *val= NULL;

  if (mariadb_get_infov(mysql, attr, &val) || !val)
    return;
  *obj= PyUnicode_FromString(val);
}

void MrdbConnection_SetAttributes(MrdbConnection *self)
{
  MY_CHARSET_INFO cinfo;

  Mrdb_ConnAttrStr(self->mysql, &self->host, MARIADB_CONNECTION_HOST);
  Mrdb_ConnAttrStr(self->mysql, &self->tls_cipher, MARIADB_CONNECTION_SSL_CIPHER);
  Mrdb_ConnAttrStr(self->mysql, &self->tls_version, MARIADB_CONNECTION_TLS_VERSION);
  Mrdb_ConnAttrStr(self->mysql, &self->unix_socket, MARIADB_CONNECTION_UNIX_SOCKET);
  mariadb_get_infov(self->mysql, MARIADB_CONNECTION_PORT, &self->port);
  mariadb_get_infov(self->mysql, MARIADB_CONNECTION_MARIADB_CHARSET_INFO, &cinfo);
  self->charset= PyUnicode_FromString(cinfo.csname);
  self->collation= PyUnicode_FromString(cinfo.name);
}

static int
MrdbConnection_Initialize(MrdbConnection *self,
                              PyObject *args,
                              PyObject *dsnargs)
{
  int rc;
  /* Todo: we need to support all dsn parameters, the current
           implementation is just a small subset.
  */
  char *dsn= NULL, *host=NULL, *user= NULL, *password= NULL, *schema= NULL,
       *socket= NULL, *init_command= NULL, *default_file= NULL,
       *default_group= NULL, *local_infile= NULL,
       *ssl_key= NULL, *ssl_cert= NULL, *ssl_ca= NULL, *ssl_capath= NULL,
       *ssl_crl= NULL, *ssl_crlpath= NULL, *ssl_cipher= NULL;
  uint8_t ssl_enforce= 0;
  unsigned int client_flags= 0, port= 0;
  unsigned int connect_timeout=0, read_timeout=0, write_timeout=0,
      compress= 0, ssl_verify_cert= 0;

  static char *dsn_keys[]= {
    "dsn", "host", "user", "password", "database", "port", "socket",
    "connect_timeout", "read_timeout", "write_timeout",
    "local_infile", "compress", "init_command",
    "default_file", "default_group",
    "ssl_key", "ssl_ca", "ssl_cert", "ssl_crl",
    "ssl_cipher", "ssl_capath", "ssl_crlpath",
    "ssl_verify_cert", "ssl",
    "client_flags"
  };

  if (!PyArg_ParseTupleAndKeywords(args, dsnargs,
        "|sssssisiiiiissssssssssipi:connect",
        dsn_keys,
        &dsn, &host, &user, &password, &schema, &port, &socket,
        &connect_timeout, &read_timeout, &write_timeout,
        &local_infile, &compress, &init_command,
        &default_file, &default_group,
        &ssl_key, &ssl_ca, &ssl_cert, &ssl_crl,
        &ssl_cipher, &ssl_capath, &ssl_crlpath,
        &ssl_verify_cert, &ssl_enforce,
        &client_flags))
    return -1;

  if (dsn)
  {
    mariadb_throw_exception(NULL, Mariadb_ProgrammingError, 0,
                             "dsn keyword is not supported");
    return -1;
  }

  if (!(self->mysql= mysql_init(NULL)))
  {    mariadb_throw_exception(self->mysql, Mariadb_OperationalError, 0, 
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
  if (ssl_enforce || ssl_key || ssl_ca || ssl_cert || ssl_capath || ssl_cipher)
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
  Py_BEGIN_ALLOW_THREADS;
  mysql_real_connect(self->mysql, host, user, password, schema, port,
                          socket, client_flags);
  Py_END_ALLOW_THREADS;
  if (mysql_errno(self->mysql))
  {
    mariadb_throw_exception(self->mysql, NULL, 0, NULL);
    goto end;
  }

  /* make sure that we use a utf8 connection */
  Py_BEGIN_ALLOW_THREADS;
  rc= mysql_set_character_set(self->mysql, "utf8mb4");
  Py_END_ALLOW_THREADS;
  if (rc)
  {
    mariadb_throw_exception(self->mysql, NULL, 0, NULL);
    goto end;
  }
end:
  if (PyErr_Occurred())
    return -1;

  /* set connection attributes */
  MrdbConnection_SetAttributes(self);

  return 0;
}

static int MrdbConnection_traverse(
	MrdbConnection *self,
	visitproc visit,
	void *arg)
{
	return 0;
}

PyTypeObject MrdbConnection_Type = {
  PyVarObject_HEAD_INIT(NULL, 0)
	"mariadb.connection",
	sizeof(MrdbConnection),
	0,
	(destructor)MrdbConnection_dealloc, /* tp_dealloc */
	0, /*tp_print*/
	0, /* tp_getattr */
	0, /* tp_setattr */
	0, /* PyAsyncMethods* */
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
	(traverseproc)MrdbConnection_traverse, /* tp_traverse */

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
	(struct PyMethodDef *)MrdbConnection_Methods, /* tp_methods */
	(struct PyMemberDef *)MrdbConnection_Members, /* tp_members */
	MrdbConnection_sets, /* (struct getsetlist *) tp_getset; */
	0, /* (struct _typeobject *) tp_base; */
	0, /* (PyObject *) tp_dict */
	0, /* (descrgetfunc) tp_descr_get */
	0, /* (descrsetfunc) tp_descr_set */
	0, /* (long) tp_dictoffset */
	(initproc)MrdbConnection_Initialize, /* tp_init */
	PyType_GenericAlloc, //NULL, /* tp_alloc */
	PyType_GenericNew, //NULL, /* tp_new */
	NULL, /* tp_free Low-level free-memory routine */ 
	0, /* (PyObject *) tp_bases */
	0, /* (PyObject *) tp_mro method resolution order */
	0, /* (PyObject *) tp_defined */
};

PyObject *
MrdbConnection_connect(
	PyObject *self,
	PyObject *args,
	PyObject *kwargs)
{
  MrdbConnection *c;

  if (!(c= (MrdbConnection *)PyType_GenericAlloc(&MrdbConnection_Type, 1)))
    return NULL;

  if (MrdbConnection_Initialize(c, args, kwargs))
  {
    Py_DECREF(c);
    return NULL;
  }
	return (PyObject *) c;
}

/* destructor of MariaDB Connection object */
void
MrdbConnection_dealloc(MrdbConnection *self)
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

PyObject *MrdbConnection_close(MrdbConnection *self)
{
  MARIADB_CHECK_CONNECTION(self, NULL);
  /* Todo: check if all the cursor stuff is deleted (when using prepared
     statemnts this should be handled in mysql_close) */
  Py_BEGIN_ALLOW_THREADS
  mysql_close(self->mysql);
  Py_END_ALLOW_THREADS
  self->mysql= NULL;
  Py_INCREF(Py_None);
  return Py_None;
}

static PyObject *MrdbConnection_cursor(MrdbConnection *self,
                                           PyObject *args,
                                           PyObject *kwargs)
{
  PyObject *cursor= NULL;
  PyObject *conn = NULL;

  conn= Py_BuildValue("(O)", self);
  cursor= PyObject_Call((PyObject *)&MrdbCursor_Type, conn, kwargs);
  return cursor;
}

static PyObject *
MrdbConnection_exception(PyObject *self, void *closure)
{
    PyObject *exception = *(PyObject **)closure;

    Py_INCREF(exception);
    return exception;
}

/* {{{ MrdbConnection_commit */
PyObject *MrdbConnection_commit(MrdbConnection *self)
{
  MARIADB_CHECK_CONNECTION(self, NULL);

  if (self->tpc_state != TPC_STATE_NONE)
  {
    mariadb_throw_exception(self->mysql, Mariadb_ProgrammingError,
        0, "rollback() is not allowed if a TPC transaction is active");
    return NULL;
  }
  Py_BEGIN_ALLOW_THREADS;
  if (mysql_commit(self->mysql))
  {
    mariadb_throw_exception(self->mysql, NULL, 0, NULL);
    goto end;
  }
end:
  Py_END_ALLOW_THREADS;
  if (PyErr_Occurred())
    return NULL;
  Py_RETURN_NONE;
} /* }}} */

/* {{{ MrdbConnection_rollback */
PyObject *MrdbConnection_rollback(MrdbConnection *self)
{
  MARIADB_CHECK_CONNECTION(self, NULL);

  if (self->tpc_state != TPC_STATE_NONE)
  {
    mariadb_throw_exception(self->mysql, Mariadb_ProgrammingError,
        0, "rollback() is not allowed if a TPC transaction is active");
    return NULL;
  }

  Py_BEGIN_ALLOW_THREADS;
  if (mysql_rollback(self->mysql))
  {
    mariadb_throw_exception(self->mysql, NULL, 0, NULL);
    goto end;
  }
end:
  Py_END_ALLOW_THREADS;
  if (PyErr_Occurred())
    return NULL;
  Py_RETURN_NONE;
}
/* }}} */

/* {{{ Mariadb_autocommit */
PyObject *MrdbConnection_autocommit(MrdbConnection *self,
                                        PyObject *args)
{
  int autocommit;
  MARIADB_CHECK_CONNECTION(self, NULL);

  if (PyArg_ParseTuple(args, "p", &autocommit))
    return NULL;

  Py_BEGIN_ALLOW_THREADS;
  if (mysql_autocommit(self->mysql, autocommit))
  {
    mariadb_throw_exception(self->mysql, NULL, 0, NULL);
  }
  Py_END_ALLOW_THREADS;
  if (PyErr_Occurred())
    return NULL;
  Py_RETURN_NONE;
}
/* }}} */

/* {{{ DBAPIType Object */
PyObject *Mariadb_DBAPIType_Object(uint32_t type)
{
  PyObject *types= Py_BuildValue("(I)", (uint32_t)type);
  PyObject *number= PyObject_CallObject((PyObject *)&Mariadb_DBAPIType_Type,
                                        types);
  Py_DECREF(types);
  return number;
}
/* }}} */

/*{{{ Mariadb_xid */
PyObject *MrdbConnection_xid(MrdbConnection *self, PyObject *args)
{
  PyObject *xid= NULL;
  char     *format_id= NULL,
           *transaction_id= NULL;
  int      *branch_qualifier= NULL;

  if (!PyArg_ParseTuple(args, "ssi", &format_id,
                                     &transaction_id,
                                     &branch_qualifier))
    return NULL;

  if (!(xid= Py_BuildValue("(ssi)", format_id,
                                    transaction_id,
                                    branch_qualifier)))
    return NULL;

  return xid;
}
/* }}} */

/* {{{ MrdbConnection_tpc_begin */
PyObject *MrdbConnection_tpc_begin(MrdbConnection *self, PyObject *args)
{
  char *transaction_id= 0,
       *format_id=0;
  long branch_qualifier= 0;
  char stmt[128];
  int rc= 0;

  if (!PyArg_ParseTuple(args, "(ssi)", &format_id,
                                       &transaction_id,
                                       &branch_qualifier))
    return NULL;

  /* MariaDB ignores format_id and branch_qualifier */
  snprintf(stmt, 127, "XA BEGIN '%s'", transaction_id);
  Py_BEGIN_ALLOW_THREADS;
  rc= mysql_query(self->mysql, stmt);
  Py_END_ALLOW_THREADS;

  if (rc)
  {
    mariadb_throw_exception(self->mysql, NULL, 0, NULL);
    return NULL;
  }
  self->tpc_state= TPC_STATE_XID;
  strncpy(self->xid, transaction_id, MAX_TPC_XID_SIZE - 1);

  Py_RETURN_NONE;
}
/* }}} */

/* {{{ MrdbConnection_tpc_commit */
PyObject *MrdbConnection_tpc_commit(MrdbConnection *self, PyObject *args)
{
  char *transaction_id= 0,
       *format_id=0;
  long branch_qualifier= 0;
  char stmt[128];

  MARIADB_CHECK_CONNECTION(self, NULL);
  MARIADB_CHECK_TPC(self);

  if (!PyArg_ParseTuple(args, "|(ssi)", &format_id,
                                        &transaction_id,
                                        &branch_qualifier))
    return NULL;

  if (!args && self->tpc_state != TPC_STATE_PREPARE)
  {
    mariadb_throw_exception(NULL, Mariadb_ProgrammingError, 0,
       "transaction is not in prepared state");
    return NULL;
  }

  Py_BEGIN_ALLOW_THREADS;
  if (self->tpc_state < TPC_STATE_PREPARE)
  {
    snprintf(stmt, 127, "XA END '%s'", transaction_id ?
             transaction_id : self->xid);
    if (mysql_query(self->mysql, stmt))
    {
      mariadb_throw_exception(self->mysql, NULL, 0, NULL);
      goto end;
    }
  }
  snprintf(stmt, 127, "XA COMMIT '%s' %s", transaction_id ?
           transaction_id : self->xid,
           self->tpc_state < TPC_STATE_PREPARE ? "ONE PHASE" : "");
  if (mysql_query(self->mysql, stmt))
  {
    mariadb_throw_exception(self->mysql, NULL, 0, NULL);
    goto end;
  }
end:
  Py_END_ALLOW_THREADS;

  if (PyErr_Occurred())
    return NULL;
  self->xid[0]= 0;
  self->tpc_state= TPC_STATE_NONE;

  Py_RETURN_NONE;
}
/* }}} */

/* {{{ MrdbConnection_tpc_rollback */
PyObject *MrdbConnection_tpc_rollback(MrdbConnection *self, PyObject *args)
{
  char *transaction_id= 0,
       *format_id=0;
  long branch_qualifier= 0;
  char stmt[128];

  MARIADB_CHECK_CONNECTION(self, NULL);
  MARIADB_CHECK_TPC(self);

  if (!PyArg_ParseTuple(args, "|(ssi)", &format_id,
                                        &transaction_id,
                                        &branch_qualifier))
    return NULL;

  if (!args && self->tpc_state != TPC_STATE_PREPARE)
  {
    mariadb_throw_exception(NULL, Mariadb_ProgrammingError, 0,
       "transaction is not in prepared state");
    return NULL;
  }
  Py_BEGIN_ALLOW_THREADS;
  if (self->tpc_state < TPC_STATE_PREPARE)
  {
    snprintf(stmt, 127, "XA END '%s'", transaction_id ? 
             transaction_id : self->xid);
    if (mysql_query(self->mysql, stmt))
    {
      mariadb_throw_exception(self->mysql, NULL, 0, NULL);
      goto end;
    }
  }
  snprintf(stmt, 127, "XA ROLLBACK '%s'", transaction_id ?
           transaction_id : self->xid);
  if (mysql_query(self->mysql, stmt))
  {
    mariadb_throw_exception(self->mysql, NULL, 0, NULL);
    goto end;
  }
end:
  Py_END_ALLOW_THREADS;

  if (PyErr_Occurred())
    return NULL;

  self->xid[0]= 0;
  self->tpc_state= TPC_STATE_NONE;
  Py_RETURN_NONE;
}
/* }}} */

/* {{{ MrdbConnection_tpc_prepare */
PyObject *MrdbConnection_tpc_prepare(MrdbConnection *self)
{
  char stmt[128];

  MARIADB_CHECK_CONNECTION(self, NULL);
  MARIADB_CHECK_TPC(self);

  if (self->tpc_state == TPC_STATE_PREPARE)
  {
    mariadb_throw_exception(NULL, Mariadb_ProgrammingError, 0,
       "transaction is already in prepared state");
    return NULL;
  }
  snprintf(stmt, 127, "XA END '%s'", self->xid);
  Py_BEGIN_ALLOW_THREADS;
  if (mysql_query(self->mysql, stmt))
  {
    mariadb_throw_exception(self->mysql, NULL, 0, NULL);
    goto end;
  }

  snprintf(stmt, 127, "XA PREPARE '%s'", self->xid);
  if (mysql_query(self->mysql, stmt))
  {
    mariadb_throw_exception(self->mysql, NULL, 0, NULL);
    goto end;
  }
end:
  Py_END_ALLOW_THREADS;
  if (PyErr_Occurred())
    return NULL;

  self->tpc_state= TPC_STATE_PREPARE;
  Py_RETURN_NONE;
}
/* }}} */

/* {{{ MrdbConnection_tpc_recover */
PyObject *MrdbConnection_tpc_recover(MrdbConnection *self)
{
  PyObject *List= NULL;
  MYSQL_RES *result;
  MYSQL_ROW row;

  MARIADB_CHECK_CONNECTION(self, NULL);
  MARIADB_CHECK_TPC(self);

  Py_BEGIN_ALLOW_THREADS;
  if (mysql_query(self->mysql, "XA RECOVER"))
  {
    mariadb_throw_exception(self->mysql, NULL, 0, NULL);
    goto end;
  }

  if (!(result= mysql_store_result(self->mysql)))
  {
    mariadb_throw_exception(self->mysql, NULL, 0, NULL);
    goto end;
  }

  if (!(List= PyList_New(0)))
    return NULL;

  /* if there are no rows, return an empty list */
  if (!mysql_num_rows(result))
  {
    mysql_free_result(result);
    return List;
  }

  while ((row= mysql_fetch_row(result)))
  {
    PyObject *tpl= Py_BuildValue("(ssss)", row[0], row[1], row[2], row[3]);
    PyList_Append(List, tpl);
    Py_DECREF(tpl);
  }

  mysql_free_result(result);
end:
  Py_END_ALLOW_THREADS;
  if (PyErr_Occurred())
    return NULL;
  return List;
}
/* }}} */

/* {{{ MrdbConnection_ping */
PyObject *MrdbConnection_ping(MrdbConnection *self)
{
  int rc;

  Py_BEGIN_ALLOW_THREADS;
  rc= mysql_ping(self->mysql);
  Py_END_ALLOW_THREADS;

  if (rc)
  {
    mariadb_throw_exception(self->mysql, NULL, 0, NULL);
    return NULL;
  }
  Py_RETURN_NONE;
}
/* }}} */

/* {{{ MrdbConnection_change_user */
PyObject *MrdbConnection_change_user(MrdbConnection *self,
                                     PyObject *args)
{
  const char *user= NULL,
             *password= NULL,
             *database= NULL;
  int rc= 0;
  MARIADB_CHECK_CONNECTION(self, NULL);

  if (!PyArg_ParseTuple(args, "sss", &user, &password, &database))
    return NULL;

  Py_BEGIN_ALLOW_THREADS;
  rc= mysql_change_user(self->mysql, user, password, database);
  Py_END_ALLOW_THREADS;

  if (rc)
  {
    mariadb_throw_exception(self->mysql, NULL, 0, NULL);
    return NULL;
  }
  Py_RETURN_NONE;
}
/* }}} */

/* {{{ MrdbConnection_kill */
PyObject *MrdbConnection_kill(MrdbConnection *self, PyObject *args)
{
  int rc;
  unsigned long thread_id= 0;

  MARIADB_CHECK_CONNECTION(self, NULL);
  if (!PyArg_ParseTuple(args, "l", &thread_id))
    return NULL;

  Py_BEGIN_ALLOW_THREADS;
  rc= mysql_kill(self->mysql, thread_id);
  Py_END_ALLOW_THREADS;

  if (rc)
  {
    mariadb_throw_exception(self->mysql, Mariadb_DatabaseError, 0, NULL);
    return NULL;
  }
  Py_RETURN_NONE;
}

/* {{{ MrdbConnection_getid */
static PyObject *MrdbConnection_getid(MrdbConnection *self, void *closure)
{
  PyObject *p;

  MARIADB_CHECK_CONNECTION(self, NULL);
  p= PyLong_FromUnsignedLong(mysql_thread_id(self->mysql));
  return p;
}
/* }}} */

/* {{{ MrdbConnection_getreconnect */
static PyObject *MrdbConnection_getreconnect(MrdbConnection *self,
                                             void *closure)
{
  uint8_t reconnect= 0;

  if (self->mysql)
    mysql_get_option(self->mysql, MYSQL_OPT_RECONNECT, &reconnect);

  if (reconnect)
    Py_RETURN_TRUE;

  Py_RETURN_FALSE;
}
/* }}} */

/* MrdbConnection_setreconnect */
static int MrdbConnection_setreconnect(MrdbConnection *self,
                                             PyObject *args,
                                             void *closure)
{
  uint8_t reconnect;

  if (!self->mysql)
    return 0;

  if (!args || Py_TYPE(args) != &PyBool_Type)
  {
    PyErr_SetString(PyExc_TypeError, "Argument must be boolean");
    return -1;
  }

  reconnect= PyObject_IsTrue(args);
  mysql_optionsv(self->mysql, MYSQL_OPT_RECONNECT, &reconnect);
  return 0;
}
/* }}} */

/* {{{ MrdbConnection_getuser */
static PyObject *MrdbConnection_getuser(MrdbConnection *self, void *closure)
{
  PyObject *p;
  char *user= NULL;

  MARIADB_CHECK_CONNECTION(self, NULL);

  mariadb_get_infov(self->mysql, MARIADB_CONNECTION_USER, &user);
  p= PyUnicode_FromString(user);
  return p;
}
/* }}} */

/* {{{ MrdbConnection_setdb */
static int MrdbConnection_setdb(MrdbConnection *self, PyObject *db,
                                 void *closure)
{
  int rc= 0;
  char *schema;

  MARIADB_CHECK_CONNECTION(self, -1);

  if (!db || Py_TYPE(db) != &PyUnicode_Type)
  {
    PyErr_SetString(PyExc_TypeError, "Argument must be string");
    return -1;
  }
  schema= PyUnicode_AsUTF8(db);

  Py_BEGIN_ALLOW_THREADS;
  rc= mysql_select_db(self->mysql, schema);
  Py_END_ALLOW_THREADS;

  if (rc)
  {
    mariadb_throw_exception(self->mysql, Mariadb_DatabaseError, 0, NULL);
    return -1;
  }
  return 0;
}
/* }}} */

/* {{{ MrdbConnection_getdb */
static PyObject *MrdbConnection_getdb(MrdbConnection *self, void *closure)
{
  PyObject *p;
  char *db= NULL;

  MARIADB_CHECK_CONNECTION(self, NULL);

  mariadb_get_infov(self->mysql, MARIADB_CONNECTION_SCHEMA, &db);
  p= PyUnicode_FromString(db);
  return p;
}
/* }}} */

/* {{{ MrdbConnection_reconnect */
PyObject *MrdbConnection_reconnect(MrdbConnection *self)
{
  int rc;
  uint8_t reconnect= 1;
  uint8_t save_reconnect;

  MARIADB_CHECK_CONNECTION(self, NULL);

  mysql_get_option(self->mysql, MYSQL_OPT_RECONNECT, &save_reconnect);
  if (!save_reconnect)
    mysql_optionsv(self->mysql, MYSQL_OPT_RECONNECT, &reconnect);

  Py_BEGIN_ALLOW_THREADS;
  rc= mariadb_reconnect(self->mysql);
  Py_END_ALLOW_THREADS;

  if (!save_reconnect)
    mysql_optionsv(self->mysql, MYSQL_OPT_RECONNECT, &save_reconnect);

  if (rc)
  {
    mariadb_throw_exception(self->mysql, NULL, 0, NULL);
    return NULL;
  }
  Py_RETURN_NONE;
}
/* }}} */

/* {{{ MrdbConnection_reset */
PyObject *MrdbConnection_reset(MrdbConnection *self)
{
  int rc;
  MARIADB_CHECK_CONNECTION(self, NULL);

  Py_BEGIN_ALLOW_THREADS;
  rc= mysql_reset_connection(self->mysql);
  Py_END_ALLOW_THREADS;

  if (rc)
  {
    mariadb_throw_exception(self->mysql, NULL, 0, NULL);
    return NULL;
  }
  Py_RETURN_NONE;
}
/* }}} */

/* {{{ MrdbConnection_warnings */
static PyObject *MrdbConnection_warnings(MrdbConnection *self)
{
  MARIADB_CHECK_CONNECTION(self, NULL);

  return PyLong_FromLong((long)mysql_warning_count(self->mysql));
}
/* }}} */

/* {{{ MrdbConnection_escape_string */
static PyObject *MrdbConnection_escape_string(MrdbConnection *self,
                                              PyObject *args)
{
  PyObject *string= NULL,
           *new_string= NULL;
  size_t from_length, to_length;
  char *from, *to;

  /* escaping depends on the server status, so we need a valid
     connection */
  MARIADB_CHECK_CONNECTION(self, NULL);

  if (!PyArg_ParseTuple(args, "O!", &PyUnicode_Type, &string))
    return NULL;

  from= PyUnicode_AsUTF8AndSize(string, (Py_ssize_t *)&from_length);
  to= (char *)alloca(from_length * 2 + 1);
  to_length= mysql_real_escape_string(self->mysql, to, from, from_length);
  new_string= PyUnicode_FromStringAndSize(to, to_length);
  return new_string;
}
/* }}} */

/* {{{ MrdbConnection_server_version */
static PyObject *MrdbConnection_server_version(MrdbConnection *self)
{
  MARIADB_CHECK_CONNECTION(self, NULL);
  return PyLong_FromLong((long)mysql_get_server_version(self->mysql));
}
/* }}} */

/* {{{ MrdbConnection_server_info */
static PyObject *MrdbConnection_server_info(MrdbConnection *self)
{
  MARIADB_CHECK_CONNECTION(self, NULL);
  return PyUnicode_FromString(mysql_get_server_info(self->mysql));
}
/* }}} */

