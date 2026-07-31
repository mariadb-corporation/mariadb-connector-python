//  SPDX-License-Identifier: LGPL-2.1-or-later
//  Copyright (c) 2020-2025 MariaDB Corporation Ab

#include "mariadb_python.h"
#include "docs/connection.h"
#include "docs/exception.h"
#include <datetime.h>
#ifndef _WIN32
#include <poll.h>
#include <fcntl.h>
#endif

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
    "client_flag", "plugin_dir",
    "username", "db", "passwd",
    "status_callback", "tls_version",
    "tls_fp", "tls_fp_list", "protocol",
    "max_allowed_columns",
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

static PyObject
*MrdbConnection_socket(MrdbConnection *self);

/* Non-blocking API forward declarations */
static PyObject *
MrdbConnection_set_nonblock_option(MrdbConnection *self, PyObject *args);

static PyObject *
MrdbConnection_get_timeout_value(MrdbConnection *self, PyObject *args);

/* Sync methods */
PyObject *MrdbConnection_sync_ping(MrdbConnection *self);

/* Async methods and helpers are now defined at the end of this file */
static PyObject *MrdbConnection_init_fields_only(MrdbConnection *self);
static PyObject *MrdbConnection_async_real_query_start(MrdbConnection *self, PyObject *args);
static PyObject *MrdbConnection_async_real_query_cont(MrdbConnection *self, PyObject *args);
static PyObject *MrdbConnection_async_ping_start(MrdbConnection *self);
static PyObject *MrdbConnection_async_ping_cont(MrdbConnection *self, PyObject *args);
static PyObject *MrdbConnection_async_close_start(MrdbConnection *self);
static PyObject *MrdbConnection_async_close_cont(MrdbConnection *self, PyObject *args);
static PyObject *MrdbConnection_async_change_user_start(MrdbConnection *self, PyObject *args);
static PyObject *MrdbConnection_async_change_user_cont(MrdbConnection *self, PyObject *args);
static PyObject *MrdbConnection_async_reset_start(MrdbConnection *self);
static PyObject *MrdbConnection_async_reset_cont(MrdbConnection *self, PyObject *args);
static PyObject *MrdbConnection_async_dump_debug_info_start(MrdbConnection *self);
static PyObject *MrdbConnection_async_dump_debug_info_cont(MrdbConnection *self, PyObject *args);
static PyObject *MrdbConnection_check_socket_ready(MrdbConnection *self, PyObject *args);
static PyObject *MrdbConnection_close_stmt_capsule(MrdbConnection *self, PyObject *capsule);
static PyObject *MrdbConnection_neutralize_stmt_capsule(MrdbConnection *self, PyObject *capsule);

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
    { "_sync_ping",
        (PyCFunction)MrdbConnection_sync_ping,
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
    {"_mariadb_get_info", (PyCFunction)MrdbConnection_getinfo,
      METH_O,
      "For internal use only"},
    {"_get_socket", (PyCFunction)MrdbConnection_socket,
      METH_NOARGS,
      "For internal use only"},
    /* Non-blocking API methods for async support */
    {"_init_fields_only", (PyCFunction)MrdbConnection_init_fields_only,
      METH_NOARGS,
      "Initialize C struct fields without connecting (for async)"},
    {"set_nonblock_option", (PyCFunction)MrdbConnection_set_nonblock_option,
      METH_NOARGS,
      "Enable non-blocking mode"},
    {"get_socket", (PyCFunction)MrdbConnection_socket,
      METH_NOARGS,
      "Get socket file descriptor"},
    {"get_timeout_value", (PyCFunction)MrdbConnection_get_timeout_value,
      METH_NOARGS,
      "Get timeout value in seconds"},
    {"_async_real_query_start", (PyCFunction)MrdbConnection_async_real_query_start,
      METH_VARARGS,
      "Start non-blocking query"},
    {"_async_real_query_cont", (PyCFunction)MrdbConnection_async_real_query_cont,
      METH_VARARGS,
      "Continue non-blocking query"},
    {"_async_ping_start", (PyCFunction)MrdbConnection_async_ping_start,
      METH_NOARGS,
      "Start non-blocking ping"},
    {"_async_ping_cont", (PyCFunction)MrdbConnection_async_ping_cont,
      METH_VARARGS,
      "Continue non-blocking ping"},
    {"_async_close_start", (PyCFunction)MrdbConnection_async_close_start,
      METH_NOARGS,
      "Start non-blocking close"},
    {"_async_close_cont", (PyCFunction)MrdbConnection_async_close_cont,
      METH_VARARGS,
      "Continue non-blocking close"},
    {"_async_change_user_start", (PyCFunction)MrdbConnection_async_change_user_start,
      METH_VARARGS,
      "Start non-blocking change_user"},
    {"_async_change_user_cont", (PyCFunction)MrdbConnection_async_change_user_cont,
      METH_VARARGS,
      "Continue non-blocking change_user"},
    {"_async_reset_start", (PyCFunction)MrdbConnection_async_reset_start,
      METH_NOARGS,
      "Start non-blocking reset"},
    {"_async_reset_cont", (PyCFunction)MrdbConnection_async_reset_cont,
      METH_VARARGS,
      "Continue non-blocking reset"},
    {"_async_dump_debug_info_start", (PyCFunction)MrdbConnection_async_dump_debug_info_start,
      METH_NOARGS,
      "Start non-blocking dump_debug_info"},
    {"_async_dump_debug_info_cont", (PyCFunction)MrdbConnection_async_dump_debug_info_cont,
      METH_VARARGS,
      "Continue non-blocking dump_debug_info"},
    {"_check_socket_ready", (PyCFunction)MrdbConnection_check_socket_ready,
      METH_VARARGS,
      "Check if socket is ready for I/O (non-blocking)"},
    {"_close_stmt_capsule",
        (PyCFunction)MrdbConnection_close_stmt_capsule,
        METH_O,
        "Close a MYSQL_STMT wrapped in a PyCapsule (for cache eviction)"},
    {"_neutralize_stmt_capsule",
        (PyCFunction)MrdbConnection_neutralize_stmt_capsule,
        METH_O,
        "Disarm a PyCapsule destructor without sending COM_STMT_CLOSE"},
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
  MrdbConnection *self= (MrdbConnection *)data;
  PyObject *dict= NULL;
  PyObject *dict_key= NULL, *dict_val= NULL;

  PyGILState_STATE gstate;
  /* Acquire the GIL */
  gstate = PyGILState_Ensure();

  va_start(ap, type);
  if (self->status_callback) {
    if (type == STATUS_TYPE)
    {
      unsigned int server_status= va_arg(ap, int);

      dict_key= PyUnicode_FromString("server_status");
      dict_val= PyLong_FromLong(server_status);
      dict= PyDict_New();
      PyDict_SetItem(dict, dict_key, dict_val);
      Py_DECREF(dict_key);
      Py_DECREF(dict_val);
      PyObject *res= PyObject_CallFunction(self->status_callback, "OO", (PyObject *)data, dict);
      Py_XDECREF(res);
      Py_DECREF(dict);
      dict= NULL;
    }
  }
  if (type == SESSION_TRACK_TYPE)
  {
    enum enum_session_state_type track_type= va_arg(ap, enum enum_session_state_type);


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
      dict_key= NULL;
      Py_DECREF(dict_val);
      PyObject *res= PyObject_CallFunction(self->status_callback, "OO", (PyObject *)data, dict);
      Py_XDECREF(res);
      Py_DECREF(dict);
      dict= NULL;
    }

    if (track_type == SESSION_TRACK_SYSTEM_VARIABLES)
    {
      MARIADB_CONST_STRING *key= va_arg(ap, MARIADB_CONST_STRING *);
      MARIADB_CONST_STRING *val= va_arg(ap, MARIADB_CONST_STRING *);

      if (key->length == strlen("character_set_client") &&
          !strncmp(key->str, "character_set_client", key->length) &&
          (val->length != strlen("utf8mb4") ||
           strncmp(val->str, "utf8mb4", val->length)))
      {
        /* mariadb_throw_exception (PyUnicode_FormatV)
           doesn't support string with length,
           so we need a temporary variable */
        char charset[128];
        size_t copy_len= val->length < sizeof(charset) ?
                         val->length : sizeof(charset) - 1;

        memcpy(charset, val->str, copy_len);
        charset[copy_len]= 0;
        mariadb_throw_exception(NULL, Mariadb_ProgrammingError, 1,
                "Character set '%s' is not supported", charset);
        goto end;
      }
      if (self->status_callback)
      {
        dict_key= PyUnicode_FromStringAndSize(key->str, key->length);
        dict_val= PyUnicode_FromStringAndSize(val->str, val->length);
        dict= PyDict_New();
        PyDict_SetItem(dict, dict_key, dict_val);
        Py_DECREF(dict_key);
        Py_DECREF(dict_val);
        PyObject *res= PyObject_CallFunction(self->status_callback, "OO", (PyObject *)data, dict);
        Py_XDECREF(res);
        Py_DECREF(dict);
        dict= NULL;
      }
    }
  }
