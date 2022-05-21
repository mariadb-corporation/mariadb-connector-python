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
 *****************************************************************************/

#include "mariadb_python.h"
#include "docs/connection.h"
#include "docs/exception.h"

#define MADB_SET_OPTION(m,o,v)\
if (mysql_optionsv((m), (o), (v)))\
{\
    mariadb_throw_exception(self->mysql, NULL, 0, NULL);\
    return -1;\
}

char *dsn_keys[]= {
    "dsn", "host", "user", "password", "database", "port", "unix_socket",
    "connect_timeout", "read_timeout", "write_timeout",
    "local_infile", "compress", "init_command",
    "default_file", "default_group",
    "ssl_key", "ssl_ca", "ssl_cert", "ssl_crl",
    "ssl_cipher", "ssl_capath", "ssl_crlpath",
    "ssl_verify_cert", "ssl",
    "client_flag", "pool_name", "pool_size", 
    "pool_reset_connection", "plugin_dir",
    "username", "db", "passwd",
    NULL
};

const char *mariadb_default_charset= "utf8mb4";
const char *mariadb_default_collation= "utf8mb4_general_ci";

void
MrdbConnection_dealloc(MrdbConnection *self);

static PyObject *
MrdbConnection_exception(PyObject *self, void *closure);

#define GETTER_EXCEPTION(name, exception, doc)\
{ name,MrdbConnection_exception, NULL, doc, &exception }

static PyObject *
MrdbConnection_getreconnect(MrdbConnection *self, void *closure);

static int
MrdbConnection_setreconnect(MrdbConnection *self, PyObject *args,
                            void *closure);
static PyObject *
MrdbConnection_escape_string(MrdbConnection *self, PyObject *args);

static PyObject *
MrdbConnection_getinfo(MrdbConnection *self, PyObject *args);

static PyObject *
MrdbConnection_dump_debug_info(MrdbConnection *self);

static PyObject *
MrdbConnection_warnings(MrdbConnection *self);

static PyObject *
MrdbConnection_executecommand(MrdbConnection *self,
                             PyObject *args);

static PyObject *
MrdbConnection_readresponse(MrdbConnection *self);

static PyGetSetDef
MrdbConnection_sets[]=
{
    {"auto_reconnect", (getter)MrdbConnection_getreconnect,
        (setter)MrdbConnection_setreconnect,
        connection_auto_reconnect__doc__, NULL},
    {"warnings", (getter)MrdbConnection_warnings, NULL,
        connection_warnings__doc__, NULL},
    GETTER_EXCEPTION("Error", Mariadb_Error, ""),
    GETTER_EXCEPTION("Warning", Mariadb_Warning, exception_warning__doc__),
    GETTER_EXCEPTION("InterfaceError", Mariadb_InterfaceError, exception_interface__doc__),
    GETTER_EXCEPTION("ProgrammingError", Mariadb_ProgrammingError, exception_programming__doc__),
    GETTER_EXCEPTION("IntegrityError", Mariadb_IntegrityError, exception_integrity__doc__),
    GETTER_EXCEPTION("DatabaseError", Mariadb_DatabaseError, exception_database__doc__),
    GETTER_EXCEPTION("NotSupportedError", Mariadb_NotSupportedError, exception_notsupported__doc__),
    GETTER_EXCEPTION("InternalError", Mariadb_InternalError, exception_internal__doc__),
    GETTER_EXCEPTION("OperationalError", Mariadb_OperationalError, exception_operational__doc__),
    GETTER_EXCEPTION("PoolError", Mariadb_OperationalError, exception_pool__doc__),
    GETTER_EXCEPTION("DataError", Mariadb_OperationalError, exception_data__doc__),
    {NULL}
};

static PyMethodDef
MrdbConnection_Methods[] =
{
    /* PEP-249 methods */
    {"close", (PyCFunction)MrdbConnection_close,
        METH_NOARGS,
        connection_close__doc__},
    {"connect", (PyCFunction)MrdbConnection_connect,
        METH_VARARGS | METH_KEYWORDS,
        connection_connect__doc__},
    /* additional methods */
    { "ping",
        (PyCFunction)MrdbConnection_ping,
        METH_NOARGS,
        connection_ping__doc__
    },
    { "change_user",
        (PyCFunction)MrdbConnection_change_user,
        METH_VARARGS,
        connection_change_user__doc__
    },
    { "reconnect",
        (PyCFunction)MrdbConnection_reconnect,
        METH_NOARGS,
        connection_reconnect__doc__
    },
    { "reset",
        (PyCFunction)MrdbConnection_reset,
        METH_NOARGS,
        connection_reset__doc__,
    },
    { "escape_string",
        (PyCFunction)MrdbConnection_escape_string,
        METH_VARARGS,
        connection_escape_string__doc__
    },
    { "dump_debug_info",
       (PyCFunction)MrdbConnection_dump_debug_info,
       METH_NOARGS,
       connection_dump_debug_info__doc__
    },
    /* Internal methods */
    { "_execute_command", 
      (PyCFunction)MrdbConnection_executecommand,
      METH_VARARGS,
      "For internal use only"},
    {"_read_response", (PyCFunction)MrdbConnection_readresponse,
      METH_NOARGS,
      "For internal use only"},
    {"_mariadb_get_info", (PyCFunction)MrdbConnection_getinfo,
      METH_VARARGS,
      "For internal use only"},
    {NULL} /* always last */
};

