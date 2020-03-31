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

void
MrdbConnection_dealloc(MrdbConnection *self);

extern PyObject *cnx_pool;

static PyObject 
*MrdbConnection_cursor(MrdbConnection *self, PyObject *args, PyObject *kwargs);

static PyObject *
MrdbConnection_enter(MrdbConnection *self, PyObject *args __attribute__((unused)));
static PyObject *
MrdbConnection_exit(MrdbConnection *self, PyObject *args __attribute__((unused)));

static PyObject *
MrdbConnection_exception(PyObject *self, void *closure);

#define GETTER_EXCEPTION(name, exception, doc)\
{ name,MrdbConnection_exception, NULL, doc, &exception }

static PyObject *
MrdbConnection_getid(MrdbConnection *self, void *closure);

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
MrdbConnection_server_version(MrdbConnection *self);

static PyObject *
MrdbConnection_server_info(MrdbConnection *self);

static PyObject *
MrdbConnection_warnings(MrdbConnection *self);

static PyObject *
MrdbConnection_getautocommit(MrdbConnection *self);

static int
MrdbConnection_setautocommit(MrdbConnection *self, PyObject *arg,
                             void *closure);

static PyGetSetDef
MrdbConnection_sets[]=
{
    {"autocommit", (getter)MrdbConnection_getautocommit,
        (setter)MrdbConnection_setautocommit, 
        connection_autocommit__doc__, NULL},
    {"connection_id", (getter)MrdbConnection_getid, NULL,
        connection_connection_id__doc__, NULL},
    {"database", (getter)MrdbConnection_getdb, (setter)MrdbConnection_setdb,
        connection_database__doc__, NULL},
    {"auto_reconnect", (getter)MrdbConnection_getreconnect,
        (setter)MrdbConnection_setreconnect,
        connection_auto_reconnect__doc__, NULL},
    {"user", (getter)MrdbConnection_getuser, NULL, connection_user__doc__, 
        NULL},
    {"warnings", (getter)MrdbConnection_warnings, NULL,
        connection_warnings__doc__, NULL},
    {"server_version", (getter)MrdbConnection_server_version, NULL,
        connection_server_version__doc__, NULL},
    {"server_info", (getter)MrdbConnection_server_info, NULL, 
        connection_server_info__doc__, NULL},
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
    {"commit", (PyCFunction)MrdbConnection_commit,
        METH_NOARGS,
        connection_commit__doc__},
    {"rollback", (PyCFunction)MrdbConnection_rollback,
        METH_NOARGS,
        connection_rollback__doc__},
    {"cursor", (PyCFunction)MrdbConnection_cursor,
        METH_VARARGS | METH_KEYWORDS,
        connection_cursor__doc__},
    /*TPC methods */
    {"tpc_begin",
        (PyCFunction)MrdbConnection_tpc_begin,
        METH_VARARGS,
        connection_tpc_begin__doc__},
    {"tpc_commit",
        (PyCFunction)MrdbConnection_tpc_commit,
        METH_VARARGS,
        connection_tpc_commit__doc__,
    },
    {"tpc_prepare",
        (PyCFunction)MrdbConnection_tpc_prepare,
        METH_NOARGS,
        connection_tpc_prepare__doc__,},
    {"tpc_recover",
        (PyCFunction)MrdbConnection_tpc_recover,
        METH_NOARGS,
        connection_tpc_recover__doc__},
    {"tpc_rollback",
        (PyCFunction)MrdbConnection_tpc_rollback,
        METH_VARARGS,
        connection_tpc_rollback__doc__},
    {"xid",
        (PyCFunction)MrdbConnection_xid,
        METH_VARARGS,
        connection_xid__doc__},
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
    { "kill",
        (PyCFunction)MrdbConnection_kill,
        METH_VARARGS,
        connection_kill__doc__
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
    {"__enter__", (PyCFunction)MrdbConnection_enter,
        METH_NOARGS, connection_enter__doc__},
    {"__exit__", (PyCFunction)MrdbConnection_exit,
        METH_VARARGS, connection_exit__doc__},
    {NULL} /* alwa+ys last */
};

static struct
PyMemberDef MrdbConnection_Members[] =
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

static void
Mrdb_ConnAttrStr(MYSQL *mysql, PyObject **obj, enum mariadb_value attr)
{
    char *val= NULL;

    if (mariadb_get_infov(mysql, attr, &val) || !val)
    {
        return;
    }
    *obj= PyUnicode_FromString(val);
}

void MrdbConnection_SetAttributes(MrdbConnection *self)
{
    MY_CHARSET_INFO cinfo;

    Mrdb_ConnAttrStr(self->mysql, &self->host, MARIADB_CONNECTION_HOST);
    Mrdb_ConnAttrStr(self->mysql, &self->tls_cipher,
                     MARIADB_CONNECTION_SSL_CIPHER);
    Mrdb_ConnAttrStr(self->mysql, &self->tls_version,
                     MARIADB_CONNECTION_TLS_VERSION);
    Mrdb_ConnAttrStr(self->mysql, &self->unix_socket,
                     MARIADB_CONNECTION_UNIX_SOCKET);
    mariadb_get_infov(self->mysql, MARIADB_CONNECTION_PORT, &self->port);
    mariadb_get_infov(self->mysql, MARIADB_CONNECTION_MARIADB_CHARSET_INFO,
                      &cinfo);
    self->charset= PyUnicode_FromString(cinfo.csname);
    self->collation= PyUnicode_FromString(cinfo.name);
}

static int
MrdbConnection_Initialize(MrdbConnection *self,
        PyObject *args,
        PyObject *dsnargs)
{
    int rc;
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

    char *dsn_keys[]= {
        "dsn", "host", "user", "password", "database", "port", "unix_socket",
        "connect_timeout", "read_timeout", "write_timeout",
        "local_infile", "compress", "init_command",
        "default_file", "default_group",
        "ssl_key", "ssl_ca", "ssl_cert", "ssl_crl",
        "ssl_cipher", "ssl_capath", "ssl_crlpath",
        "ssl_verify_cert", "ssl",
        "client_flags", "pool_name", "pool_size", 
        "pool_reset_connection", "plugin_dir",
        NULL
    };


    if (!PyArg_ParseTupleAndKeywords(args, dsnargs,
                "|sssssisiiibbssssssssssipisibs:connect",
                dsn_keys,
                &dsn, &host, &user, &password, &schema, &port, &socket,
                &connect_timeout, &read_timeout, &write_timeout,
                &local_infile, &compress, &init_command,
                &default_file, &default_group,
                &ssl_key, &ssl_ca, &ssl_cert, &ssl_crl,
                &ssl_cipher, &ssl_capath, &ssl_crlpath,
                &ssl_verify_cert, &ssl_enforce,
                &client_flags, &pool_name, &pool_size,
                &reset_session, &plugin_dir))
    {
        return -1;
    }

    if (dsn)
    {
        mariadb_throw_exception(NULL, Mariadb_ProgrammingError, 1,
                "dsn keyword is not supported");
        return -1;
    }

    /* do we need pooling? */
    if (pool_name)
    {
        /* check if pool exists */
        if (PyDict_Contains(cnx_pool, PyUnicode_FromString(pool_name)))
        {
            /* get connection from pool */
        }
    }

    if (!(self->mysql= mysql_init(NULL)))
    {
        mariadb_throw_exception(self->mysql, Mariadb_OperationalError, 1,
            "Can't allocate memory for connection");
        return -1;
    }

    if (local_infile != 0xFF)
    {
        mysql_optionsv(self->mysql, MYSQL_OPT_LOCAL_INFILE, &local_infile);
    }

    if (compress)
    {
        mysql_optionsv(self->mysql, MYSQL_OPT_COMPRESS, 1);
    }

    if (init_command)
    {
        mysql_optionsv(self->mysql, MYSQL_INIT_COMMAND, init_command);
    }

    if (plugin_dir) {
        mysql_optionsv(self->mysql, MYSQL_PLUGIN_DIR, plugin_dir);
    } else {
#if defined(DEFAULT_PLUGINS_SUBDIR)
        mysql_optionsv(self->mysql, MYSQL_PLUGIN_DIR, DEFAULT_PLUGINS_SUBDIR);
#endif
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
    PyObject *pn= NULL,
             *pool= NULL;


    /* if pool name exists, we need to return a connection from pool */
    if ((pn= PyDict_GetItemString(kwargs, "pool_name")))
    {
        if ((pool = PyDict_GetItem(cnx_pool, pn)))
        {
            return MrdbPool_getconnection((MrdbPool *)pool);
        }
        if ((pool = MrdbPool_add(self, args, kwargs)))
        {
            return MrdbPool_getconnection((MrdbPool *)pool);
        }
    }

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
        }
        Py_TYPE(self)->tp_free((PyObject*)self);
    }
}