end:
  va_end(ap);
  /* Release the GIL */
  PyGILState_Release(gstate);
}
#endif

static int
MrdbConnection_init_fields(MrdbConnection *self)
{
    /* Initialize all fields to NULL/0 */
    self->mysql = NULL;
    self->open = 0;
    self->is_buffered = 0;
    self->is_closed = 0;
    self->tpc_state = 0;
    memset(self->xid, 0, sizeof(self->xid));
    self->dsn = NULL;
    self->host = NULL;
    self->inuse = 0;
    self->status = 0;
    self->asynchronous = 0;
    memset(&self->last_used, 0, sizeof(self->last_used));
    self->server_info = NULL;
    self->closed = 0;
#if MARIADB_PACKAGE_VERSION_ID > 30301
    self->status_callback = NULL;
#endif
    self->last_executed_stmt = NULL;
    self->converter = NULL;
    self->tls_in_use = 0;
    self->active_result_cursor = NULL;
    return 0;
}

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
    /* Secure by default */
    uint8_t ssl_enforce= 1;
    unsigned int client_flags= 0, port= 0, protocol= 0;
    unsigned int local_infile= 0xFF;
    unsigned int connect_timeout=10, read_timeout=0, write_timeout=0,
                 compress= 0, ssl_verify_cert= 1;
    /* keep in sync with Configuration.max_allowed_columns (pure Python) */
    int max_allowed_columns= 65535;
    PyObject *status_callback= NULL;

    /* Initialize all fields first */
    MrdbConnection_init_fields(self);

    if (!PyArg_ParseTupleAndKeywords(args, dsnargs,
                "|zzzzziziiibbzzzzzzzzzzibizzzzOzzzii:connect",
                dsn_keys,
                &dsn, &host, &user, &password, &schema, &port, &socket,
                &connect_timeout, &read_timeout, &write_timeout,
                &local_infile, &compress, &init_command,
                &default_file, &default_group,
                &ssl_key, &ssl_ca, &ssl_cert, &ssl_crl,
                &ssl_cipher, &ssl_capath, &ssl_crlpath,
                &ssl_verify_cert, &ssl_enforce,
                &client_flags, &plugin_dir,
                &user, &schema, &password, &status_callback,
                &tls_version, &tls_fp, &tls_fp_list, &protocol,
                &max_allowed_columns))
    {
        return -1;
    }

    if (dsn)
    {
        mariadb_throw_exception(NULL, Mariadb_ProgrammingError, 1,
                "dsn keyword is not supported");
        return -1;
    }

    if (max_allowed_columns < 1)
    {
        mariadb_throw_exception(NULL, Mariadb_ProgrammingError, 1,
                "Invalid value for max_allowed_columns: %d "
                "(must be greater than 0)", max_allowed_columns);
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
    /* Store status_callback reference and increment refcount */
    Py_XINCREF(status_callback);
    self->status_callback = status_callback;
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

    if (protocol)
    {
        if (mysql_options(self->mysql, MYSQL_OPT_PROTOCOL, &protocol))
          goto end;
    }

    /* Bound the column count a server may announce for a result set, so a
       malicious proxy can't make libmariadb allocate the metadata of an
       arbitrary number of columns (CONPY-377). */
/* MARIADB_OPT_MAX_COLUMNS was added in C/C 3.3.20 and 3.4.10 */
#if MARIADB_PACKAGE_VERSION_ID >= 30410 || \
    (MARIADB_PACKAGE_VERSION_ID >= 30320 && MARIADB_PACKAGE_VERSION_ID < 30400)
    {
        unsigned int max_columns= (unsigned int)max_allowed_columns;
        if (mysql_optionsv(self->mysql, MARIADB_OPT_MAX_COLUMNS, &max_columns))
          goto end;
    }
#endif

    /* set TLS/SSL options */
    if (ssl_enforce || ssl_key || ssl_ca || ssl_cert || ssl_capath || ssl_cipher || tls_version ||
        tls_fp || tls_fp_list)
        mysql_ssl_set(self->mysql, (const char *)ssl_key,
                (const char *)ssl_cert,
                (const char *)ssl_ca,
                (const char *)ssl_capath,
                (const char *)ssl_cipher);
    else
        /* No TLS option given. libmariadb is secure-by-default (it would still
           negotiate and verify TLS), so when the caller explicitly opted out with
           ssl=False we disable verification below to keep the connection in clear. */
        ssl_verify_cert= 0;
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

    Py_BEGIN_ALLOW_THREADS;
    mysql_real_connect(self->mysql, host, user, password, schema, port,
            socket, client_flags);
    Py_END_ALLOW_THREADS;

    if (mysql_errno(self->mysql))
    {
        goto end;
    }

    if (mysql_get_ssl_cipher(self->mysql))
        self->tls_in_use= 1;

    /* PEP-446-style hygiene: mark the socket non-inheritable so an
       execve() in a child process won't leak our fd.  This does NOT
       protect against fork() without exec — that case is documented
       as unsupported (open a fresh connection in the child). */
    {
        my_socket _fd = mysql_get_socket(self->mysql);
#ifdef _WIN32
        if (_fd != INVALID_SOCKET)
            SetHandleInformation((HANDLE)_fd, HANDLE_FLAG_INHERIT, 0);
#else
        if (_fd >= 0) {
            int _flags = fcntl((int)_fd, F_GETFD, 0);
            if (_flags != -1)
                fcntl((int)_fd, F_SETFD, _flags | FD_CLOEXEC);
        }
#endif
    }
    mariadb_get_infov(self->mysql, MARIADB_CONNECTION_HOST, (void *)&self->host);

    has_error= 0;
end:

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
    Py_VISIT(self->last_executed_stmt);
    Py_VISIT(self->converter);
#if MARIADB_PACKAGE_VERSION_ID > 30301
    Py_VISIT(self->status_callback);
#endif
    Py_VISIT(self->dsn);
    /* Note: active_result_cursor is managed entirely by cursor code with its own refcounting */
    /* Don't visit it here to avoid GC interference with cursor's lifecycle management */
    return 0;
}

