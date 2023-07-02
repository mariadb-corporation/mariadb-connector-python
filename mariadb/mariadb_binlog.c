/*****************************************************************************
  Copyright (C) 2022 Georg Richter and MariaDB Corporation AB

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

#define binlog__doc__ NULL

void
MrdbBinlog_dealloc(MrdbBinlog *self);

static PyObject *MrdbBinlog_fetch(MrdbBinlog *self);
static PyObject *MrdbBinlog_close(MrdbBinlog *self);
static PyObject *MrdbBinlog_filename(MrdbBinlog *self);


#define MA_SET_DICT_ITEM_STRING(dict, key, val)\
{\
  PyObject *x= (val);\
  if (!PyErr_Occurred()) \
  {\
    PyDict_SetItemString(dict, key, x);\
    Py_DECREF(x);\
  }\
  else {\
    printf("File: %s Line: %d\n", __FILE__, __LINE__);\
    PyErr_Print();\
  }\
}

#define STR_AND_LEN(a)  (a).str, (a).length

struct st_event_name {
  const char *event_name;
  uint32_t event_type;
} event_names[]= {
  {"UNKNOWN", UNKNOWN_EVENT},
  {"START_V3", START_EVENT_V3},
  {"QUERY", QUERY_EVENT},
  {"STOP", STOP_EVENT},
  {"ROTATE", ROTATE_EVENT},
  {"INTVAR", INTVAR_EVENT},
  {"LOAD", LOAD_EVENT},
  {"SLAVE", SLAVE_EVENT},
  {"CREATE_FILE", CREATE_FILE_EVENT},
  {"APPEND_BLOCK", APPEND_BLOCK_EVENT},
  {"EXEC_LOAD", EXEC_LOAD_EVENT},
  {"DELETE_FILE", DELETE_FILE_EVENT},
  {"NEW_LOAD", NEW_LOAD_EVENT},
  {"RAND", RAND_EVENT},
  {"USER_VAR", USER_VAR_EVENT},
  {"FORMAT_DESCRIPTION", FORMAT_DESCRIPTION_EVENT},
  {"XID", XID_EVENT},
  {"BEGIN_LOAD_QUERY", BEGIN_LOAD_QUERY_EVENT},
  {"EXECUTE_LOAD_QUERY", EXECUTE_LOAD_QUERY_EVENT},
  {"TABLE_MAP", TABLE_MAP_EVENT},
  {"WRITE_ROWS_V1", WRITE_ROWS_EVENT_V1},
  {"UPDATE_ROWS_V1", UPDATE_ROWS_EVENT_V1},
  {"DELETE_ROWS_V1", DELETE_ROWS_EVENT_V1},
  {"INCIDENT", INCIDENT_EVENT},
  {"HEARTBEAT_LOG", HEARTBEAT_LOG_EVENT},
  {"IGNORABLE", IGNORABLE_LOG_EVENT},
  {"ROWS_QUERY_LOG", ROWS_QUERY_LOG_EVENT},
  {"WRITE_ROWS", WRITE_ROWS_EVENT},
  {"UPDATE_ROWS", UPDATE_ROWS_EVENT},
  {"DELETE_ROWS", DELETE_ROWS_EVENT},
  {"GTID_LOG", GTID_LOG_EVENT},
  {"ANONYMOUS_GTID_LOG", ANONYMOUS_GTID_LOG_EVENT},
  {"PREVIOUS_GTID_LOG", PREVIOUS_GTIDS_LOG_EVENT},
  {"TRANSACTION_CONTEXT", TRANSACTION_CONTEXT_EVENT},
  {"VIEW_CHANGE", VIEW_CHANGE_EVENT},
  {"XA_PREPARE_LOG", XA_PREPARE_LOG_EVENT},
  {"PARTIAL_UPDATE_ROWS", PARTIAL_UPDATE_ROWS_EVENT},
  {"ANNOTATE_ROWS", ANNOTATE_ROWS_EVENT},
  {"BINLOG_CHECKPOINT", BINLOG_CHECKPOINT_EVENT},
  {"GTID", GTID_EVENT},
  {"GTID_LIST", GTID_LIST_EVENT},
  {"START_ENCRYPTION", START_ENCRYPTION_EVENT},
  {"QUERY_COMPRESSED", QUERY_COMPRESSED_EVENT},
  {"WRITE_ROWS_COMPRESSED_V1", WRITE_ROWS_COMPRESSED_EVENT_V1},
  {"UPDATE_ROWS_COMPRESSED_V1", UPDATE_ROWS_COMPRESSED_EVENT_V1},
  {"DELETE_ROWS_COMPRESSED_V1", DELETE_ROWS_COMPRESSED_EVENT_V1},
  {"WRITE_ROWS_COMPRESSED", WRITE_ROWS_COMPRESSED_EVENT},
  {"UPDATE_ROWS_COMPRESSED", UPDATE_ROWS_COMPRESSED_EVENT},
  {"DELETE_ROWS_COMPRESSED", DELETE_ROWS_COMPRESSED_EVENT},
  {NULL, 0}
};

static PyGetSetDef
MrdbBinlog_sets[]=
{
    {"filename", (getter)MrdbBinlog_filename, NULL,
        binlog__doc__, NULL},
    {NULL}
};

static PyMethodDef
MrdbBinlog_Methods[] =
{
    {"fetch", (PyCFunction)MrdbBinlog_fetch,
        METH_NOARGS,
        binlog__doc__},
    {"close", (PyCFunction)MrdbBinlog_close,
        METH_NOARGS,
        binlog__doc__},
    {NULL} /* always last */
};

