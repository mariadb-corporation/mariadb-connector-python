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
    "converter", "asynchronous",
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
MrdbConnection_getuser(MrdbConnection *self, void *closure);

static PyObject *
MrdbConnection_getreconnect(MrdbConnection *self, void *closure);

static int
MrdbConnection_setreconnect(MrdbConnection *self, PyObject *args,
                            void *closure);
static PyObject *
MrdbConnection_getdb(MrdbConnection *self, void *closure);

static int
MrdbConnection_setdb(MrdbConnection *self, PyObject *arg, void *closure);

static PyObject *
MrdbConnection_escape_string(MrdbConnection *self, PyObject *args);

static PyObject *
MrdbConnection_warnings(MrdbConnection *self);

static PyObject *
MrdbConnection_get_server_status(MrdbConnection *self);

static PyObject *
MrdbConnection_executecommand(MrdbConnection *self,
                             PyObject *args);

static PyObject *
MrdbConnection_readresponse(MrdbConnection *self);

static PyGetSetDef
MrdbConnection_sets[]=
{
    {"database", (getter)MrdbConnection_getdb, (setter)MrdbConnection_setdb,
        connection_database__doc__, NULL},
    {"auto_reconnect", (getter)MrdbConnection_getreconnect,
        (setter)MrdbConnection_setreconnect,
        connection_auto_reconnect__doc__, NULL},
    {"user", (getter)MrdbConnection_getuser, NULL, connection_user__doc__, 
        NULL},
    {"warnings", (getter)MrdbConnection_warnings, NULL,
        connection_warnings__doc__, NULL},
    {"_server_status", (getter)MrdbConnection_get_server_status, NULL,
        NULL, NULL},
    GETTER_EXCEPTION("Error", Mariadb_Error, ""),
    GETTER_EXCEPTION("Warning", Mariadb_Warning, ""),
    GETTER_EXCEPTION("InterfaceError", Mariadb_InterfaceError, ""),
    GETTER_EXCEPTION("ProgrammingError", Mariadb_ProgrammingError, ""),
    GETTER_EXCEPTION("IntegrityError", Mariadb_IntegrityError, ""),
    GETTER_EXCEPTION("DatabaseError", Mariadb_DatabaseError, ""),
    GETTER_EXCEPTION("NotSupportedError", Mariadb_NotSupportedError, ""),
    GETTER_EXCEPTION("InternalError", Mariadb_InternalError, ""),
    GETTER_EXCEPTION("OperationalError", Mariadb_OperationalError, ""),
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
    /* Internal methods */
    { "_execute_command", 
      (PyCFunction)MrdbConnection_executecommand,
      METH_VARARGS,
      NULL
    },
    {"_read_response", (PyCFunction)MrdbConnection_readresponse,
        METH_NOARGS,
        NULL},
    {NULL} /* always last */
};

