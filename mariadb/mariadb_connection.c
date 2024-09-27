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
#include <datetime.h>

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
    "status_callback", "tls_version",
    "tls_fp", "tls_fp_list",
    NULL
};

const char *mariadb_default_charset= "utf8mb4";
const char *mariadb_default_collation= "utf8mb4_general_ci";

static void
MrdbConnection_finalize(MrdbConnection *self);

static PyObject *
MrdbConnection_exception(PyObject *self, void *closure);

#define GETTER_EXCEPTION(name, exception, doc)\
{ name,MrdbConnection_exception, NULL, doc, &exception }

static PyObject *
MrdbConnection_getreconnect(MrdbConnection *self, void *closure);

static PyObject *
MrdbConnection_connection_id(MrdbConnection *self);

static int
MrdbConnection_setreconnect(MrdbConnection *self, PyObject *args,
                            void *closure);
static PyObject *
MrdbConnection_escape_string(MrdbConnection *self, PyObject *str);

static PyObject *
MrdbConnection_getinfo(MrdbConnection *self, PyObject *optionval);

static PyObject *
MrdbConnection_dump_debug_info(MrdbConnection *self);

static PyObject *
MrdbConnection_warnings(MrdbConnection *self);

static PyObject *
MrdbConnection_executecommand(MrdbConnection *self,
                             PyObject *command);

static PyObject *
MrdbConnection_readresponse(MrdbConnection *self);

static PyObject
*MrdbConnection_socket(MrdbConnection *self);

static PyGetSetDef
MrdbConnection_sets[]=
{
    {"auto_reconnect", (getter)MrdbConnection_getreconnect,
        (setter)MrdbConnection_setreconnect,
        connection_auto_reconnect__doc__, NULL},
    {"connection_id", (getter)MrdbConnection_connection_id,
        NULL, "Id of current connection", NULL},
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
    GETTER_EXCEPTION("PoolError", Mariadb_PoolError, exception_pool__doc__),
    GETTER_EXCEPTION("DataError", Mariadb_DataError, exception_data__doc__),
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
        METH_O,
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
      METH_O,
      "For internal use only"},
    {"_read_response", (PyCFunction)MrdbConnection_readresponse,
      METH_NOARGS,
      "For internal use only"},
    {"_mariadb_get_info", (PyCFunction)MrdbConnection_getinfo,
      METH_O,
      "For internal use only"},
    {"_get_socket", (PyCFunction)MrdbConnection_socket,
      METH_NOARGS,
      "For internal use only"},
    {NULL} /* always last */
};

static struct
PyMemberDef MrdbConnection_Members[] =
{
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
    {"_converter",
        T_OBJECT,
        offsetof(MrdbConnection, converter),
        0,
        "Conversion dictionary"},
    {"_tls",
        T_BOOL,
        offsetof(MrdbConnection, tls_in_use),
        0,
        "Indicates if connection uses TLS/SSL"},
    {NULL} /* always last */
};

int connection_datetime_init(void)
{
    PyDateTime_IMPORT;

    if (!PyDateTimeAPI) {
        PyErr_SetString(PyExc_ImportError, "DateTimeAPI initialization failed");
        return 1;
    }
    return 0;
}