static struct
PyMemberDef MrdbBinlog_Members[] =
{
    {NULL} /* always last */
};

static int
MrdbBinlog_Initialize(MrdbBinlog *self,
        PyObject *args,
        PyObject *kwargs)
{
    char *key_words[]= {"connection", "filename", "host", "port", "server_id",
                        "start_position", "flags", "raw_data", "verify_checksum", NULL};
    const char *filename= NULL, *host= NULL;
    unsigned int server_id= 0, port= 0, flags= 0;
    unsigned long start_position= 0;
    uint8_t raw_data= 0;
    uint8_t verify_checksum= 1;
    MrdbConnection *connection= NULL;
    MYSQL *mysql= NULL;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs,
                "|O!ssiikibb", key_words, &MrdbConnection_Type,
                &connection, &filename, &host, &port, &server_id,
                &start_position, &flags, &raw_data, &verify_checksum))
    {
        return -1;
    }

    if (connection) {
      if (!connection->mysql)
      {
        mariadb_throw_exception(NULL, Mariadb_ProgrammingError, 0,
                "Connection isn't valid anymore");
        return -1;
      }
      mysql= connection->mysql;
    }

    if (!(self->rpl= mariadb_rpl_init(mysql)))
    {
        mariadb_throw_exception(NULL, Mariadb_ProgrammingError, 0, NULL);
        return -1;
    }

    PyDateTime_IMPORT;

    self->connection= connection;

    mariadb_rpl_optionsv(self->rpl, MARIADB_RPL_SERVER_ID, server_id);
    mariadb_rpl_optionsv(self->rpl, MARIADB_RPL_START, start_position);
    mariadb_rpl_optionsv(self->rpl, MARIADB_RPL_FILENAME, filename, 0);
    mariadb_rpl_optionsv(self->rpl, MARIADB_RPL_FLAGS, flags);
    mariadb_rpl_optionsv(self->rpl, MARIADB_RPL_VERIFY_CHECKSUM, verify_checksum);
    self->raw_data= raw_data;

    if (host)
    {
        if (mysql_optionsv(connection->mysql, MARIADB_OPT_RPL_REGISTER_REPLICA,
                           host, port))
        {
            mariadb_throw_exception(self->connection->mysql, Mariadb_ProgrammingError, 0, NULL);
            return -1;
        }
    }

    if (mariadb_rpl_open(self->rpl))
    {
        mariadb_throw_exception(0, Mariadb_ProgrammingError, self->rpl->error_no, self->rpl->error_msg);
        return -1;
    }

    if (PyErr_Occurred())
        return -1;

    return 0;
}