static int MrdbConnection_tpclear(MrdbConnection *self)
{
    Py_CLEAR(self->last_executed_stmt);
    Py_CLEAR(self->converter);
#if MARIADB_PACKAGE_VERSION_ID > 30301
    Py_CLEAR(self->status_callback);
#endif
    Py_CLEAR(self->dsn);
    /* Note: active_result_cursor is managed by cursor code - don't touch it here */
    return 0;
}

static PyObject *MrdbConnection_repr(MrdbConnection *self)
{
    char cobj_repr[384];

    if (!self->closed)
        snprintf(cobj_repr, 384, "<mariadb_c.connection connected to '%s' at %p>",
                self->host, self);
    else
        snprintf(cobj_repr, 384, "<mariadb_c.connection (closed) at %p>",
                self);
    return PyUnicode_FromString(cobj_repr);
}

void
ma_connection_consume_active_result(MrdbConnection *conn, void *requesting_cursor)
{
    /* If there's an active unbuffered result, clear it before allowing
     * any cursor to execute. This prevents "Commands out of sync" when
     * switching between cursors or re-executing on the same cursor.
     *
     * Note: We clear even if the requesting cursor is the same as the active one,
     * because re-executing a cursor should consume its previous result.
     */

    /* Try to get Python-level active cursor tracking */
    PyObject *active = PyObject_GetAttrString((PyObject *)conn, "_active_streaming_result");
    if (!active) {
        PyErr_Clear();
        active = PyObject_GetAttrString((PyObject *)conn, "_active_async_cursor");
        if (!active)
            PyErr_Clear();
    }

    if (!active || active == Py_None) {
        Py_XDECREF(active);
        return;
    }

    /* Clear the active cursor's result (even if it's the same cursor re-executing) */
    MrdbCursor_clear_result((MrdbCursor *)active);
    Py_DECREF(active);
}