static struct
PyMemberDef MrdbConnection_Members[] =
{
    {"connection_id",
        T_LONG,
        offsetof(MrdbConnection, thread_id),
        READONLY,
        "Id of current connection."},
    {"dsn",
        T_OBJECT,
        offsetof(MrdbConnection, dsn),
        READONLY,
        "Data source name (dsn)"},
    {"_closed",
        T_BOOL,
        offsetof(MrdbConnection, closed),
        READONLY,
        "Indicates if connection was closed"},
    {NULL} /* always last */
};

static int
MrdbConnection_Initialize(MrdbConnection *self,
        PyObject *args,
        PyObject *dsnargs)
{
    uint8_t has_error= 1;
    char *dsn= NULL, *host=NULL, *user= NULL, *password= NULL, *schema= NULL,
         *socket= NULL, *init_command= NULL, *default_file= NULL,
         *default_group= NULL,
         *ssl_key= NULL, *ssl_cert= NULL, *ssl_ca= NULL, *ssl_capath= NULL,
         *ssl_crl= NULL, *ssl_crlpath= NULL, *ssl_cipher= NULL,
         *plugin_dir= NULL;
    char *pool_name= 0;
    uint32_t pool_size= 0;
    uint8_t ssl_enforce= 0;
    uint8_t reset_session= 1;
    unsigned int client_flags= 0, port= 0;
    unsigned int local_infile= 0xFF;
    unsigned int connect_timeout=0, read_timeout=0, write_timeout=0,
                 compress= 0, ssl_verify_cert= 0;

    if (!PyArg_ParseTupleAndKeywords(args, dsnargs,
                "|zzzzziziiibbzzzzzzzzzzibizibzzzz:connect",
                dsn_keys,
                &dsn, &host, &user, &password, &schema, &port, &socket,
                &connect_timeout, &read_timeout, &write_timeout,
                &local_infile, &compress, &init_command,
                &default_file, &default_group,
                &ssl_key, &ssl_ca, &ssl_cert, &ssl_crl,
                &ssl_cipher, &ssl_capath, &ssl_crlpath,
                &ssl_verify_cert, &ssl_enforce,
                &client_flags, &pool_name, &pool_size,
                &reset_session, &plugin_dir,
                &user, &schema, &password))
    {
        return -1;
    }

    if (dsn)
    {
        mariadb_throw_exception(NULL, Mariadb_ProgrammingError, 1,
                "dsn keyword is not supported");
        return -1;
    }

    if (!(self->mysql= mysql_init(NULL)))
    {
        mariadb_throw_exception(self->mysql, Mariadb_OperationalError, 1,
            "Can't allocate memory for connection");
        return -1;
    }

    Py_BEGIN_ALLOW_THREADS;
    if (mysql_options(self->mysql, MYSQL_SET_CHARSET_NAME, mariadb_default_charset))
       goto end;

    if (local_infile != 0xFF)
    {
        if (mysql_options(self->mysql, MYSQL_OPT_LOCAL_INFILE, &local_infile))
          goto end;
    }

    if (compress)
    {
        if (mysql_options(self->mysql, MYSQL_OPT_COMPRESS, "1"))
          goto end;
    }

    if (init_command)
    {
        if (mysql_options(self->mysql, MYSQL_INIT_COMMAND, init_command))
          goto end;
    }

    if (plugin_dir) {
        if (mysql_options(self->mysql, MYSQL_PLUGIN_DIR, plugin_dir))
          goto end;
    } else {
#if defined(DEFAULT_PLUGINS_SUBDIR)
      if (mysql_options(self->mysql, MYSQL_PLUGIN_DIR, DEFAULT_PLUGINS_SUBDIR))
        goto end;
#endif
    }

    /* read defaults from configuration file(s) */
    if (default_file)
    {
        if (mysql_options(self->mysql, MYSQL_READ_DEFAULT_FILE, default_file))
          goto end;
    }
    if (default_group)
    {
        if (mysql_options(self->mysql, MYSQL_READ_DEFAULT_GROUP, default_group))
          goto end;
    }

    /* set timeouts */
    if (connect_timeout)
    {
        if (mysql_options(self->mysql, MYSQL_OPT_CONNECT_TIMEOUT, &connect_timeout))
          goto end;
    }
    if (read_timeout)
    {
        if (mysql_options(self->mysql, MYSQL_OPT_READ_TIMEOUT, &read_timeout))
          goto end;
    }
    if (write_timeout)
    {
        if (mysql_options(self->mysql, MYSQL_OPT_WRITE_TIMEOUT, &write_timeout))
          goto end;
    }

    /* set TLS/SSL options */
    if (ssl_enforce || ssl_key || ssl_ca || ssl_cert || ssl_capath || ssl_cipher)
        mysql_ssl_set(self->mysql, (const char *)ssl_key,
                (const char *)ssl_cert,
                (const char *)ssl_ca,
                (const char *)ssl_capath,
                (const char *)ssl_cipher);
    if (ssl_crl)
    {
        if (mysql_options(self->mysql, MYSQL_OPT_SSL_CRL, ssl_crl))
          goto end;
    }
    if (ssl_crlpath)
    {
        if (mysql_options(self->mysql, MYSQL_OPT_SSL_CRLPATH, ssl_crlpath))
          goto end;
    }
    if (ssl_verify_cert)
    {
        if (mysql_options(self->mysql, MYSQL_OPT_SSL_VERIFY_SERVER_CERT, (unsigned char *) &ssl_verify_cert))
          goto end;
    }

    mysql_real_connect(self->mysql, host, user, password, schema, port,
            socket, client_flags);
   
    if (mysql_errno(self->mysql))
    {
        goto end;
    }

    self->thread_id= mysql_thread_id(self->mysql);
    mariadb_get_infov(self->mysql, MARIADB_CONNECTION_HOST, (void *)&self->host);

    has_error= 0;
end:
    Py_END_ALLOW_THREADS;

    if (has_error)
    {
          mariadb_throw_exception(self->mysql, NULL, 0, NULL);
          return -1;
    }

    if (PyErr_Occurred())
        return -1;

    return 0;
}