void mrdb_process_status(PyObject *d_event, char *str_status, size_t status_len)
{
  char *p= str_status, *end= str_status + status_len;
  PyObject *d_status= PyDict_New();
  const char *flag_name[]= {"flags2", "sql_mode", "catalog", "auto_increment", 
                            "character_set", "time_zone", "catalog_nz", "lc_time_names",
                            "character_set_db", "tablemap_for_update", "master_data_written",
                            "invokers", "updated_db_names", "microseconds"};
  while (p < end)
  {
    u_char status;

    status= *p++;

    switch (status)
    {
      case QS_FLAGS2:
      case QS_MASTER_DATA_WRITTEN:
      {
        uint32_t val;
        val= uint4korr(p);
        p+= 4;
        MA_SET_DICT_ITEM_STRING(d_status, flag_name[status], PyLong_FromUnsignedLong((unsigned long)val));
      }
      break;
      case QS_SQL_MODE:
      case QS_TABLE_MAP_FOR_UPDATE:
      {
        uint64_t flags;
        flags= uint8korr(p);
        MA_SET_DICT_ITEM_STRING(d_status, flag_name[status], PyLong_FromUnsignedLongLong(flags));
        p+= 8;
      }
      break;
      case QS_CATALOG:
      case QS_TIMEZONE:
      case QS_CATALOG_NZ:
      {
        uint8_t len;
        len= *p++;
        MA_SET_DICT_ITEM_STRING(d_status, flag_name[status], PyUnicode_FromStringAndSize(p, (Py_ssize_t)len));
        p+= len;
        if (status == QS_CATALOG)
          p++;
      }
      break;
      case QS_UPDATED_DB_NAMES:
      {
        uint8_t count, i;
        PyObject *tuple;
        count= *p++;
        if (count) {
          tuple= PyTuple_New(count);
          for (i=0; i < count; i++)
          {
            PyTuple_SetItem(tuple, i, PyUnicode_FromString(p));
            p+= (strlen(p) + 1);
          }
          MA_SET_DICT_ITEM_STRING(d_status, flag_name[status], tuple);
        }
        break;
      }
      case QS_LC_TIME_NAMES:
      {
        uint16_t val= uint2korr(p);
        MA_SET_DICT_ITEM_STRING(d_status, flag_name[status], PyLong_FromUnsignedLong((unsigned long)val));
        p+= 2;
        break;
      }
      case QS_CHARSET_DATABASE:
      {
        uint16_t val;
        MARIADB_CHARSET_INFO *info= NULL;
        val= uint2korr(p);
        p+=2;
        info= mariadb_get_charset_by_nr(val);
        MA_SET_DICT_ITEM_STRING(d_status, flag_name[status], PyUnicode_FromString(info ? info->csname : "-"));
      }
      break;
      case QS_MICROSECONDS:
      {
        uint32_t val;
        val= uint3korr(p);
        p+= 3;
        MA_SET_DICT_ITEM_STRING(d_status, flag_name[status], PyLong_FromUnsignedLong((unsigned long)val));
      }
      break;
      case QS_AUTO_INCREMENT:
      {
        PyObject *tuple= PyTuple_New(2);
        uint16_t val1, val2;
        val1= uint2korr(p);
        p+= 2;
        val2= uint2korr(p);
        p+=2;
        PyTuple_SetItem(tuple, 0, PyLong_FromUnsignedLong((unsigned long)val1));
        PyTuple_SetItem(tuple, 1, PyLong_FromUnsignedLong((unsigned long)val2));
        MA_SET_DICT_ITEM_STRING(d_status, flag_name[status], tuple);
      }
      break;
      case QS_CHARSET:
      {
        PyObject *tuple= PyTuple_New(3);
        MARIADB_CHARSET_INFO *info= NULL;
        uint16_t val1, val2, val3;
        val1= uint2korr(p);
        p+= 2;
        val2= uint2korr(p);
        p+=2;
        val3= uint2korr(p);
        p+=2;
        info= mariadb_get_charset_by_nr(val1);
        PyTuple_SetItem(tuple, 0, PyUnicode_FromString(info ? info->csname : ""));
        info= mariadb_get_charset_by_nr(val2);
        PyTuple_SetItem(tuple, 1, PyUnicode_FromString(info ? info->name : ""));
        info= mariadb_get_charset_by_nr(val3);
        PyTuple_SetItem(tuple, 2, PyUnicode_FromString(info ? info->name : ""));
        MA_SET_DICT_ITEM_STRING(d_status, flag_name[status], tuple);
      }
      break;
      case QS_INVOKERS:
      {
        PyObject *dict= PyDict_New();
        uint8_t len;
        len= *p++;
        MA_SET_DICT_ITEM_STRING(dict, "username", PyUnicode_FromStringAndSize(p, (Py_ssize_t)len));
        p+= len;
        len= *p++;
        MA_SET_DICT_ITEM_STRING(dict, "hostname", PyUnicode_FromStringAndSize(p, (Py_ssize_t)len));
        p+= len;
        MA_SET_DICT_ITEM_STRING(d_status, flag_name[status], dict);
      }
      break;

      case QS_DEFAULT_COLLATION_FOR_UTF8MB4:
      {
        p+= 2;
        break;
      }

      case QS_DDL_LOGGED_WITH_XID:
      {
        p+= 8;
        break;
      }

      case QS_DEFAULT_TABLE_ENCRYPTION:
      {
        p++;
        break;
      }

      case QS_SQL_REQUIRE_PRIMARY_KEY:
      {
        p++;
        break;
      }

      case QS_XID: 
      {
        p+= 8;
        break;
      }

      default:
        return;
        break;
    }
  }
  MA_SET_DICT_ITEM_STRING(d_event, "status", d_status);
}