static void ma_connection_close(MrdbConnection *conn)
{
    if (conn)
    {
        if (conn->mysql)
        {
            Py_BEGIN_ALLOW_THREADS
            mysql_close(conn->mysql);
            Py_END_ALLOW_THREADS
            conn->mysql= NULL;
        }
    }
}

static void MrdbConnection_dealloc(PyObject *obj)
{
    MrdbConnection *self = (MrdbConnection *)obj;

    PyObject_GC_UnTrack(self);
    if (self->mysql)
        ma_connection_close(self);

    Py_CLEAR(self->converter);
    Py_CLEAR(self->last_executed_stmt);
#if MARIADB_PACKAGE_VERSION_ID > 30301
    Py_CLEAR(self->status_callback);
#endif
    Py_CLEAR(self->dsn);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

PyTypeObject MrdbConnection_Type = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "mariadb_c.connection",
    .tp_basicsize = (Py_ssize_t)sizeof(MrdbConnection),
    .tp_repr = (reprfunc)MrdbConnection_repr,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_HAVE_GC | Py_TPFLAGS_BASETYPE,
    .tp_doc = connection__doc__,
    .tp_new = PyType_GenericNew,
    .tp_alloc = PyType_GenericAlloc,
    .tp_traverse = (traverseproc)MrdbConnection_traverse,
    .tp_clear = (inquiry)MrdbConnection_tpclear,
    .tp_methods = (struct PyMethodDef *)MrdbConnection_Methods,
    .tp_members = (struct PyMemberDef *)MrdbConnection_Members,
    .tp_getset = MrdbConnection_sets,
    .tp_init = (initproc)MrdbConnection_Initialize,
    .tp_dealloc = MrdbConnection_dealloc,
    .tp_free = PyObject_GC_Del,
    .tp_finalize = (destructor)MrdbConnection_finalize,
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
    PyObject *cache = PyObject_GetAttrString((PyObject *)self, "_stmt_cache");
    if (cache && cache != Py_None)
    {
        PyObject *res = PyObject_CallMethod(cache, "clear", NULL);
        Py_XDECREF(res);
        /* Break the cycle: Connection → _stmt_cache → StmtCache → _connection */
        PyObject_SetAttrString((PyObject *)self, "_stmt_cache", Py_None);
    }
    if (PyErr_Occurred())
        PyErr_Clear();
    Py_XDECREF(cache);

    ma_connection_close(self);
}