static int MrdbConnection_traverse(
        MrdbConnection *self,
        visitproc visit,
        void *arg)
{
    return 0;
}

static PyObject *MrdbConnection_repr(MrdbConnection *self)
{
    char cobj_repr[384];

    if (!self->closed)
        snprintf(cobj_repr, 384, "<mariadb.connection connected to '%s' at %p>",
                self->host, self);
    else
        snprintf(cobj_repr, 384, "<mariadb.connection (closed) at %p>",
                self);
    return PyUnicode_FromString(cobj_repr);
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
    (reprfunc)MrdbConnection_repr, /* tp_repr */

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
    connection__doc__, /* tp_doc Documentation string */

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
void MrdbConnection_dealloc(MrdbConnection *self)
{
    if (self)
    {
        if (self->mysql)
        {
            Py_BEGIN_ALLOW_THREADS
            mysql_close(self->mysql);
            Py_END_ALLOW_THREADS
            self->mysql= NULL;
        }
        Py_TYPE(self)->tp_free((PyObject*)self);
    }
}

static PyObject *
MrdbConnection_executecommand(MrdbConnection *self,
                             PyObject *args)
{
  char *cmd;
  int rc;

  MARIADB_CHECK_CONNECTION(self, NULL);
  if (!PyArg_ParseTuple(args, "s", &cmd))
    return NULL;

  Py_BEGIN_ALLOW_THREADS;
  rc= mysql_send_query(self->mysql, cmd, (long)strlen(cmd));
  Py_END_ALLOW_THREADS;

  if (rc)
  {
      mariadb_throw_exception(self->mysql, NULL, 0, NULL);
      return NULL;
  }
  Py_RETURN_NONE;
}

PyObject *MrdbConnection_close(MrdbConnection *self)
{
    MARIADB_CHECK_CONNECTION(self, NULL);
    /* Todo: check if all the cursor stuff is deleted (when using prepared
       statements this should be handled in mysql_close) */

    Py_BEGIN_ALLOW_THREADS
    mysql_close(self->mysql);
    Py_END_ALLOW_THREADS
    self->mysql= NULL;
    self->closed= 1;
    Py_RETURN_NONE;
}

static PyObject *
MrdbConnection_exception(PyObject *self, void *closure)
{
    PyObject *exception = *(PyObject **)closure;

    Py_INCREF(exception);
    return exception;
}

/* {{{ MrdbConnection_ping */
PyObject *MrdbConnection_ping(MrdbConnection *self)
{
    int rc;

    MARIADB_CHECK_CONNECTION(self, NULL);

    Py_BEGIN_ALLOW_THREADS;
    rc= mysql_ping(self->mysql);
    Py_END_ALLOW_THREADS;

    if (rc) {
        mariadb_throw_exception(self->mysql, Mariadb_InterfaceError, 0, NULL);
        return NULL;
    }

    /* in case a reconnect occured, we need to obtain new thread_id */
    self->thread_id= mysql_thread_id(self->mysql);

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

/* {{{ MrdbConnection_getreconnect */
static PyObject *MrdbConnection_getreconnect(MrdbConnection *self,
        void *closure)
{
    uint8_t reconnect= 0;

    if (self->mysql) {
        mysql_get_option(self->mysql, MYSQL_OPT_RECONNECT, &reconnect);
    }

    if (reconnect) {
        Py_RETURN_TRUE;
    }

    Py_RETURN_FALSE;
}
/* }}} */

/* MrdbConnection_setreconnect */
static int MrdbConnection_setreconnect(MrdbConnection *self,
        PyObject *args,
        void *closure)
{
    uint8_t reconnect;

    if (!self->mysql) {
        return 0;
    }

    if (!args || !CHECK_TYPE(args, &PyBool_Type)) {
        PyErr_SetString(PyExc_TypeError, "Argument must be boolean");
        return -1;
    }

    reconnect= PyObject_IsTrue(args);
    mysql_optionsv(self->mysql, MYSQL_OPT_RECONNECT, &reconnect);
    return 0;
}
/* }}} */

static PyObject *
MrdbConnection_getinfo(MrdbConnection *self, PyObject *args)
{
    union {
        char *str;
        uint64_t num;
        uint8_t b;
    } val;

    PyObject *type;

    uint32_t option;

    if (!PyArg_ParseTuple(args, "iO", &option, &type))
          return NULL;

    memset(&val, 0, sizeof(val));

    if (mariadb_get_infov(self->mysql, option, &val))
    {
        mariadb_throw_exception(NULL, Mariadb_ProgrammingError, 1,
                                "Parameter option not supported");
        return NULL;
    }

    if ((PyTypeObject *)type == &PyUnicode_Type)
    {
        return PyUnicode_FromString(val.str ? val.str : "");
    }
    if ((PyTypeObject *)type == &PyLong_Type)
        return PyLong_FromLong((long)val.num);
    if ((PyTypeObject *)type == &PyBool_Type)
        return val.b ? Py_True : Py_False;
    Py_RETURN_NONE;
}

/* {{{ MrdbConnection_reconnect */
PyObject *MrdbConnection_reconnect(MrdbConnection *self)
{
    int rc;
    uint8_t reconnect= 1;
    uint8_t save_reconnect;

    MARIADB_CHECK_CONNECTION(self, NULL);

    mysql_get_option(self->mysql, MYSQL_OPT_RECONNECT, &save_reconnect);
    /* coverity[copy_paste_error] */
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
    /* get capabilities */
    self->thread_id= mysql_thread_id(self->mysql);
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

    from= (char *)PyUnicode_AsUTF8AndSize(string, (Py_ssize_t *)&from_length);
    if (!(to= (char *)PyMem_RawCalloc(1, from_length * 2 + 1)))
    {
        return NULL;
    }
    to_length= mysql_real_escape_string(self->mysql, to, from, (unsigned long)from_length);
    new_string= PyUnicode_FromStringAndSize(to, to_length);
    PyMem_Free(to);
    return new_string;
}
/* }}} */

static PyObject *
MrdbConnection_dump_debug_info(MrdbConnection *self)
{
    int rc;
    MARIADB_CHECK_CONNECTION(self, NULL);

    Py_BEGIN_ALLOW_THREADS;
    rc= mysql_dump_debug_info(self->mysql);
    Py_END_ALLOW_THREADS;

    if (rc)
    {
        mariadb_throw_exception(self->mysql, NULL, 0, NULL);
        return NULL;
    }
    Py_RETURN_NONE;
}

static PyObject *MrdbConnection_readresponse(MrdbConnection *self)
{
    int rc;

    Py_BEGIN_ALLOW_THREADS;
    rc= self->mysql->methods->db_read_query_result(self->mysql);
    Py_END_ALLOW_THREADS;

    if (rc)
    {
        mariadb_throw_exception(self->mysql, NULL, 0, NULL);
        return NULL;
    }
    Py_RETURN_NONE;
}

/* vim: set tabstop=4 */
/* vim: set shiftwidth=4 */
/* vim: set expandtab */
/* vim: set foldmethod=indent */
/* vim: set foldnestmax=10 */
/* vim: set nofoldenable */
/* vim: set foldlevel=2 */