static PyObject *MrdbBinlog_fetch(MrdbBinlog *self)
{
    MARIADB_RPL_EVENT *event= NULL;
    PyObject *ret= NULL;
    PyObject *d_header;
    PyObject *d_event;
    PyObject *raw;
    uint32_t i= 0;

    if (!(event= mariadb_rpl_fetch(self->rpl, event)))
    {
        if (self->rpl->mysql && mysql_errno(self->connection->mysql))
        {
            mariadb_throw_exception(self->connection->mysql, Mariadb_ProgrammingError, 0, NULL);
            return NULL;
        }
        Py_RETURN_NONE;
    }

    ret= PyDict_New();
    if (self->rpl->mysql)
      raw= PyBytes_FromStringAndSize((char *)event->raw_data + event->raw_data_ofs,
                                      event->raw_data_size - event->raw_data_ofs);
    else
      raw= PyBytes_FromStringAndSize((char *)event->raw_data, event->raw_data_size);

    if (self->raw_data)
    {
      MA_SET_DICT_ITEM_STRING(ret, "raw", raw);
    }

    d_header= PyDict_New();

    if (self->rpl->encrypted)
    {
      MA_SET_DICT_ITEM_STRING(ret, "encrypted", PyLong_FromUnsignedLong((unsigned long)1));
      MA_SET_DICT_ITEM_STRING(ret, "header", d_header);
      return ret;
    } else {
      MA_SET_DICT_ITEM_STRING(d_header, "event_type",
                              PyLong_FromUnsignedLong((unsigned long)event->event_type));
      while (event_names[i].event_name)
      {
        if (event_names[i].event_type == event->event_type)
        {
          MA_SET_DICT_ITEM_STRING(d_header, "event_name", PyUnicode_FromString(event_names[i].event_name));
          break;
        }
        i++;
      }
      MA_SET_DICT_ITEM_STRING(d_header, "event_length",
                              PyLong_FromUnsignedLong((unsigned long)event->event_length));
      MA_SET_DICT_ITEM_STRING(d_header, "checksum",
                              PyLong_FromUnsignedLong((unsigned long)event->checksum));
      MA_SET_DICT_ITEM_STRING(d_header, "timestamp",
                              PyLong_FromUnsignedLong((unsigned long)event->timestamp));
      MA_SET_DICT_ITEM_STRING(d_header, "server_id",
                              PyLong_FromUnsignedLong((unsigned long)event->server_id));
      MA_SET_DICT_ITEM_STRING(d_header, "start_position",
                              PyLong_FromUnsignedLong(event->event_type == ROTATE_EVENT ? 
                              (unsigned long)event->event.rotate.position : 
                              (unsigned long) event->next_event_pos - event->event_length));
      MA_SET_DICT_ITEM_STRING(d_header, "next_event_position",
                              PyLong_FromUnsignedLong((unsigned long)event->next_event_pos));
      MA_SET_DICT_ITEM_STRING(d_header, "flags",
                              PyLong_FromUnsignedLong((unsigned long)event->flags));
    }
    d_event= PyDict_New();

    switch(event->event_type)
    {
      case BEGIN_LOAD_QUERY_EVENT:
        MA_SET_DICT_ITEM_STRING(d_event, "file_id",
                                PyLong_FromUnsignedLong((unsigned long)event->event.begin_load_query.file_id));
        MA_SET_DICT_ITEM_STRING(d_event, "data",
                                PyBytes_FromString((char *)event->event.begin_load_query.data));
        break;
      case EXECUTE_LOAD_QUERY_EVENT:
        MA_SET_DICT_ITEM_STRING(d_event, "thread_id",
                                PyLong_FromUnsignedLong((unsigned long)event->event.execute_load_query.thread_id));
        MA_SET_DICT_ITEM_STRING(d_event, "execution_time",
                                PyLong_FromUnsignedLong((unsigned long)event->event.execute_load_query.execution_time));
        MA_SET_DICT_ITEM_STRING(d_event, "error_code",
                                PyLong_FromUnsignedLong((unsigned long)event->event.execute_load_query.error_code));
        MA_SET_DICT_ITEM_STRING(d_event, "file_id",
                                PyLong_FromUnsignedLong((unsigned long)event->event.execute_load_query.file_id));
        MA_SET_DICT_ITEM_STRING(d_event, "ofs_1",
                                PyLong_FromUnsignedLong((unsigned long)event->event.execute_load_query.ofs1));
        MA_SET_DICT_ITEM_STRING(d_event, "ofs_2",
                                PyLong_FromUnsignedLong((unsigned long)event->event.execute_load_query.ofs2));
        MA_SET_DICT_ITEM_STRING(d_event, "duplicate_flag",
                                PyLong_FromUnsignedLong((unsigned long)event->event.execute_load_query.duplicate_flag));
        MA_SET_DICT_ITEM_STRING(d_event, "status",
                                PyBytes_FromStringAndSize(STR_AND_LEN(event->event.execute_load_query.status_vars)));
        MA_SET_DICT_ITEM_STRING(d_event, "schema",
                                PyUnicode_FromStringAndSize(STR_AND_LEN(event->event.execute_load_query.schema)));
        
        break;
      case STOP_EVENT:
        break;
      case USER_VAR_EVENT:
        MA_SET_DICT_ITEM_STRING(d_event, "variable",
                                PyUnicode_FromStringAndSize(STR_AND_LEN(event->event.uservar.name)));
        MA_SET_DICT_ITEM_STRING(d_event, "is_null",
                                PyLong_FromUnsignedLong((unsigned long)event->event.uservar.is_null));
        if (!event->event.uservar.is_null) {
          MARIADB_CHARSET_INFO *info;
          MA_SET_DICT_ITEM_STRING(d_event, "type",
                                  PyLong_FromUnsignedLong((unsigned long)event->event.uservar.type));
          info= mariadb_get_charset_by_nr(event->event.uservar.charset_nr);
          MA_SET_DICT_ITEM_STRING(d_event, "collation",
                                  PyUnicode_FromString(info->name));
          MA_SET_DICT_ITEM_STRING(d_event, "charset",
                                  PyUnicode_FromString(info->csname));
          switch (event->event.uservar.type)
          {
            case DECIMAL_RESULT:
            case REAL_RESULT:
              MA_SET_DICT_ITEM_STRING(d_event, "value",
                                    PyBytes_FromStringAndSize(STR_AND_LEN(event->event.uservar.value)));
              break;
            case STRING_RESULT:
              MA_SET_DICT_ITEM_STRING(d_event, "value",
                                    PyBytes_FromStringAndSize(STR_AND_LEN(event->event.uservar.value)));

              break;
            case INT_RESULT:
            {
              uint64_t val= uint8korr(event->event.uservar.value.str); 
              MA_SET_DICT_ITEM_STRING(d_event, "value", (event->event.uservar.flags) ?
                                    PyLong_FromUnsignedLongLong(val) :
                                    PyLong_FromLongLong((int64_t)val));
            }
              break;
            default:
              printf("not handled: %d\n", event->event.uservar.type);
              break;
          }
          MA_SET_DICT_ITEM_STRING(d_event, "flags",
                                  PyLong_FromUnsignedLong((unsigned long)event->event.uservar.flags));
        }
        break;

      case ROTATE_EVENT:
      {
        MA_SET_DICT_ITEM_STRING(d_event, "position",
                                PyLong_FromUnsignedLong((unsigned long)event->event.rotate.position));
        MA_SET_DICT_ITEM_STRING(d_event, "filename", 
                                PyUnicode_FromStringAndSize(event->event.rotate.filename.str,
                                                            event->event.rotate.filename.length));
        break;
      }
      case RAND_EVENT:
      {
        MA_SET_DICT_ITEM_STRING(d_event, "rand_seed1",
                                PyLong_FromUnsignedLong((unsigned long)event->event.rand.first_seed));
        MA_SET_DICT_ITEM_STRING(d_event, "rand_seed2",
                                PyLong_FromUnsignedLong((unsigned long)event->event.rand.second_seed));
        break;
      }
      case FORMAT_DESCRIPTION_EVENT:
      {
        MA_SET_DICT_ITEM_STRING(d_event, "format",
                                PyLong_FromUnsignedLong((unsigned long)event->event.format_description.format));
        MA_SET_DICT_ITEM_STRING(d_event, "server_version", 
                                PyUnicode_FromString(event->event.format_description.server_version));
        MA_SET_DICT_ITEM_STRING(d_event, "timestamp", 
                                PyLong_FromUnsignedLong((unsigned long)event->event.format_description.timestamp));
        MA_SET_DICT_ITEM_STRING(d_event, "header_length",
                                PyLong_FromUnsignedLong((unsigned long)event->event.format_description.header_len));
        if (event->event.format_description.post_header_lengths.length)
        {
          PyObject *list= PyList_New(event->event.format_description.post_header_lengths.length);

          for (uint16_t i= 0; i < event->event.format_description.post_header_lengths.length; i++)
          {
            PyList_SetItem(list, i, PyLong_FromUnsignedLong((u_char)event->event.format_description.post_header_lengths.str[i]));
          }
          MA_SET_DICT_ITEM_STRING(d_event, "post_header_lengths", list);
        }
        break;
      }
      case GTID_LIST_EVENT:
      {
        MA_SET_DICT_ITEM_STRING(d_event, "gtid_count",
                                PyLong_FromUnsignedLong((unsigned long)event->event.gtid_list.gtid_cnt));

        if (event->event.gtid_list.gtid_cnt)
        {
          PyObject *tuple= PyTuple_New(event->event.gtid_list.gtid_cnt);
          uint32_t i;

          for (i=0; i < event->event.gtid_list.gtid_cnt; i++)
          {
            PyObject *gtid= PyDict_New();
            MA_SET_DICT_ITEM_STRING(gtid, "domain_id", 
                                    PyLong_FromUnsignedLong((unsigned long)event->event.gtid_list.gtid[i].domain_id));
            MA_SET_DICT_ITEM_STRING(gtid, "server_id",
                                    PyLong_FromUnsignedLong((unsigned long)event->event.gtid_list.gtid[i].server_id));
            MA_SET_DICT_ITEM_STRING(gtid, "sequence_nr",
                                    PyLong_FromUnsignedLong((unsigned long)event->event.gtid_list.gtid[i].sequence_nr));
            PyTuple_SetItem(tuple, i, gtid);
          }
          MA_SET_DICT_ITEM_STRING(d_event, "gtid_list", tuple);
        }
        break;
      }
      case XA_PREPARE_LOG_EVENT:
      {
        MA_SET_DICT_ITEM_STRING(d_event, "one_phase", 
                                PyLong_FromUnsignedLong((unsigned long)event->event.xa_prepare_log.one_phase));
        MA_SET_DICT_ITEM_STRING(d_event, "format_id", 
                                PyLong_FromUnsignedLong((unsigned long)event->event.xa_prepare_log.format_id));
        MA_SET_DICT_ITEM_STRING(d_event, "gtrid_len", 
                                PyLong_FromUnsignedLong((unsigned long)event->event.xa_prepare_log.gtrid_len));
        MA_SET_DICT_ITEM_STRING(d_event, "bqual_len", 
                                PyLong_FromUnsignedLong((unsigned long)event->event.xa_prepare_log.bqual_len));
        MA_SET_DICT_ITEM_STRING(d_event, "xid", 
                                PyBytes_FromStringAndSize(STR_AND_LEN(event->event.xa_prepare_log.xid)));
        
        break;
      }
      case BINLOG_CHECKPOINT_EVENT:
      {
        MA_SET_DICT_ITEM_STRING(d_event, "filename", 
                                PyUnicode_FromStringAndSize(STR_AND_LEN(event->event.checkpoint.filename)));
        break;
      }
      case ANONYMOUS_GTID_LOG_EVENT:
      case PREVIOUS_GTIDS_LOG_EVENT:
        MA_SET_DICT_ITEM_STRING(d_event, "commit_flag", 
                                PyLong_FromUnsignedLong((unsigned long)event->event.gtid_log.commit_flag));
        MA_SET_DICT_ITEM_STRING(d_event, "source_id", 
                                PyBytes_FromStringAndSize(event->event.gtid_log.source_id, 16));
        MA_SET_DICT_ITEM_STRING(d_event, "sequence_nr", 
                                PyLong_FromUnsignedLong((unsigned long)event->event.gtid_log.sequence_nr));
        break;
      case GTID_EVENT:
      {
        MA_SET_DICT_ITEM_STRING(d_event, "sequence_nr",
                                PyLong_FromUnsignedLong((unsigned long)event->event.gtid.sequence_nr));
        MA_SET_DICT_ITEM_STRING(d_event, "domain_id",
                                PyLong_FromUnsignedLong((unsigned long)event->event.gtid.domain_id));
        MA_SET_DICT_ITEM_STRING(d_event, "flags", 
                                PyLong_FromUnsignedLong((unsigned long)event->event.gtid.flags));
        if (event->event.gtid.flags & FL_GROUP_COMMIT_ID)
        {
          MA_SET_DICT_ITEM_STRING(d_event, "commit_id",
                                  PyLong_FromUnsignedLong((unsigned long)event->event.gtid.commit_id));
        }
#ifdef MARIADB_PACKAGE_VERSION_ID > 30305
        else if (event->event.gtid.flags & (FL_PREPARED_XA | FL_COMPLETED_XA))
        {
          MA_SET_DICT_ITEM_STRING(d_event, "format_id",
                                  PyLong_FromUnsignedLong((unsigned long)event->event.gtid.format_id));
          MA_SET_DICT_ITEM_STRING(d_event, "gtrid_length",
                                  PyLong_FromUnsignedLong((unsigned long)event->event.gtid.gtrid_len));
          MA_SET_DICT_ITEM_STRING(d_event, "bqual_length",
                                  PyLong_FromUnsignedLong((unsigned long)event->event.gtid.bqual_len));
          MA_SET_DICT_ITEM_STRING(d_event, "xid",
                                  PyBytes_FromStringAndSize(event->event.gtid.xid.str,
                                                            event->event.gtid.xid.length));
        }
#endif
        break;
      }
      case START_ENCRYPTION_EVENT:
        MA_SET_DICT_ITEM_STRING(d_event, "scheme",
                                PyLong_FromUnsignedLong((unsigned long)event->event.start_encryption.scheme));
        MA_SET_DICT_ITEM_STRING(d_event, "key_version",
                                PyLong_FromUnsignedLong((unsigned long)event->event.start_encryption.key_version));
        MA_SET_DICT_ITEM_STRING(d_event, "nonce",
                                PyBytes_FromStringAndSize(event->event.start_encryption.nonce, 12));
      break;
      case QUERY_EVENT:
      case QUERY_COMPRESSED_EVENT:
      {
        if (event->event_type == QUERY_COMPRESSED_EVENT)
        {
          MA_SET_DICT_ITEM_STRING(d_event, "compressed",
                                  PyLong_FromUnsignedLong((unsigned long)1));
        }
        MA_SET_DICT_ITEM_STRING(d_event, "status",
                                PyBytes_FromStringAndSize(STR_AND_LEN(event->event.query.status)));
        MA_SET_DICT_ITEM_STRING(d_event, "thread_id",
                                PyLong_FromUnsignedLong((unsigned long)event->event.query.thread_id));
        MA_SET_DICT_ITEM_STRING(d_event, "seconds",
                                PyLong_FromUnsignedLong((unsigned long)event->event.query.seconds));
        MA_SET_DICT_ITEM_STRING(d_event, "schema",
                                PyUnicode_FromStringAndSize(STR_AND_LEN(event->event.query.database)));
        MA_SET_DICT_ITEM_STRING(d_event, "error_no",
                                PyLong_FromLong((unsigned long)event->event.query.errornr));
        if (event->event.query.statement.str && event->event.query.statement.length)
        {
          PyObject *b= PyBytes_FromStringAndSize(STR_AND_LEN(event->event.query.statement));
          MA_SET_DICT_ITEM_STRING(d_event, "statement", b);
        }
        break;
      }
      case ANNOTATE_ROWS_EVENT:
      {
        MA_SET_DICT_ITEM_STRING(d_event, "statement", 
                                PyBytes_FromStringAndSize(STR_AND_LEN(event->event.annotate_rows.statement)));
        break;
      }
      case TABLE_MAP_EVENT:
      {
        MA_SET_DICT_ITEM_STRING(d_event, "table_id",
                                PyLong_FromUnsignedLongLong(event->event.table_map.table_id));
        MA_SET_DICT_ITEM_STRING(d_event, "schema",
                                PyUnicode_FromStringAndSize(STR_AND_LEN(event->event.table_map.database)));
        MA_SET_DICT_ITEM_STRING(d_event, "table", 
                                PyUnicode_FromStringAndSize(STR_AND_LEN(event->event.table_map.table)));
        MA_SET_DICT_ITEM_STRING(d_event, "column_count",
                                PyLong_FromUnsignedLong((unsigned long)event->event.table_map.column_count));
        MA_SET_DICT_ITEM_STRING(d_event, "column_types",
                                PyBytes_FromStringAndSize(STR_AND_LEN(event->event.table_map.column_types)));
        MA_SET_DICT_ITEM_STRING(d_event, "metadata",
                                PyBytes_FromStringAndSize(STR_AND_LEN(event->event.table_map.metadata)));
        MA_SET_DICT_ITEM_STRING(d_event, "null_indicator",
          PyBytes_FromStringAndSize((char *)event->event.table_map.null_indicator,
                                    (event->event.table_map.column_count + 8) / 7));
        break;
      }
      case WRITE_ROWS_EVENT_V1:
      case WRITE_ROWS_EVENT:
      case UPDATE_ROWS_EVENT_V1:
      case UPDATE_ROWS_EVENT:
      case DELETE_ROWS_EVENT_V1:
      case DELETE_ROWS_EVENT:
      case WRITE_ROWS_COMPRESSED_EVENT_V1:
      case UPDATE_ROWS_COMPRESSED_EVENT_V1:
      case DELETE_ROWS_COMPRESSED_EVENT_V1:
      case WRITE_ROWS_COMPRESSED_EVENT:
      case UPDATE_ROWS_COMPRESSED_EVENT:
      case DELETE_ROWS_COMPRESSED_EVENT:
      {
        MA_SET_DICT_ITEM_STRING(d_event, "type",
                                PyLong_FromUnsignedLong((unsigned long)event->event.rows.type));
        MA_SET_DICT_ITEM_STRING(d_event, "table_id",
                                PyLong_FromUnsignedLong((unsigned long)event->event.rows.table_id));
        MA_SET_DICT_ITEM_STRING(d_event, "flags",
                                PyLong_FromUnsignedLong((unsigned long)event->event.rows.flags));
        MA_SET_DICT_ITEM_STRING(d_event, "extra_data",
                                PyBytes_FromStringAndSize(event->event.rows.extra_data, event->event.rows.extra_data_size));
        MA_SET_DICT_ITEM_STRING(d_event, "column_count",
                                PyLong_FromUnsignedLong((unsigned long)event->event.rows.column_count));
        if (event->event_type == UPDATE_ROWS_EVENT ||
            event->event_type == UPDATE_ROWS_EVENT_V1)
        {
          MA_SET_DICT_ITEM_STRING(d_event, "update_bitmap",
                                  PyBytes_FromStringAndSize((void *)event->event.rows.column_update_bitmap, (event->event.rows.column_count + 7) / 8));
        }
        if (event->event.rows.row_data_size)
        {
          MA_SET_DICT_ITEM_STRING(d_event, "row_data",
               PyBytes_FromStringAndSize(event->event.rows.row_data, event->event.rows.row_data_size));
        }
        if (self->tm_event)
        {
          MARIADB_RPL_ROW *row, *tmp;
          uint64_t row_count= 0;
          PyObject *list= PyList_New(0);

          tmp= row= mariadb_rpl_extract_rows(self->rpl, self->tm_event, event);
          while (tmp)
          {
            PyObject *tpl= PyTuple_New(tmp->column_count);
            for (i=0; i < row->column_count; i++)
            {
              PyObject *col= Py_None;
              MARIADB_RPL_VALUE column= tmp->columns[i];

              if (column.is_null)
              {
                PyTuple_SetItem(tpl, i, Py_None);
                continue;
              }
              switch(column.field_type) {
                case MYSQL_TYPE_TINY:
                case MYSQL_TYPE_YEAR:
                case MYSQL_TYPE_SHORT:
                case MYSQL_TYPE_INT24:
                case MYSQL_TYPE_LONG:
                case MYSQL_TYPE_LONGLONG:
                  col= PyLong_FromUnsignedLongLong(column.val.ull);
                  break;
                case MYSQL_TYPE_DOUBLE:
                  col= PyFloat_FromDouble(column.val.d);
                  break;
                case MYSQL_TYPE_FLOAT:
                  col= PyFloat_FromDouble((double)column.val.f);
                  break;
                case MYSQL_TYPE_TINY_BLOB:
                case MYSQL_TYPE_MEDIUM_BLOB:
                case MYSQL_TYPE_BLOB:
                case MYSQL_TYPE_LONG_BLOB:
                case MYSQL_TYPE_GEOMETRY:
                case MYSQL_TYPE_BIT:
                  col= PyBytes_FromStringAndSize(column.val.str.str, column.val.str.length);
                  break;
                case MYSQL_TYPE_STRING:
                case MYSQL_TYPE_VARCHAR:
                case MYSQL_TYPE_VAR_STRING:
                case MYSQL_TYPE_NEWDECIMAL:
                  col= PyBytes_FromStringAndSize(column.val.str.str, column.val.str.length);
                  break;
                case MYSQL_TYPE_DATE:
                  {
                    #define MAX_DATE_LEN 10
                    MYSQL_TIME *tm= &column.val.tm;
                    char str_date[MAX_DATE_LEN + 1];

                    snprintf(str_date, MAX_DATE_LEN + 1, "%04d-%02d-%02d",
                             tm->year, tm->month, tm->day);
                    col= PyUnicode_FromStringAndSize(str_date, MAX_DATE_LEN);
                    break;
                  }
                case MYSQL_TYPE_TIME:
                  col= Mrdb_GetTimeDelta(&column.val.tm);
                  break;
                case MYSQL_TYPE_DATETIME:
                {
                  #define MAX_DATETIME_LEN 26
                  MYSQL_TIME *tm= &column.val.tm;
                  char str_dt[MAX_DATETIME_LEN + 1];

                  if (tm->second_part)
                     snprintf(str_dt, MAX_DATETIME_LEN, "%04d-%02d-%02d %02d:%02d:%02d.%ld",
                              tm->year, tm->month, tm->day, tm->hour, tm->minute, tm->second, tm->second_part);
                  else
                    snprintf(str_dt, MAX_DATETIME_LEN, "%04d-%02d-%02d %02d:%02d:%02d",
                             tm->year, tm->month, tm->day, tm->hour, tm->minute, tm->second);
                  col= PyUnicode_FromString(str_dt);
                  break;
                }
                case MYSQL_TYPE_TIMESTAMP2:
                {
                  col= PyUnicode_FromStringAndSize(column.val.str.str, column.val.str.length);
                  break;
                }
                case MYSQL_TYPE_ENUM:
                case MYSQL_TYPE_SET:
                {
                  col= PyUnicode_FromStringAndSize(column.val.str.str, column.val.str.length);
                  break;
                }
                default:
                  printf("unhandled type: %d!\n", column.field_type);
                  exit(0);
                  break;
              }
              PyTuple_SetItem(tpl, i, col);
            }
            PyList_Append(list,tpl);
            row_count++;
            tmp= tmp->next;
          }
          MA_SET_DICT_ITEM_STRING(d_event, "data", list);
          MA_SET_DICT_ITEM_STRING(d_event, "row_count",
                                PyLong_FromUnsignedLongLong(row_count));

          /* If STMT_END flag is set, we can free and unset table_map event */
          if (event->event.rows.flags & STMT_END_F)
          {
            mariadb_free_rpl_event(self->tm_event);
            self->tm_event= NULL;
          }
        }
        break;
      }
      case XID_EVENT:
      {
        MA_SET_DICT_ITEM_STRING(d_event, "transaction_nr",
                                PyLong_FromUnsignedLongLong((unsigned long long)event->event.xid.transaction_nr));
        break;
      }
      case INTVAR_EVENT:
      {
        MA_SET_DICT_ITEM_STRING(d_event, "int_type",
                                PyLong_FromUnsignedLong((unsigned long)event->event.intvar.type));
        MA_SET_DICT_ITEM_STRING(d_event, "int_value",
                                PyLong_FromUnsignedLongLong(event->event.intvar.value)); 
        break;
      }
      default:
        if (!self->raw_data)
          MA_SET_DICT_ITEM_STRING(ret, "raw", raw);
        break;
    }

    MA_SET_DICT_ITEM_STRING(ret, "header", d_header);
    MA_SET_DICT_ITEM_STRING(ret, "event", d_event);

    if (event->event_type == TABLE_MAP_EVENT)
    {
      self->tm_event= event;
    }
    else {
       mariadb_free_rpl_event(event);
    }

    return ret;
}