#if MARIADB_PACKAGE_VERSION_ID > 30301
void MrdbConnection_process_status_info(void *data, enum enum_mariadb_status_info type, ...)
{
  va_list ap;
  PyThreadState *_save= NULL;
  MrdbConnection *self= (MrdbConnection *)data;
  PyObject *dict= NULL;
  PyObject *dict_key= NULL, *dict_val= NULL;
  va_start(ap, type);

  if (self->status_callback) {
    if (type == STATUS_TYPE)
    {
      unsigned int server_status= va_arg(ap, int);
      
      MARIADB_UNBLOCK_THREADS(self);
      dict_key= PyUnicode_FromString("server_status");
      dict_val= PyLong_FromLong(server_status);
      dict= PyDict_New();
      PyDict_SetItem(dict, dict_key, dict_val);
      Py_DECREF(dict_key);
      Py_DECREF(dict_val);
      PyObject_CallFunction(self->status_callback, "OO", (PyObject *)data, dict);
      MARIADB_BLOCK_THREADS(self);
    }
  }
  if (type == SESSION_TRACK_TYPE)
  {
    enum enum_session_state_type track_type= va_arg(ap, enum enum_session_state_type);

    MARIADB_UNBLOCK_THREADS(self);

    if (self->status_callback) {
      switch (track_type) {
        case SESSION_TRACK_SCHEMA:
          dict_key= PyUnicode_FromString("schema");
          break;
        case SESSION_TRACK_STATE_CHANGE:
          dict_key= PyUnicode_FromString("state_change");
          break;
        default:
          break;
      }
    }

    if (dict_key)
    {
      MARIADB_CONST_STRING *val= va_arg(ap, MARIADB_CONST_STRING *);
      dict_val= PyUnicode_FromStringAndSize(val->str, val->length);
      dict= PyDict_New();
      PyDict_SetItem(dict, dict_key, dict_val);
      Py_DECREF(dict_key);
      Py_DECREF(dict_val);
      PyObject_CallFunction(self->status_callback, "OO", (PyObject *)data, dict);
    }

    if (track_type == SESSION_TRACK_SYSTEM_VARIABLES)
    {
      MARIADB_CONST_STRING *key= va_arg(ap, MARIADB_CONST_STRING *);
      MARIADB_CONST_STRING *val= va_arg(ap, MARIADB_CONST_STRING *);

      if (!strncmp(key->str, "character_set_client", key->length) &&
           strncmp(val->str, "utf8mb4", val->length))
      {
        /* mariadb_throw_exception (PyUnicode_FormatV)
           doesn't support string with length,
           so we need a temporary variable */
        char charset[128];

        memcpy(charset, val->str, val->length);
        charset[val->length]= 0;
        va_end(ap);
        mariadb_throw_exception(NULL, Mariadb_ProgrammingError, 1,
                "Character set '%s' is not supported", charset);
      }
      if (self->status_callback)
      {
        dict_key= PyUnicode_FromStringAndSize(key->str, key->length);
        dict_val= PyUnicode_FromStringAndSize(val->str, val->length);
        dict= PyDict_New();
        PyDict_SetItem(dict, dict_key, dict_val);
        Py_DECREF(dict_key);
        Py_DECREF(dict_val);
        PyObject_CallFunction(self->status_callback, "OO", (PyObject *)data, dict);
      }
    }
    MARIADB_BLOCK_THREADS(self);
  }
  va_end(ap);
} 
#endif

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
         *plugin_dir= NULL, *tls_version= NULL, *tls_fp= NULL, *tls_fp_list= NULL;
    char *pool_name= 0;
    uint32_t pool_size= 0;
    uint8_t ssl_enforce= 0;
    uint8_t reset_session= 1;
    unsigned int client_flags= 0, port= 0;
    unsigned int local_infile= 0xFF;
    unsigned int connect_timeout=0, read_timeout=0, write_timeout=0,
                 compress= 0, ssl_verify_cert= 0;
    PyObject *status_callback= NULL;

    if (!PyArg_ParseTupleAndKeywords(args, dsnargs,
                "|zzzzziziiibbzzzzzzzzzzibizibzzzzOzzz:connect",
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
                &user, &schema, &password, &status_callback,
                &tls_version, &tls_fp, &tls_fp_list))
    {
        return -1;
    }

    if (dsn)
    {
        mariadb_throw_exception(NULL, Mariadb_ProgrammingError, 1,
                "dsn keyword is not supported");
        return -1;
    }

#if MARIADB_PACKAGE_VERSION_ID < 30302
    if (status_callback)
      {
        /* status callback requires C/C 3.3.2 */
        PyErr_WarnFormat(PyExc_RuntimeWarning, 1, "status_callback support requires MariaDB Connector/C >= 3.3.2 "\
                                                  "(found version %s)", mysql_get_client_info());
    }
#else
    self->status_callback= status_callback;
#endif

    if (!(self->mysql= mysql_init(NULL)))
    {
        mariadb_throw_exception(self->mysql, Mariadb_OperationalError, 1,
            "Can't allocate memory for connection");
        return -1;
    }