PyObject *MrdbConnection_close(MrdbConnection *self)
{
    MARIADB_CHECK_CONNECTION(self, NULL);
    /* Todo: check if all the cursor stuff is deleted (when using prepared
       statemnts this should be handled in mysql_close) */

    if (self->pool)
    {
        int rc= 0;
        pthread_mutex_lock(&self->pool->lock);
        if (self->pool->reset_session)
        {
            rc= mysql_reset_connection(self->mysql);
        }
        if (!rc)
        {
            self->inuse= 0;
            clock_gettime(CLOCK_MONOTONIC_RAW, &self->last_used);
        }
        pthread_mutex_unlock(&self->pool->lock);
        return Py_None;
    }

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

PyObject *
MrdbConnection_commit(MrdbConnection *self)
{
    int rc= 0;
    MARIADB_CHECK_CONNECTION(self, NULL);

    if (self->tpc_state != TPC_STATE_NONE)
    {
        mariadb_throw_exception(self->mysql, Mariadb_ProgrammingError,
                0, "rollback() is not allowed if a TPC transaction is active");
        return NULL;
    }
    Py_BEGIN_ALLOW_THREADS;
    rc= mysql_commit(self->mysql);
    Py_END_ALLOW_THREADS;
    if (rc)
    {
        mariadb_throw_exception(self->mysql, NULL, 0, NULL);
        return NULL;
    }
    Py_RETURN_NONE;
}

PyObject *
MrdbConnection_rollback(MrdbConnection *self)
{
    int rc= 0;
    MARIADB_CHECK_CONNECTION(self, NULL);

    if (self->tpc_state != TPC_STATE_NONE)
    {
        mariadb_throw_exception(self->mysql, Mariadb_ProgrammingError,
                0, "rollback() is not allowed if a TPC transaction is active");
        return NULL;
    }

    Py_BEGIN_ALLOW_THREADS;
    rc= mysql_rollback(self->mysql);
    Py_END_ALLOW_THREADS;
    if (rc)
    {
        mariadb_throw_exception(self->mysql, NULL, 0, NULL);
        return NULL;
    }

    Py_RETURN_NONE;
}

PyObject *
Mariadb_DBAPIType_Object(uint32_t type)
{
    PyObject *types= Py_BuildValue("(I)", (uint32_t)type);
    PyObject *number= PyObject_CallObject((PyObject *)&Mariadb_DBAPIType_Type,
            types);
    Py_DECREF(types);
    return number;
}

PyObject *
MrdbConnection_xid(MrdbConnection *self, PyObject *args)
{
    PyObject *xid= NULL;
    int      format_id= 1;
    char     *branch_qualifier= NULL,
             *transaction_id= NULL;

    if (!PyArg_ParseTuple(args, "iss", &format_id,
                &transaction_id,
                &branch_qualifier))
    {
        return NULL;
    }

    if (strlen(transaction_id) > MAX_TPC_XID_SIZE ||
        strlen(branch_qualifier) > MAX_TPC_XID_SIZE)
    {
        mariadb_throw_exception(NULL, Mariadb_ProgrammingError, 0,
                "Maximum length of transaction_id or branch_qualifier exceeded.");
        return NULL;
    }

    if (!format_id)
      format_id= 1;

    if (!(xid= Py_BuildValue("(iss)", format_id,
                    transaction_id,
                    branch_qualifier)))
    {
        return NULL;
    }

    return xid;
}

PyObject *
MrdbConnection_tpc_begin(MrdbConnection *self, PyObject *args)
{
    char *transaction_id= 0;
    char *branch_qualifier= 0;
    int format_id= 1;
    char stmt[192];
    int rc= 0;

    if (!PyArg_ParseTuple(args, "(iss)", &format_id,
                &transaction_id,
                &branch_qualifier))
    {
        return NULL;
    }

    snprintf(stmt, 191, "XA BEGIN '%s', '%s', %d", transaction_id, branch_qualifier, format_id);
    Py_BEGIN_ALLOW_THREADS;
    rc= mysql_query(self->mysql, stmt);
    Py_END_ALLOW_THREADS;

    if (rc)
    {
        mariadb_throw_exception(self->mysql, NULL, 0, NULL);
        return NULL;
    }
    self->tpc_state= TPC_STATE_XID;
    snprintf(self->xid, 149, "'%s', '%s', %d", transaction_id, branch_qualifier, format_id);

    Py_RETURN_NONE;
}

PyObject *
MrdbConnection_tpc_commit(MrdbConnection *self, PyObject *args)
{
    char *transaction_id= 0;
    int format_id=1;
    char *branch_qualifier= 0;
    char stmt[192];

    MARIADB_CHECK_CONNECTION(self, NULL);
    MARIADB_CHECK_TPC(self);

    if (!PyArg_ParseTuple(args, "|(iss)", &format_id,
                &transaction_id,
                &branch_qualifier))
    {
        return NULL;
    }

    if (!args && self->tpc_state != TPC_STATE_PREPARE)
    {
        mariadb_throw_exception(NULL, Mariadb_ProgrammingError, 0,
                "transaction is not in prepared state");
        return NULL;
    }

    Py_BEGIN_ALLOW_THREADS;
    if (self->tpc_state < TPC_STATE_PREPARE)
    {
        if (transaction_id) {
            snprintf(stmt, 191, "XA END '%s', '%s', %d",  
                     transaction_id, branch_qualifier, format_id);
        }
        else {
            snprintf(stmt, 191, "XA END %s", self->xid);
        }
        if (mysql_query(self->mysql, stmt))
        {
            mariadb_throw_exception(self->mysql, NULL, 0, NULL);
            goto end;
        }
    }
    if (transaction_id)
    {
        snprintf(stmt, 191, "XA COMMIT '%s', '%s', %d  %s", 
            transaction_id, branch_qualifier, format_id,
            self->tpc_state < TPC_STATE_PREPARE ? "ONE PHASE" : "");
    }
    else {
        snprintf(stmt, 191, "XA COMMIT %s %s", 
            self->xid, 
            self->tpc_state < TPC_STATE_PREPARE ? "ONE PHASE" : "");
    }
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
    char *transaction_id= 0;
    int format_id=1;
    char *branch_qualifier= 0;
    char stmt[192];
    int rc;

    MARIADB_CHECK_CONNECTION(self, NULL);
    MARIADB_CHECK_TPC(self);

    if (!PyArg_ParseTuple(args, "|(iss)", &format_id,
                &transaction_id,
                &branch_qualifier))
        return NULL;

    if (!args && self->tpc_state != TPC_STATE_PREPARE)
    {
        mariadb_throw_exception(NULL, Mariadb_ProgrammingError, 0,
                "transaction is not in prepared state");
        return NULL;
    }
    if (self->tpc_state < TPC_STATE_PREPARE)
    {
        if (transaction_id)
        {
            snprintf(stmt, 191, "XA END '%s', '%s', %d",
                     transaction_id, branch_qualifier, format_id);
        }
        else {
            snprintf(stmt, 191, "XA END %s", self->xid);
        }
        Py_BEGIN_ALLOW_THREADS;
        rc= mysql_query(self->mysql, stmt);
        Py_END_ALLOW_THREADS;
        if (rc)
        {
            mariadb_throw_exception(self->mysql, NULL, 0, NULL);
            goto end;
        }
    }
    if (transaction_id)
    {
       snprintf(stmt, 191, "XA ROLLBACK '%s', '%s', %d", 
                transaction_id, branch_qualifier, format_id);
    }
    else {
            snprintf(stmt, 191, "XA ROLLBACK %s", self->xid);
    }

    Py_BEGIN_ALLOW_THREADS;
    rc= mysql_query(self->mysql, stmt);
    Py_END_ALLOW_THREADS;

    if (rc)
    {
        mariadb_throw_exception(self->mysql, NULL, 0, NULL);
        goto end;
    }
end:

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
    char stmt[192];
    int rc;

    MARIADB_CHECK_CONNECTION(self, NULL);
    MARIADB_CHECK_TPC(self);

    if (self->tpc_state == TPC_STATE_PREPARE)
    {
        mariadb_throw_exception(NULL, Mariadb_ProgrammingError, 0,
                "transaction is already in prepared state");
        return NULL;
    }
    snprintf(stmt, 191, "XA END %s", self->xid);
    Py_BEGIN_ALLOW_THREADS;
    rc= mysql_query(self->mysql, stmt);
    Py_END_ALLOW_THREADS;

    if (rc)
    {
        mariadb_throw_exception(self->mysql, NULL, 0, NULL);
        goto end;
    }

    snprintf(stmt, 191, "XA PREPARE %s", self->xid);
    Py_BEGIN_ALLOW_THREADS;
    rc= mysql_query(self->mysql, stmt);
    Py_END_ALLOW_THREADS;

    if (rc)
    {
        mariadb_throw_exception(self->mysql, NULL, 0, NULL);
        goto end;
    }
end:
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
    int rc;

    MARIADB_CHECK_CONNECTION(self, NULL);
    MARIADB_CHECK_TPC(self);

    Py_BEGIN_ALLOW_THREADS;
    rc= mysql_query(self->mysql, "XA RECOVER");
    Py_END_ALLOW_THREADS;

    if (rc)
    {
        mariadb_throw_exception(self->mysql, NULL, 0, NULL);
        goto end;
    }

    Py_BEGIN_ALLOW_THREADS;
    result= mysql_store_result(self->mysql);
    Py_END_ALLOW_THREADS;

    if (!result)
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

    Py_BEGIN_ALLOW_THREADS;
    mysql_free_result(result);
    Py_END_ALLOW_THREADS;
end:
    if (PyErr_Occurred())
        return NULL;
    return List;
}
/* }}} */

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

    if (!args || Py_TYPE(args) != &PyBool_Type) {
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

    from= (char *)PyUnicode_AsUTF8AndSize(string, (Py_ssize_t *)&from_length);
    to= (char *)alloca(from_length * 2 + 1);
    to_length= mysql_real_escape_string(self->mysql, to, from, (unsigned long)from_length);
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

/* {{{ MrdbConnection_setautocommit */
static int MrdbConnection_setautocommit(MrdbConnection *self, PyObject *arg,
        void *closure)
{
    int rc= 0;

    MARIADB_CHECK_CONNECTION(self, -1);

    if (!arg || Py_TYPE(arg) != &PyBool_Type)
    {
        PyErr_SetString(PyExc_TypeError, "Argument must be boolean");
        return -1;
    }
    Py_BEGIN_ALLOW_THREADS;
    rc= mysql_autocommit(self->mysql, PyObject_IsTrue(arg));
    Py_END_ALLOW_THREADS;

    if (rc)
    {
        mariadb_throw_exception(self->mysql, NULL, 0, NULL);
        return -1;
    }
    return 0;
}
/* }}} */

/* {{{ MrdbConnection_getautocommit */
static PyObject *MrdbConnection_getautocommit(MrdbConnection *self)
{
    uint32_t server_status;

    MARIADB_CHECK_CONNECTION(self, NULL);

    mariadb_get_infov(self->mysql, MARIADB_CONNECTION_SERVER_STATUS, &server_status);
    if (server_status & SERVER_STATUS_AUTOCOMMIT)
        Py_RETURN_TRUE;
    Py_RETURN_FALSE;
}
/* }}} */

static PyObject *
MrdbConnection_enter(MrdbConnection *self, PyObject *args __attribute__((unused)))
{
    Py_INCREF(self);
    return (PyObject *)self;
}

static PyObject *
MrdbConnection_exit(MrdbConnection *self, PyObject *args __attribute__((unused)))
{
    PyObject *rc= NULL,
             *tmp= NULL;

    if ((tmp= PyObject_CallMethod((PyObject *)self, "close", "")))
    {
        rc= Py_None;
        Py_INCREF(rc);
    }
    Py_XDECREF(tmp);
    return rc;
}

/* vim: set tabstop=4 */
/* vim: set shiftwidth=4 */
/* vim: set expandtab */
/* vim: set foldmethod=indent */
/* vim: set foldnestmax=10 */
/* vim: set nofoldenable */
/* vim: set foldlevel=2 */