PyObject *MrdbConnection_close(MrdbConnection *self)
{
    if (!self->closed)
    {
        ma_connection_close(self);
        self->closed= 1;
    }
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
PyObject *MrdbConnection_sync_ping(MrdbConnection *self)
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

#if MARIADB_PACKAGE_VERSION_ID > 30401
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
#endif

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
      case PYMARIADB_CONNECTION_SERVER_TYPE:
        return PyUnicode_FromString(val.str ? val.str : "");
        break;

      case PYMARIADB_CHARSET_ID:
      case PYMARIADB_CLIENT_VERSION_ID:
      case PYMARIADB_CONNECTION_ASYNC_TIMEOUT:
      case PYMARIADB_CONNECTION_ASYNC_TIMEOUT_MS:
      case PYMARIADB_CONNECTION_PORT:
      case PYMARIADB_CONNECTION_PROTOCOL_VERSION_ID:
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
#if MARIADB_PACKAGE_VERSION_ID > 30401
      case PYMARIADB_TLS_VERIFY_STATUS:
#endif
        return PyLong_FromLong((long)val.num);
        break;
      case PYMARIADB_TLS_PEER_CERT_INFO:
      {
#if MARIADB_PACKAGE_VERSION_ID < 30402
        Py_RETURN_NONE;
#else
        MARIADB_X509_INFO *info;

        if (!self->tls_in_use)
          Py_RETURN_NONE;

        mariadb_get_infov(self->mysql, option, &info, 256);
        return MrdbConnection_X509info(info);
        break;
#endif
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

static PyObject *MrdbConnection_socket(MrdbConnection *self)
{
    MARIADB_CHECK_CONNECTION(self, NULL);

    return PyLong_FromLong((unsigned long)mysql_get_socket(self->mysql));
}

/* ========================================================================
 * Non-Blocking API Functions for Async Support
 * ======================================================================== */

static PyObject *
MrdbConnection_init_fields_only(MrdbConnection *self)
{
    /* Initialize C struct fields without establishing connection.
     * This is used by async connections which need the struct fields
     * (like active_result_cursor) to exist before the actual async
     * connection is established. */
    MrdbConnection_init_fields(self);
    Py_RETURN_NONE;
}

static PyObject *
MrdbConnection_set_nonblock_option(MrdbConnection *self, PyObject *args)
{
    MARIADB_CHECK_CONNECTION(self, NULL);

    if (mysql_optionsv(self->mysql, MYSQL_OPT_NONBLOCK, (void *)0))
    {
        mariadb_throw_exception(self->mysql, NULL, 0, NULL);
        return NULL;
    }

    Py_RETURN_NONE;
}

static PyObject *
MrdbConnection_get_timeout_value(MrdbConnection *self, PyObject *args)
{
    MARIADB_CHECK_CONNECTION(self, NULL);

    unsigned int timeout = mysql_get_timeout_value(self->mysql);
    return PyFloat_FromDouble((double)timeout);
}


/* Async query execution methods */

static PyObject *
MrdbConnection_async_real_query_start(MrdbConnection *self, PyObject *args) {
    char *stmt;
    Py_ssize_t len;
    int rc;

    MARIADB_CHECK_CONNECTION(self, NULL);

    if (!PyArg_ParseTuple(args, "s#", &stmt, &len))
        return NULL;

    MARIADB_ASYNC_OP(self, mysql_real_query_start(&rc, self->mysql, stmt, (unsigned long)len),
                     (rc != 0), NULL, {});
}

static PyObject *
MrdbConnection_async_real_query_cont(MrdbConnection *self, PyObject *args) {
    int wait_status, rc;

    if (!PyArg_ParseTuple(args, "i", &wait_status))
        return NULL;
    MARIADB_ASYNC_OP(self, mysql_real_query_cont(&rc, self->mysql, wait_status), (rc != 0), NULL, {});
}


/* Async ping methods */

static PyObject *
MrdbConnection_async_ping_start(MrdbConnection *self) {
    int rc;

    MARIADB_CHECK_CONNECTION(self, NULL);
    MARIADB_ASYNC_OP(self, mysql_ping_start(&rc, self->mysql), (rc != 0), Mariadb_InterfaceError, {});
}

static PyObject *
MrdbConnection_async_ping_cont(MrdbConnection *self, PyObject *args)
{
    int wait_status, rc;

     /* Parse the wait_status returned from the previous poll */
    if (!PyArg_ParseTuple(args, "i", &wait_status))
        return NULL;

    MARIADB_CHECK_CONNECTION(self, NULL);

    MARIADB_ASYNC_OP(self, mysql_ping_cont(&rc, self->mysql, wait_status),
                     (rc != 0), Mariadb_InterfaceError, {});
}

/* Async close methods */
static PyObject *
MrdbConnection_async_close_start(MrdbConnection *self) {
    if (self->closed || !self->mysql)
        Py_RETURN_NONE;

    MARIADB_ASYNC_OP(self, mysql_close_start(self->mysql), 0, NULL, { self->mysql = NULL; self->closed = 1;});
}

static PyObject *
MrdbConnection_async_close_cont(MrdbConnection *self, PyObject *args) {
    int wait_status;

    if (self->closed || !self->mysql)
      Py_RETURN_NONE;

    if (!PyArg_ParseTuple(args, "i", &wait_status))
        return NULL;

    MARIADB_ASYNC_OP(self, mysql_close_cont(self->mysql, wait_status), 0, NULL, { self->mysql = NULL; self->closed = 1; });
}

/* Async change_user methods */
static PyObject *
MrdbConnection_async_change_user_start(MrdbConnection *self, PyObject *args)
{
    char *user = NULL, *password = NULL, *database = NULL;
    my_bool rc;

    MARIADB_CHECK_CONNECTION(self, NULL);

    if (!PyArg_ParseTuple(args, "zz|z", &user, &password, &database))
        return NULL;

    MARIADB_ASYNC_OP(self, mysql_change_user_start(&rc, self->mysql, user, password, database),
                     rc, Mariadb_OperationalError, {});
}

static PyObject *
MrdbConnection_async_change_user_cont(MrdbConnection *self, PyObject *args)
{
    int wait_status;
    my_bool rc;

    MARIADB_CHECK_CONNECTION(self, NULL);

    if (!PyArg_ParseTuple(args, "i", &wait_status))
        return NULL;

    MARIADB_ASYNC_OP(self, mysql_change_user_cont(&rc, self->mysql, wait_status),
                     rc, Mariadb_OperationalError, {});
}

/* Async reset methods */
static PyObject *
MrdbConnection_async_reset_start(MrdbConnection *self)
{
    int ret;
    MARIADB_CHECK_CONNECTION(self, NULL);

    MARIADB_ASYNC_OP(self, mysql_reset_connection_start(&ret, self->mysql),
                     (ret != 0), Mariadb_OperationalError, {});
}

static PyObject *
MrdbConnection_async_reset_cont(MrdbConnection *self, PyObject *args)
{
    int wait_status, ret;

    MARIADB_CHECK_CONNECTION(self, NULL);

    if (!PyArg_ParseTuple(args, "i", &wait_status))
        return NULL;

    MARIADB_ASYNC_OP(self, mysql_reset_connection_cont(&ret, self->mysql, wait_status),
                     (ret != 0), Mariadb_OperationalError, {});
}

static PyObject *
MrdbConnection_async_dump_debug_info_start(MrdbConnection *self)
{
    int ret;
    MARIADB_CHECK_CONNECTION(self, NULL);

    MARIADB_ASYNC_OP(self, mysql_dump_debug_info_start(&ret, self->mysql),
                     (ret != 0), Mariadb_OperationalError, {});
}

static PyObject *
MrdbConnection_async_dump_debug_info_cont(MrdbConnection *self, PyObject *args)
{
    int wait_status, ret;

    MARIADB_CHECK_CONNECTION(self, NULL);

    if (!PyArg_ParseTuple(args, "i", &wait_status))
        return NULL;

    MARIADB_ASYNC_OP(self, mysql_dump_debug_info_cont(&ret, self->mysql, wait_status),
                     (ret != 0), Mariadb_OperationalError, {});
}

/* Check socket readiness (non-blocking) */

static PyObject *
MrdbConnection_check_socket_ready(MrdbConnection *self, PyObject *args)
{
    int wait_status;
    int ready_status = 0;

    MARIADB_CHECK_CONNECTION(self, NULL);

    if (!PyArg_ParseTuple(args, "i", &wait_status))
        return NULL;

    if (wait_status == 0) {
        return PyLong_FromLong(0);
    }

#ifdef _WIN32
    /* Windows-specific: SCHANNEL requires special handling.
     * If SSL is in use but no buffered data, add a small sleep to prevent busy loop.
     */
    if (self->tls_in_use) {
        struct timeval tv;
        tv.tv_sec = 0;
        tv.tv_usec = 1000;  /* 1ms sleep */

        Py_BEGIN_ALLOW_THREADS;
        select(0, NULL, NULL, NULL, &tv);
        Py_END_ALLOW_THREADS;

        return PyLong_FromLong(wait_status);
    }

    /* Non-SSL Windows: Use select() for socket polling */
    fd_set readfds, writefds, exceptfds;
    struct timeval tv;
    my_socket sock;
    int result;

    sock = mysql_get_socket(self->mysql);

    /* Check if socket is valid */
    if (sock == INVALID_SOCKET || sock < 0) {
        /* Invalid socket - return expected status */
        return PyLong_FromLong(wait_status & MYSQL_WAIT_READ ? MYSQL_WAIT_READ : MYSQL_WAIT_WRITE);
    }

    FD_ZERO(&readfds);
    FD_ZERO(&writefds);
    FD_ZERO(&exceptfds);

    if (wait_status & MYSQL_WAIT_READ)
        FD_SET(sock, &readfds);
    if (wait_status & MYSQL_WAIT_WRITE)
        FD_SET(sock, &writefds);
    FD_SET(sock, &exceptfds);

    tv.tv_sec = 0;
    tv.tv_usec = 0;  /* 0 timeout - just check if ready, don't wait */

    Py_BEGIN_ALLOW_THREADS;
    result = select(0, &readfds, &writefds, &exceptfds, &tv);  /* Windows: first param must be 0 */
    Py_END_ALLOW_THREADS;

    if (result < 0) {
        /* Error - return expected status to let caller handle it */
        return PyLong_FromLong(wait_status & MYSQL_WAIT_READ ? MYSQL_WAIT_READ : MYSQL_WAIT_WRITE);
    }

    if (result == 0) {
        /* Timeout - socket not ready yet */
        return PyLong_FromLong(0);
    }

    /* result > 0: Socket has activity */
    if (FD_ISSET(sock, &exceptfds)) {
        /* Error on socket - return expected status */
        return PyLong_FromLong(wait_status & MYSQL_WAIT_READ ? MYSQL_WAIT_READ : MYSQL_WAIT_WRITE);
    }
    if (FD_ISSET(sock, &readfds))
        ready_status |= MYSQL_WAIT_READ;
    if (FD_ISSET(sock, &writefds))
        ready_status |= MYSQL_WAIT_WRITE;
#else
    /* Unix/Linux: This shouldn't be called, but provide fallback using poll() */
    struct pollfd pfd;
    int result;

    pfd.fd = mysql_get_socket(self->mysql);
    pfd.events = 0;
    pfd.revents = 0;

    if (wait_status & MYSQL_WAIT_READ)
        pfd.events |= POLLIN;
    if (wait_status & MYSQL_WAIT_WRITE)
        pfd.events |= POLLOUT;

    Py_BEGIN_ALLOW_THREADS;
    result = poll(&pfd, 1, 1);  /* 1ms timeout */
    Py_END_ALLOW_THREADS;

    if (result < 0) {
        /* Error */
        return PyLong_FromLong(wait_status & MYSQL_WAIT_READ ? MYSQL_WAIT_READ : MYSQL_WAIT_WRITE);
    }

    if (result == 0) {
        /* Timeout - socket not ready yet */
        return PyLong_FromLong(0);
    }

    /* result > 0: Socket has activity */
    if (pfd.revents & (POLLERR | POLLHUP | POLLNVAL)) {
        /* Error on socket */
        return PyLong_FromLong(wait_status & MYSQL_WAIT_READ ? MYSQL_WAIT_READ : MYSQL_WAIT_WRITE);
    }
    if (pfd.revents & POLLIN)
        ready_status |= MYSQL_WAIT_READ;
    if (pfd.revents & POLLOUT)
        ready_status |= MYSQL_WAIT_WRITE;
#endif

    return PyLong_FromLong(ready_status);
}

/* _close_stmt_capsule(capsule): unwrap MYSQL_STMT* and send COM_STMT_CLOSE.
 * Used by StmtCache eviction and connection.close() cleanup. */
static PyObject *
MrdbConnection_close_stmt_capsule(MrdbConnection *self, PyObject *capsule)
{
    MYSQL_STMT *stmt;

    if (!PyCapsule_CheckExact(capsule)) {
        PyErr_SetString(PyExc_TypeError, "_close_stmt_capsule: expected a PyCapsule");
        return NULL;
    }

    stmt = (MYSQL_STMT *)PyCapsule_GetPointer(capsule, "MYSQL_STMT");
    if (!stmt)
        return NULL;

    /* Neutralise the capsule destructor so it won't double-free */
    PyCapsule_SetDestructor(capsule, NULL);

    if (self->mysql) {
        Py_BEGIN_ALLOW_THREADS;
        mysql_stmt_close(stmt);
        Py_END_ALLOW_THREADS;
    }

    Py_RETURN_NONE;
}

/* _neutralize_stmt_capsule(capsule): free the MYSQL_STMT and disarm the
 * PyCapsule destructor.  Uses mysql_stmt_close (public API) to release
 * libmariadb's internal allocations, list bookkeeping, and the stmt
 * struct itself.  Sends COM_STMT_CLOSE to the server if the connection
 * is still healthy; callers that don't want the wire traffic (e.g.
 * teardown ordering with COM_QUIT immediately after) can ignore that
 * cost — the server will free the stmt at connection close anyway. */
static PyObject *
MrdbConnection_neutralize_stmt_capsule(MrdbConnection *self, PyObject *capsule)
{
    MYSQL_STMT *stmt;

    if (!PyCapsule_CheckExact(capsule)) {
        PyErr_SetString(PyExc_TypeError,
                        "_neutralize_stmt_capsule: expected a PyCapsule");
        return NULL;
    }

    stmt = (MYSQL_STMT *)PyCapsule_GetPointer(capsule, "MYSQL_STMT");
    PyCapsule_SetDestructor(capsule, NULL);

    if (stmt) {
        Py_BEGIN_ALLOW_THREADS;
        mysql_stmt_close(stmt);
        Py_END_ALLOW_THREADS;
    } else {
        PyErr_Clear();
    }

    Py_RETURN_NONE;
}


/* Note: Cursor-level fetch methods (MrdbCursor_fetch_row_start/cont in mariadb_cursor.c)
 * are used by async cursors. They properly use field_fetch_fromtext for type conversion.
 * Connection-level fetch methods are not needed. */
/* vim: set tabstop=4 */
/* vim: set shiftwidth=4 */
/* vim: set expandtab */
/* vim: set foldmethod=indent */
/* vim: set foldnestmax=10 */
/* vim: set nofoldenable */
/* vim: set foldlevel=2 */