#if MARIADB_PACKAGE_VERSION_ID > 30301
   if (mysql_optionsv(self->mysql, MARIADB_OPT_STATUS_CALLBACK, MrdbConnection_process_status_info, self))
   {
     /* Generate a warning, not an error - this will allow to run the module if Connector/C installation
        was overwritten */
      PyErr_WarnFormat(PyExc_RuntimeWarning, 1, "MariaDB Connector/Python was build with MariaDB Connector/C version %s "\
                                             "but loaded Connector/C library has version %s", MARIADB_PACKAGE_VERSION,
                                             mysql_get_client_info());
   }
#endif

    MARIADB_BEGIN_ALLOW_THREADS(self);

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
    if (ssl_enforce || ssl_key || ssl_ca || ssl_cert || ssl_capath || ssl_cipher || tls_version ||
        tls_fp || tls_fp_list)
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
    if (mysql_options(self->mysql, MYSQL_OPT_SSL_VERIFY_SERVER_CERT, (unsigned char *) &ssl_verify_cert))
        goto end;
    if (tls_version)
    {
        if (mysql_options(self->mysql, MARIADB_OPT_TLS_VERSION, tls_version))
          goto end;
    }
    if (tls_fp)
    {
        if (mysql_options(self->mysql, MARIADB_OPT_SSL_FP, tls_fp))
          goto end;
    }
    if (tls_fp_list)
    {
        if (mysql_options(self->mysql, MARIADB_OPT_SSL_FP_LIST, tls_fp_list))
          goto end;
    }

    mysql_real_connect(self->mysql, host, user, password, schema, port,
            socket, client_flags);
   
    if (mysql_errno(self->mysql))
    {
        goto end;
    }

    if (mysql_get_ssl_cipher(self->mysql))
        self->tls_in_use= 1;

    mariadb_get_infov(self->mysql, MARIADB_CONNECTION_HOST, (void *)&self->host);

    has_error= 0;
end:
    MARIADB_END_ALLOW_THREADS(self);

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
    .tp_name = "mariadb.connection",
    .tp_basicsize = (Py_ssize_t)sizeof(MrdbConnection),
    .tp_repr = (reprfunc)MrdbConnection_repr,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_HAVE_GC | Py_TPFLAGS_BASETYPE,
    .tp_doc = connection__doc__,
    .tp_new = PyType_GenericNew,
    .tp_traverse = (traverseproc)MrdbConnection_traverse,
    .tp_methods = (struct PyMethodDef *)MrdbConnection_Methods,
    .tp_members = (struct PyMemberDef *)MrdbConnection_Members,
    .tp_getset = MrdbConnection_sets,
    .tp_init = (initproc)MrdbConnection_Initialize,
    .tp_alloc = PyType_GenericAlloc,
    .tp_finalize = (destructor)MrdbConnection_finalize
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

static
void MrdbConnection_finalize(MrdbConnection *self)
{
    if (self)
    {
        if (self->mysql)
        {
            MARIADB_BEGIN_ALLOW_THREADS(self)
            mysql_close(self->mysql);
            MARIADB_END_ALLOW_THREADS(self)
            self->mysql= NULL;
        }
    }
}