static struct
PyMemberDef MrdbConnection_Members[] =
{
    {"character_set",
        T_STRING,
        offsetof(MrdbConnection, charset),
        READONLY,
        "Client character set"},
    {"converter",
        T_OBJECT,
        offsetof(MrdbConnection, converter),
        READONLY,
        "Conversion dictionary"},
    {"connection_id",
        T_ULONG,
        offsetof(MrdbConnection, thread_id),
        READONLY,
        connection_connection_id__doc__},
    {"collation",
        T_STRING,
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
    {"server_version",
        T_ULONG,
        offsetof(MrdbConnection, server_version),
        READONLY,
        "Server version"},
    {"server_info",
        T_STRING,
        offsetof(MrdbConnection, server_info),
        READONLY,
        "Server info"},
    {"unix_socket",
        T_STRING,
        offsetof(MrdbConnection, unix_socket),
        READONLY,
        "Unix socket name"},
    {"server_name",
        T_STRING,
        offsetof(MrdbConnection, host),
        READONLY,
        "Name or address of database server"},
    {"tls_cipher",
        T_STRING,
        offsetof(MrdbConnection, tls_cipher),
        READONLY,
        "TLS cipher suite in used by connection"},
    {"tls_version",
        T_STRING,
        offsetof(MrdbConnection, tls_version),
        READONLY,
        "TLS protocol version used by connection"},
    {"client_capabilities",
        T_ULONG,
        offsetof(MrdbConnection, client_capabilities),
        READONLY,
        "Client capabilities"},
    {"server_capabilities",
        T_ULONG,
        offsetof(MrdbConnection, server_capabilities),
        READONLY,
        "Server capabilities"},
    {NULL} /* always last */
};

static void MrdbConnection_GetCapabilities(MrdbConnection *self)
{
    mariadb_get_infov(self->mysql, MARIADB_CONNECTION_SERVER_CAPABILITIES,
        &self->server_capabilities);
    mariadb_get_infov(self->mysql, MARIADB_CONNECTION_EXTENDED_SERVER_CAPABILITIES,
        &self->extended_server_capabilities);
    mariadb_get_infov(self->mysql, MARIADB_CONNECTION_CLIENT_CAPABILITIES,
        &self->client_capabilities);
}

void MrdbConnection_SetAttributes(MrdbConnection *self)
{
    mariadb_get_infov(self->mysql, MARIADB_CONNECTION_HOST, &self->host);
    mariadb_get_infov(self->mysql, MARIADB_CONNECTION_SSL_CIPHER, &self->tls_cipher);
    mariadb_get_infov(self->mysql, MARIADB_CONNECTION_TLS_VERSION, &self->tls_version);
    mariadb_get_infov(self->mysql, MARIADB_CONNECTION_UNIX_SOCKET, &self->unix_socket);
    mariadb_get_infov(self->mysql, MARIADB_CONNECTION_PORT, &self->port);
    self->charset= mariadb_default_charset;
    self->collation= mariadb_default_collation;
}

static int
MrdbConnection_Initialize(MrdbConnection *self,
        PyObject *args,
        PyObject *dsnargs)
{
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
    PyObject *converter= NULL;
    PyObject *asynchronous= NULL;

    if (!PyArg_ParseTupleAndKeywords(args, dsnargs,
                "|zzzzziziiibbzzzzzzzzzzibizibzzzzO!OO!:connect",
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
                &user, &schema, &password,
                &PyBool_Type, 
                &converter,
                &PyBool_Type, &asynchronous))
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

    if (mysql_options(self->mysql, MYSQL_SET_CHARSET_NAME, mariadb_default_charset))
    {
        mariadb_throw_exception(self->mysql, Mariadb_OperationalError, 1,
            "Can't set default character set.");
        return -1;
    }

    if (converter)
        Py_INCREF(converter);
    else
        if (!(converter= PyDict_New()))
            return 1;
    self->converter= converter;

    if (local_infile != 0xFF)
    {
        MADB_SET_OPTION(self->mysql, MYSQL_OPT_LOCAL_INFILE, &local_infile);
    }

    if (compress)
    {
        MADB_SET_OPTION(self->mysql, MYSQL_OPT_COMPRESS, 1);
    }

    if (init_command)
    {
        MADB_SET_OPTION(self->mysql, MYSQL_INIT_COMMAND, init_command);
    }

    if (plugin_dir) {
        MADB_SET_OPTION(self->mysql, MYSQL_PLUGIN_DIR, plugin_dir);
    } else {
#if defined(DEFAULT_PLUGINS_SUBDIR)
        MADB_SET_OPTION(self->mysql, MYSQL_PLUGIN_DIR, DEFAULT_PLUGINS_SUBDIR);
#endif
    }

    /* read defaults from configuration file(s) */
    if (default_file)
    {
        MADB_SET_OPTION(self->mysql, MYSQL_READ_DEFAULT_FILE, default_file);
    }
    if (default_group)
    {
        MADB_SET_OPTION(self->mysql, MYSQL_READ_DEFAULT_GROUP, default_group);
    }

    /* set timeouts */
    if (connect_timeout)
    {
        MADB_SET_OPTION(self->mysql, MYSQL_OPT_CONNECT_TIMEOUT, &connect_timeout);
    }
    if (read_timeout)
    {
        MADB_SET_OPTION(self->mysql, MYSQL_OPT_READ_TIMEOUT, &read_timeout);
    }
    if (write_timeout)
    {
        MADB_SET_OPTION(self->mysql, MYSQL_OPT_WRITE_TIMEOUT, &write_timeout);
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
        MADB_SET_OPTION(self->mysql, MYSQL_OPT_SSL_CRL, ssl_crl);
    }
    if (ssl_crlpath)
    {
        MADB_SET_OPTION(self->mysql, MYSQL_OPT_SSL_CRLPATH, ssl_crlpath);
    }
    if (ssl_verify_cert)
    {
        MADB_SET_OPTION(self->mysql, MYSQL_OPT_SSL_VERIFY_SERVER_CERT, (unsigned char *) &ssl_verify_cert);
    }

    Py_BEGIN_ALLOW_THREADS;
    mysql_real_connect(self->mysql, host, user, password, schema, port,
            socket, client_flags);
    Py_END_ALLOW_THREADS;
   
    if (mysql_errno(self->mysql))
    {
        mariadb_throw_exception(self->mysql, NULL, 0, NULL);
        goto end;
    }

    self->thread_id= mysql_thread_id(self->mysql);

    /* CONPY-129: server_version_info */
    self->server_version= mysql_get_server_version(self->mysql);
    self->server_info= mysql_get_server_info(self->mysql);
/*
    if (asynchronous && PyObject_IsTrue(asynchronous))
    {
        self->asynchronous= 1;
        MADB_SET_OPTION(self->mysql, MARIADB_OPT_SKIP_READ_RESPONSE, &self->asynchronous);
    }
*/
end:
    if (PyErr_Occurred())
        return -1;

    /* set connection attributes */
    MrdbConnection_SetAttributes(self);
    /* get capabilities */
    MrdbConnection_GetCapabilities(self);

    return 0;
}

static int MrdbConnection_traverse(
        MrdbConnection *self,
        visitproc visit,
        void *arg)
{
    if (self->converter)
         return visit(self->converter, arg);
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
  rc= mysql_send_query(self->mysql, cmd, strlen(cmd));
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

    Py_XDECREF(self->converter);
    self->converter= NULL;

    Py_BEGIN_ALLOW_THREADS
    mysql_close(self->mysql);
    Py_END_ALLOW_THREADS
    self->mysql= NULL;
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

    if (!db || !CHECK_TYPE(db, &PyUnicode_Type))
    {
        PyErr_SetString(PyExc_TypeError, "Argument must be string");
        return -1;
    }
    schema= (char *)PyUnicode_AsUTF8(db);

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
    if (db)
      p= PyUnicode_FromString(db);
    else
      p= Py_None;
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
    MrdbConnection_GetCapabilities(self);
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
    to= (char *)alloca(from_length * 2 + 1);
    to_length= mysql_real_escape_string(self->mysql, to, from, (unsigned long)from_length);
    new_string= PyUnicode_FromStringAndSize(to, to_length);
    return new_string;
}
/* }}} */

static PyObject *MrdbConnection_get_server_status(MrdbConnection *self)
{
    uint32_t server_status;

    MARIADB_CHECK_CONNECTION(self, NULL);

    mariadb_get_infov(self->mysql, MARIADB_CONNECTION_SERVER_STATUS, &server_status);
    return PyLong_FromLong((long)server_status);
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