static int MrdbBinlog_traverse(
        MrdbBinlog *self,
        visitproc visit,
        void *arg)
{
    return 0;
}

static PyObject *MrdbBinlog_repr(MrdbBinlog *self)
{
    char cobj_repr[384];

    if (!self->closed)
        snprintf(cobj_repr, 384, "<mariadb.binlog connected to '%s' at %p>",
                self->connection->host, self);
    else
        snprintf(cobj_repr, 384, "<mariadb.connection (closed) at %p>",
                self);
    return PyUnicode_FromString(cobj_repr);
}

PyTypeObject MrdbBinlog_Type = {
    PyVarObject_HEAD_INIT(NULL, 0)
    "mariadb.binlog",
    sizeof(MrdbBinlog),
    0,
    (destructor)MrdbBinlog_dealloc, /* tp_dealloc */
    0, /*tp_print*/
    0, /* tp_getattr */
    0, /* tp_setattr */
    0, /* PyAsyncMethods* */
    (reprfunc)MrdbBinlog_repr, /* tp_repr */

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
    binlog__doc__, /* tp_doc Documentation string */

    /* call function for all accessible objects */
    (traverseproc)MrdbBinlog_traverse, /* tp_traverse */

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
    (struct PyMethodDef *)MrdbBinlog_Methods, /* tp_methods */
    (struct PyMemberDef *)MrdbBinlog_Members, /* tp_members */
    MrdbBinlog_sets, /* (struct getsetlist *) tp_getset; */
    0, /* (struct _typeobject *) tp_base; */
    0, /* (PyObject *) tp_dict */
    0, /* (descrgetfunc) tp_descr_get */
    0, /* (descrsetfunc) tp_descr_set */
    0, /* (long) tp_dictoffset */
    (initproc)MrdbBinlog_Initialize, /* tp_init */
    PyType_GenericAlloc, //NULL, /* tp_alloc */
    PyType_GenericNew, //NULL, /* tp_new */
    NULL, /* tp_free Low-level free-memory routine */ 
    0, /* (PyObject *) tp_bases */
    0, /* (PyObject *) tp_mro method resolution order */
    0, /* (PyObject *) tp_defined */
};

/* destructor of MariaDB Connection object */
void MrdbBinlog_dealloc(MrdbBinlog *self)
{
    if (self)
    {
        Py_TYPE(self)->tp_free((PyObject*)self);
    }
}

static PyObject *MrdbBinlog_close(MrdbBinlog *self)
{
  if (self->rpl)
    mariadb_rpl_close(self->rpl);
  Py_RETURN_NONE;  
}

static PyObject *MrdbBinlog_filename(MrdbBinlog *self)
{
  char *filename= NULL;
  size_t len= 0;

  if (mariadb_rpl_get_optionsv(self->rpl, MARIADB_RPL_FILENAME, &filename, &len) ||
      !filename || !len)
  {
    Py_RETURN_NONE;
  }

  return PyUnicode_FromStringAndSize(filename, (Py_ssize_t)len);
}