static PyObject *
MrdbConnection_executecommand(MrdbConnection *self,
                             PyObject *command)
{
  const char *cmd;
  int rc;

  MARIADB_CHECK_CONNECTION(self, NULL);

  cmd= PyUnicode_AsUTF8AndSize(command, NULL);

  MARIADB_BEGIN_ALLOW_THREADS(self);
  rc= mysql_send_query(self->mysql, cmd, (long)strlen(cmd));
  MARIADB_END_ALLOW_THREADS(self);

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

    MARIADB_BEGIN_ALLOW_THREADS(self)
    mysql_close(self->mysql);
    MARIADB_END_ALLOW_THREADS(self)
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

    MARIADB_BEGIN_ALLOW_THREADS(self);
    rc= mysql_ping(self->mysql);
    MARIADB_END_ALLOW_THREADS(self);

    if (rc) {
        mariadb_throw_exception(self->mysql, Mariadb_InterfaceError, 0, NULL);
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

    if (!PyArg_ParseTuple(args, "szz", &user, &password, &database))
        return NULL;

    MARIADB_BEGIN_ALLOW_THREADS(self);
    rc= mysql_change_user(self->mysql, user, password, database);
    MARIADB_END_ALLOW_THREADS(self);

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
MrdbConnection_X509info(MARIADB_X509_INFO *info)
{
  PyObject *dict, *key, *val;
  struct tm *tmp;
  if (!info)
    Py_RETURN_NONE;

  dict= PyDict_New();

  key= PyUnicode_FromString("version");
  val= PyLong_FromLong((long)info->version);
  PyDict_SetItem(dict, key, val);
  Py_DECREF(key);
  Py_DECREF(val);

  key= PyUnicode_FromString("subject");
  val= PyUnicode_FromString(info->subject);
  PyDict_SetItem(dict, key, val);
  Py_DECREF(key);
  Py_DECREF(val);

  key= PyUnicode_FromString("issuer");
  val= PyUnicode_FromString(info->issuer);
  PyDict_SetItem(dict, key, val);
  Py_DECREF(key);
  Py_DECREF(val);

  key= PyUnicode_FromString("fingerprint");
  val= PyUnicode_FromString(info->fingerprint);
  PyDict_SetItem(dict, key, val);
  Py_DECREF(key);
  Py_DECREF(val);

  tmp= &info->not_before;
  key= PyUnicode_FromString("not_before");
  val= PyDateTime_FromDateAndTime(tmp->tm_year + 1900, tmp->tm_mon + 1, tmp->tm_mday,
                                  tmp->tm_hour, tmp->tm_min, tmp->tm_sec, 0);
  PyDict_SetItem(dict, key, val);
  Py_DECREF(key);
  Py_DECREF(val);

  tmp= &info->not_after;
  key= PyUnicode_FromString("not_after");
  val= PyDateTime_FromDateAndTime(tmp->tm_year + 1900, tmp->tm_mon + 1, tmp->tm_mday,
                                  tmp->tm_hour, tmp->tm_min, tmp->tm_sec, 0);
  PyDict_SetItem(dict, key, val);
  Py_DECREF(key);
  Py_DECREF(val);

  return dict;
}

static PyObject *
MrdbConnection_getinfo(MrdbConnection *self, PyObject *optionval)
{
    union {
        char *str;
        uint64_t num;
        uint8_t b;
        void *ptr;
    } val;

    uint32_t option;

    if (!optionval || !CHECK_TYPE_NO_NONE(optionval, &PyLong_Type)) {
        PyErr_SetString(PyExc_TypeError, "Parameter must be an integer value");
        return NULL;
    }

    option= (uint32_t)PyLong_AsUnsignedLong(optionval);

    memset(&val, 0, sizeof(val));

    if (mariadb_get_infov(self->mysql, option, &val))
    {
        mariadb_throw_exception(NULL, Mariadb_ProgrammingError, 1,
                                "Parameter option not supported");
        return NULL;
    }

    switch (option) {
      case PYMARIADB_CONNECTION_UNIX_SOCKET:
      case PYMARIADB_CONNECTION_USER:
      case PYMARIADB_CHARSET_NAME:
      case PYMARIADB_TLS_LIBRARY:
      case PYMARIADB_CLIENT_VERSION:
      case PYMARIADB_CONNECTION_HOST:
      case PYMARIADB_CONNECTION_INFO:
      case PYMARIADB_CONNECTION_SCHEMA:
      case PYMARIADB_CONNECTION_SQLSTATE:
      case PYMARIADB_CONNECTION_SOCKET:
      case PYMARIADB_CONNECTION_SSL_CIPHER:
      case PYMARIADB_CONNECTION_TLS_VERSION:
      case PYMARIADB_CONNECTION_SERVER_VERSION:
        return PyUnicode_FromString(val.str ? val.str : "");
        break;

      case PYMARIADB_CHARSET_ID:
      case PYMARIADB_CLIENT_VERSION_ID:
      case PYMARIADB_CONNECTION_ASYNC_TIMEOUT:
      case PYMARIADB_CONNECTION_ASYNC_TIMEOUT_MS:
      case PYMARIADB_CONNECTION_PORT:
      case PYMARIADB_CONNECTION_PROTOCOL_VERSION_ID:
      case PYMARIADB_CONNECTION_SERVER_TYPE:
      case PYMARIADB_CONNECTION_SERVER_VERSION_ID:
      case PYMARIADB_CONNECTION_TLS_VERSION_ID:
      case PYMARIADB_MAX_ALLOWED_PACKET:
      case PYMARIADB_NET_BUFFER_LENGTH:
      case PYMARIADB_CONNECTION_SERVER_STATUS:
      case PYMARIADB_CONNECTION_SERVER_CAPABILITIES:
      case PYMARIADB_CONNECTION_EXTENDED_SERVER_CAPABILITIES:
      case PYMARIADB_CONNECTION_CLIENT_CAPABILITIES:
      case PYMARIADB_CONNECTION_BYTES_READ:
      case PYMARIADB_CONNECTION_BYTES_SENT:
      case PYMARIADB_TLS_VERIFY_STATUS:
        return PyLong_FromLong((long)val.num);
        break;
      case PYMARIADB_TLS_PEER_CERT_INFO:
      {
        MARIADB_X509_INFO *info;

        if (!self->tls_in_use)
          Py_RETURN_NONE;

        mariadb_get_infov(self->mysql, option, &info, 256);
        return MrdbConnection_X509info(info);
        break;
      }
      default:
        Py_RETURN_NONE;
    }
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

    MARIADB_BEGIN_ALLOW_THREADS(self);
    rc= mariadb_reconnect(self->mysql);
    MARIADB_END_ALLOW_THREADS(self);

    if (!save_reconnect)
        mysql_optionsv(self->mysql, MYSQL_OPT_RECONNECT, &save_reconnect);

    if (rc)
    {
        mariadb_throw_exception(self->mysql, NULL, 0, NULL);
        return NULL;
    }
    /* get capabilities */
    Py_RETURN_NONE;
}
/* }}} */

/* {{{ MrdbConnection_reset */
PyObject *MrdbConnection_reset(MrdbConnection *self)
{
    int rc;
    MARIADB_CHECK_CONNECTION(self, NULL);

    MARIADB_BEGIN_ALLOW_THREADS(self);
    rc= mysql_reset_connection(self->mysql);
    MARIADB_END_ALLOW_THREADS(self);

    if (rc)
    {
        mariadb_throw_exception(self->mysql, NULL, 0, NULL);
        return NULL;
    }
    Py_RETURN_NONE;
}
/* }}} */

/* {{{ MrdbConnection_connection_id */
static PyObject *MrdbConnection_connection_id(MrdbConnection *self)
{
    MARIADB_CHECK_CONNECTION(self, NULL);

    return PyLong_FromUnsignedLong(mysql_thread_id(self->mysql));
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
        PyObject *str)
{
    PyObject *new_string= NULL;
    size_t from_length, to_length;
    char *from, *to;

    /* escaping depends on the server status, so we need a valid
       connection */
    MARIADB_CHECK_CONNECTION(self, NULL);

    if (!CHECK_TYPE_NO_NONE(str, &PyUnicode_Type)) {
        PyErr_SetString(PyExc_TypeError, "Parameter must be a string");
        return NULL;
    }

    from= (char *)PyUnicode_AsUTF8AndSize(str, (Py_ssize_t *)&from_length);
    if (!(to= (char *)PyMem_Calloc(1, from_length * 2 + 1)))
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

    MARIADB_BEGIN_ALLOW_THREADS(self);
    rc= mysql_dump_debug_info(self->mysql);
    MARIADB_END_ALLOW_THREADS(self);

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

    MARIADB_BEGIN_ALLOW_THREADS(self);
    rc= self->mysql->methods->db_read_query_result(self->mysql);
    MARIADB_END_ALLOW_THREADS(self);

    if (rc)
    {
        mariadb_throw_exception(self->mysql, NULL, 0, NULL);
        return NULL;
    }
    Py_RETURN_NONE;
}

static PyObject *MrdbConnection_socket(MrdbConnection *self)
{
    MARIADB_CHECK_CONNECTION(self, NULL);

    return PyLong_FromLong((unsigned long)mysql_get_socket(self->mysql));
}

/* vim: set tabstop=4 */
/* vim: set shiftwidth=4 */
/* vim: set expandtab */
/* vim: set foldmethod=indent */
/* vim: set foldnestmax=10 */
/* vim: set nofoldenable */
/* vim: set foldlevel=2 */
