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
#include "mariadb_python.h"
#include <datetime.h>

/* User callback function */
void field_fetch_callback(void *data, unsigned int column, unsigned char **row)
{
  Mariadb_Cursor *self= (Mariadb_Cursor *)data;
  if (!PyDateTimeAPI)
    PyDateTime_IMPORT;

  switch(self->fields[column].type) {
    case MYSQL_TYPE_NULL:
      Py_INCREF(Py_None);
      self->values[column]= Py_None;
      break;
    case MYSQL_TYPE_TINY:
      self->values[column]= (self->fields[column].flags & UNSIGNED_FLAG) ?
           PyLong_FromUnsignedLong((unsigned long)*row[0]) :
           PyLong_FromLong((long)*row[0]);
      *row+= 1;
      break;
    case MYSQL_TYPE_SHORT:
    case MYSQL_TYPE_YEAR:
      self->values[column]= (self->fields[column].flags & UNSIGNED_FLAG) ?
           PyLong_FromUnsignedLong((unsigned long)uint2korr(*row)) :
           PyLong_FromLong((long)sint2korr(*row));
      *row+= 2;
      break;
    case MYSQL_TYPE_INT24:
      self->values[column]= (self->fields[column].flags & UNSIGNED_FLAG) ?
           PyLong_FromUnsignedLong((unsigned long)uint3korr(*row)) :
           PyLong_FromLong((long)sint3korr(*row));
      *row+= 4;
      break;
    case MYSQL_TYPE_LONG:
      self->values[column]= (self->fields[column].flags & UNSIGNED_FLAG) ?
           PyLong_FromUnsignedLong((unsigned long)uint4korr(*row)) :
           PyLong_FromLong((long)sint4korr(*row));
      *row+= 4;
      break;
    case MYSQL_TYPE_LONGLONG:
    {
      long long l= sint8korr(*row);
      self->values[column]= (self->fields[column].flags & UNSIGNED_FLAG) ?
           PyLong_FromUnsignedLongLong((unsigned long long)l) :
           PyLong_FromLong(l);
      *row+= 8;
      break;
    }
    case MYSQL_TYPE_FLOAT:
    {
      float f;
      float4get(f, *row);
      self->values[column]= PyFloat_FromDouble((double)f);
      *row+= 4;
      break;
    }
    case MYSQL_TYPE_DOUBLE:
    {
      double d;
      float8get(d, *row);
      self->values[column]= PyFloat_FromDouble(d);
      *row+= 8;
      break;
    }
    case MYSQL_TYPE_DATETIME:
    case MYSQL_TYPE_TIMESTAMP:
    {
      uint8_t len= 0;
      int year= 0, month= 0, day= 0,
          hour= 0, minute= 0, second= 0, second_part= 0;

      len= (uint8_t)mysql_net_field_length(row);
      if (!len)
      {
        self->values[column]= PyDateTime_FromDateAndTime(0,0,0,0,0,0,0);
        break;
      }
      year= uint2korr(*row);
      month= uint1korr(*row + 2);
      day= uint1korr(*row + 3);
      if (len > 4)
      {
        hour= uint1korr(*row + 4);
        minute= uint1korr(*row + 5);
        second= uint1korr(*row + 6);
      }
      if (len == 11)
        second_part= uint4korr(*row + 7);
      self->values[column]= PyDateTime_FromDateAndTime(year, month, day, hour, minute, second, second_part);
      *row+= len;
      break;
    }
    case MYSQL_TYPE_DATE:
    {
      uint8_t len= 0;
      int year, month, day;

      len= (uint8_t)mysql_net_field_length(row);

      if (!len)
      {
        self->values[column]= PyDate_FromDate(0,0,0);
        break;
      }
      year= uint2korr(*row);
      month= uint1korr(*row + 2);
      day= uint1korr(*row + 3);
      self->values[column]= PyDate_FromDate(year, month, day);
      *row+= len;
      break;
    }
    case MYSQL_TYPE_TIME:
    {
      uint8_t len= 0,
              is_negative= 0,
              minute= 0,
              second= 0;
      int32_t hour;
      uint32_t day, second_part= 0;

      len= (uint8_t)mysql_net_field_length(row);
      if (!len)
      {
        self->values[column]= PyTime_FromTime(0,0,0,0);
        break;
      }
      is_negative= uint1korr(*row);
      day= uint4korr(*row + 1);
      hour= uint1korr(*row + 5);
      minute= uint1korr(*row + 6);
      second= uint1korr(*row + 7);
      if (len > 8)
        second_part= uint4korr(*row + 8);
      if (day)
        hour+= (day * 24);
      if (is_negative)
        hour*= -1;
      self->values[column]= PyTime_FromTime(hour, minute, second, second_part);
      *row+= len;
      break;
    }
    case MYSQL_TYPE_TINY_BLOB:
    case MYSQL_TYPE_MEDIUM_BLOB:
    case MYSQL_TYPE_BLOB:
    case MYSQL_TYPE_LONG_BLOB:
    {
      unsigned long length= mysql_net_field_length(row);
      if (self->fields[column].flags & BINARY_FLAG)
        self->values[column]= PyBytes_FromStringAndSize((const char *)*row, (Py_ssize_t)length);
      else
        self->values[column]= PyUnicode_FromStringAndSize((const char *)*row, (Py_ssize_t)length);
 
      *row+= length;
      break;
    }
    case MYSQL_TYPE_GEOMETRY:
    case MYSQL_TYPE_STRING:
    case MYSQL_TYPE_VAR_STRING:
    case MYSQL_TYPE_JSON:
    case MYSQL_TYPE_VARCHAR:
    case MYSQL_TYPE_DECIMAL:
    case MYSQL_TYPE_NEWDECIMAL:
    case MYSQL_TYPE_SET:
    case MYSQL_TYPE_ENUM:
    {
      unsigned long length;
      length= mysql_net_field_length(row);
      self->values[column]= PyUnicode_FromStringAndSize((const char *)*row, (Py_ssize_t)length);
      *row+= length;
    }
    default:
      break;
  }
}

/* {{{ mariadb_get_column_info */
static uint8_t mariadb_get_column_info(PyObject *obj,
                                Mariadb_ParamInfo *paraminfo)
{
  if (!PyDateTimeAPI)
    PyDateTime_IMPORT;
  if (Py_TYPE(obj) == &PyLong_Type)
  {
    size_t b= _PyLong_NumBits(obj);
    if (b > paraminfo->bits)
      paraminfo->bits= b;
    if (_PyLong_Sign(obj) < 0)
      paraminfo->is_negative= 1;
    paraminfo->type= MYSQL_TYPE_LONGLONG;
    return 0;
  } else if (Py_TYPE(obj) == &PyFloat_Type)
  {
    paraminfo->type= MYSQL_TYPE_DOUBLE;
    return 0;
  } else if (Py_TYPE(obj) == &PyBytes_Type)
  {
    paraminfo->type= MYSQL_TYPE_LONG_BLOB;
    return 0;
  } else if (PyDate_CheckExact(obj))
  {
    paraminfo->type= MYSQL_TYPE_DATE;
    return 0;
  } else if (PyTime_CheckExact(obj))
  {
    paraminfo->type= MYSQL_TYPE_TIME;
    return 0;
  } else if (PyDateTime_CheckExact(obj))
  {
    paraminfo->type= MYSQL_TYPE_DATETIME;
    return 0;
  } else if (Py_TYPE(obj) == &PyUnicode_Type)
  {
    paraminfo->type= MYSQL_TYPE_VAR_STRING;
    return 0;
  } else if (obj == Py_None)
  {
    paraminfo->type= MYSQL_TYPE_NULL;
    return 0;
  }

  return 1;
}
/* }}} */

/*
uint8_t mariadb_get_data(PyObject *obj,
                                MYSQL_BIND *bind,
                                Mariadb_BindParam *param)
{
  PyDateTime_IMPORT;

  if (mariadb_get_field_type(obj, &param->field_type))
    return 1;

  switch (param->field_type) {
  case MYSQL_TYPE_TINY_INT:
    bind->is_unsigned= param->is_unsigned= (_PyLong_Sign(obj) >= 0);
    param->num.i8= (uint8_t)PyLong_AsLong(obj);
    bind->buffer= &param->num.i8;
    return 0;
  case MYSQL_TYPE_SHORT:
    bind->is_unsigned= param->is_unsigned= (_PyLong_Sign(obj) >= 0);
    param->num.i16= (uint16_t)PyLong_AsLong(obj);
    bind->buffer= &param->num.i16;
    return 0;
  case MYSQL_TYPE_LONG:
    bind->is_unsigned= param->is_unsigned= (_PyLong_Sign(obj) >= 0);
    param->num.i32= (uint32_t)PyLong_AsLong(obj);
    bind->buffer= &param->num.i32;
    return 0;
  case MYSQL_TYPE_LONGLONG:
    bind->is_unsigned= param->is_unsigned= (_PyLong_Sign(obj) >= 0);
    param->num.i64= PyLong_AsLongLong(obj);
    bind->buffer= &param->num.i64;
    return 0;
  case MYSQL_TYPE_DOUBLE:
    param->num.dbl= (double)PyFloat_AS_DOUBLE(obj);
    bind->buffer= &param->num.dbl;
    return 0;
  case MYSQL_TYPE_TINY_BLOB:
  case MYSQL_TYPE_MEDIUM_BLOB:
  case MYSQL_TYPE_BLOB:
  case MYSQL_TYPE_LONG_BLOB:
  {
    Py_ssize_t s= PyBytes_GET_SIZE(obj);
    bind->buffer_length= param->length= (unsigned long)s;
    bind->buffer= param->buffer= (void *) PyBytes_AS_STRING(obj);
    return 0;
  }
  case MYSQL_TYPE_DATE:
    bind->buffer= &param->tm;
    memset(&param->tm, 0, sizeof(MYSQL_TIME));
    param->tm.year= PyDateTime_GET_YEAR(obj);
    param->tm.month= PyDateTime_GET_MONTH(obj);
    param->tm.day= PyDateTime_GET_DAY(obj);
    param->tm.time_type= MYSQL_TIMESTAMP_DATE;
    return 0;
  case MYSQL_TYPE_TIME:
    bind->buffer= &param->tm;
    memset(&param->tm, 0, sizeof(MYSQL_TIME));
    param->tm.hour= PyDateTime_TIME_GET_HOUR(obj);
    param->tm.minute= PyDateTime_TIME_GET_MINUTE(obj);
    param->tm.second= PyDateTime_TIME_GET_SECOND(obj);
    param->tm.second_part= PyDateTime_TIME_GET_MICROSECOND(obj);
    param->tm.time_type= MYSQL_TIMESTAMP_TIME;
    return 0;
  case MYSQL_TYPE_DATETIME:
    bind->buffer= &param->tm;
    memset(&param->tm, 0, sizeof(MYSQL_TIME));
    param->tm.year= PyDateTime_GET_YEAR(obj);
    param->tm.month= PyDateTime_GET_MONTH(obj);
    param->tm.day= PyDateTime_GET_DAY(obj);
    param->tm.hour= PyDateTime_DATE_GET_HOUR(obj);
    param->tm.minute= PyDateTime_DATE_GET_MINUTE(obj);
    param->tm.second= PyDateTime_DATE_GET_SECOND(obj);
    param->tm.second_part= PyDateTime_DATE_GET_MICROSECOND(obj);
    param->tm.time_type= MYSQL_TIMESTAMP_DATETIME;
    return 0;
  case MYSQL_TYPE_VAR_STRING:
    bind->buffer= param->buffer= (void *)PyUnicode_AsUTF8AndSize(obj, (Py_ssize_t *)&param->length);
    bind->buffer_length= (unsigned long)param->length;
    return 0;
  case MYSQL_TYPE_NULL:
    return 0;
  }
  return 1;
}
*/

/* {{{ mariadb_get_parameter */
/**
  mariadb_get_parameter()
  @brief   Returns a bulk parameter which was passed to
           cursor.executemany() or a parameter which was
           passed to cursor.execute()

  @param   self[in]         Cursor
  @param   row_nr[in]       row number
  @paran   column_nr[in]    column number
  @param   paran[in][out]   bulk parameter pointer

  @return  0 on success, 1 on error

*/
static uint8_t mariadb_get_parameter(Mariadb_Cursor *self,
                                     uint8_t is_bulk,
                                     uint32_t row_nr,
                                     uint32_t column_nr,
                                     Mariadb_ParamValue *param)
{
  PyObject *row= NULL,
           *column= NULL;

  if (is_bulk)
  {
    /* check if row_nr and column_nr are in the range from
       0 to (value - 1) */
    if (row_nr > (self->array_size - 1) ||
        column_nr > (self->param_count - 1) ||
        row_nr < 0 ||
        column_nr < 0)
    {
      mariadb_throw_exception(self->stmt, Mariadb_DataError, 0,
      "Can't access data at row %d, column %d", row_nr + 1, column_nr + 1);
      return 1;
    }

    if (!(row= PyList_GetItem(self->data, row_nr)))
    {
      mariadb_throw_exception(self->stmt, Mariadb_DataError, 0,
      "Can't access row number %d", row_nr + 1);
      return 1;
    }
  }
  else
    row= self->data;

  if (!(column= PyTuple_GetItem(row, column_nr)))
  {
    mariadb_throw_exception(self->stmt, Mariadb_DataError, 0,
    "Can't access column number %d at row %d", column_nr + 1, row_nr + 1);
    return 1;
  }

  if (Py_TYPE(column) == &PyTuple_Type) /* (value, indicator) */
  {
    PyObject *indicator;
    PyObject *value;
    if (PyTuple_Size(column) != 2)
    {
      mariadb_throw_exception(self->stmt, Mariadb_DataError, 0,
      "Invalid tuple at row %d, column %d", row_nr, column_nr);
      return 1;
    }
    if (!MARIADB_FEATURE_SUPPORTED(self->stmt->mysql, 100206))
    {
      mariadb_throw_exception(NULL, Mariadb_DataError, 0,
      "MariaDB %s doesn't support indicator variables. Required version is 10.2.6 or newer", mysql_get_server_info(self->stmt->mysql));
      return 1;
    }
    value= PyTuple_GetItem(column, 0);
    indicator= PyTuple_GetItem(column, 1);
    if (Py_TYPE(indicator) != &PyLong_Type ||
       (PyLong_AsLong(indicator) < STMT_INDICATOR_NTS ||
        PyLong_AsLong(indicator) > STMT_INDICATOR_IGNORE_ROW))
    {
      mariadb_throw_exception(self->stmt, Mariadb_DataError, 0,
      "Invalid value for indicator at row %d, column %d", row_nr, column_nr);
      return 1;
    }
    param->indicator= PyLong_AsLong(indicator);
    param->value= value;
    return 0;
  }
  else
    param->value= column;
  if (param->value == Py_None)
    param->indicator= STMT_INDICATOR_NULL;
  else
    param->indicator= STMT_INDICATOR_NONE;
  return 0;
}
/* }}} */

/* {{{ mariadb_get_parameter_info */
static uint8_t mariadb_get_parameter_info(Mariadb_Cursor *self,
                                   MYSQL_BIND *param,
                                   uint32_t column_nr)
{
  uint32_t i, bits= 0;
  Mariadb_ParamValue paramvalue;
  Mariadb_ParamInfo pinfo;

  /* Assume unsigned */
  param->is_unsigned= 1;

  if (!self->array_size)
  {
    memset(&pinfo, 0, sizeof(Mariadb_ParamInfo));
    if (mariadb_get_parameter(self, 0, 0, column_nr, &paramvalue))
      return 1;
    if (mariadb_get_column_info(paramvalue.value, &pinfo))
    {
      mariadb_throw_exception(NULL, Mariadb_DataError, 0,
                              "Can't retrieve column information for paramter %s",
                              column_nr);
      return 1;
    }
    param->buffer_type= pinfo.type;
    bits= pinfo.bits;
  }

  for (i=0; i < self->array_size; i++)
  {
    if (mariadb_get_parameter(self, 1, i, column_nr, &paramvalue))
      return 1;
    memset(&pinfo, 0, sizeof(Mariadb_ParamInfo));
    if (mariadb_get_column_info(paramvalue.value, &pinfo))
    {
      mariadb_throw_exception(NULL, Mariadb_DataError, 1,
      "Invalid parameter type at row %d, column %d", i+1, column_nr + 1);
      return 1;
    }

    if (pinfo.is_negative)
      param->is_unsigned= 0;

    if (pinfo.type == MYSQL_TYPE_LONGLONG)
    {
      if (pinfo.bits > bits)
        bits= pinfo.bits;
    }


    if (!param->buffer_type ||
         param->buffer_type == MYSQL_TYPE_NULL)
      param->buffer_type= pinfo.type;
    else {
      /* except for NULL the parameter types must match */
      if (param->buffer_type != pinfo.type &&
          pinfo.type != MYSQL_TYPE_NULL)
      {
        if ((param->buffer_type == MYSQL_TYPE_TINY ||
             param->buffer_type == MYSQL_TYPE_SHORT ||
             param->buffer_type == MYSQL_TYPE_LONG) &&
             pinfo.type == MYSQL_TYPE_LONGLONG)
          break;
        mariadb_throw_exception(NULL, Mariadb_DataError, 1,
        "Invalid parameter type at row %d, column %d", i+1, column_nr + 1);
        return 1;
      }
    }
  }
  /* check the bit size for long types and set the appropiate
     field type */
  if (param->buffer_type == MYSQL_TYPE_LONGLONG)
  {
    if (bits <= 8)
      param->buffer_type= MYSQL_TYPE_TINY;
    else if (bits <= 16)
      param->buffer_type= MYSQL_TYPE_SHORT;
    else if (bits <= 32)
      param->buffer_type= MYSQL_TYPE_LONG;
    else if (bits <= 64)
      param->buffer_type= MYSQL_TYPE_LONGLONG;
    else
      param->buffer_type= MYSQL_TYPE_VAR_STRING;
  }
  return 0;
}
/* }}} */

/* {{{ mariadb_check_bulk_parameters */
uint8_t mariadb_check_bulk_parameters(Mariadb_Cursor *self,
                                      PyObject *data)
{
  uint32_t i;

  if (!(self->array_size= PyList_Size(data)))
  {
    mariadb_throw_exception(self->stmt, Mariadb_InterfaceError, 1, 
    "Empty parameter list. At least one row must be specified");
    return 1;
  }

  for (i=0; i < self->array_size; i++)
  {
    PyObject *obj= PyList_GetItem(data, i);
    if (Py_TYPE(obj) != &PyTuple_Type)
    {
      mariadb_throw_exception(NULL, Mariadb_DataError, 0,
      "Invalid parameter type in row %d. (Row data must be provided as tuple(s))", i+1);
      return 1;
    }

    if (!self->param_count && !self->is_prepared)
      self->param_count= PyTuple_Size(obj);

    if (!self->param_count ||
        self->param_count != PyTuple_Size(obj))
    {
      mariadb_throw_exception(self->stmt, Mariadb_DataError, 1, 
      "Invalid number of parameters in row %d", i+1);
      return 1;
    }
  }

  if (!self->is_prepared &&
      !(self->params= PyMem_RawCalloc(self->param_count, sizeof(MYSQL_BIND))))
  {
    mariadb_throw_exception(NULL, Mariadb_InterfaceError, 0,
                            "Not enough memory (tried to allocated %lld bytes)",
                            self->param_count * sizeof(MYSQL_BIND));
    goto error;
  }

  if (!(self->value= PyMem_RawCalloc(self->param_count, sizeof(Mariadb_ParamValue))))
  {
    mariadb_throw_exception(NULL, Mariadb_InterfaceError, 0,
                            "Not enough memory (tried to allocated %lld bytes)",
                            self->param_count * sizeof(Mariadb_ParamValue));
    goto error;
  }

  for (i=0; i < self->param_count; i++)
  {
    if (mariadb_get_parameter_info(self, &self->params[i], i))
      goto error;
  }
  return 0;
error:
  MARIADB_FREE_MEM(self->paraminfo);
  MARIADB_FREE_MEM(self->value);
  return 1;
}
/* }}} */

/* {{{ mariadb_check_execute_parameters */
uint8_t mariadb_check_execute_parameters(Mariadb_Cursor *self,
                                         PyObject *data)
{
  uint32_t i;
  if (!self->is_prepared)
    self->param_count= PyTuple_Size(data);

  if (!self->param_count)
  {
    mariadb_throw_exception(NULL, Mariadb_DataError, 0,
    "Invalid number of parameters");
    return 1;
  }

  if (!self->is_prepared &&
      !(self->params= PyMem_RawCalloc(self->param_count, sizeof(MYSQL_BIND))))
  {
    mariadb_throw_exception(NULL, Mariadb_InterfaceError, 0,
                            "Not enough memory (tried to allocated %lld bytes)",
                            self->param_count * sizeof(MYSQL_BIND));
    goto error;
  }

  if (!(self->value= PyMem_RawCalloc(self->param_count, sizeof(Mariadb_ParamValue))))
  {
    mariadb_throw_exception(NULL, Mariadb_InterfaceError, 0,
                            "Not enough memory (tried to allocated %lld bytes)",
                            self->param_count * sizeof(Mariadb_ParamValue));
    goto error;
  }

  for (i=0; i < self->param_count; i++)
  {
    if (mariadb_get_parameter_info(self, &self->params[i], i))
      goto error;
  }
  return 0;
error:
  MARIADB_FREE_MEM(self->paraminfo);
  MARIADB_FREE_MEM(self->value);
  return 1;
}
/* }}} */

/* {{{ mariadb_param_to_bind */
/**
  mariadb_param_to_bind()

  @brief Set the current value for the specified bind buffer

  @param bind[in]   bind structure
  @param value[in]  current column value

  @return 0 on succes, otherwise error
*/
static uint8_t mariadb_param_to_bind(MYSQL_BIND *bind,
                                     Mariadb_ParamValue *value)
{
  if (value->indicator)
    bind->u.indicator[0]= value->indicator;
  if (value->indicator > 0)
    return 0;

  if (IS_NUM(bind->buffer_type))
    bind->buffer= value->num;

  switch(bind->buffer_type)
  {
    case MYSQL_TYPE_TINY:
      if (bind->is_unsigned)
        value->num[0]= (uint8_t)PyLong_AsUnsignedLong(value->value);
      else
        value->num[0]= (int8_t)PyLong_AsLong(value->value);
      break;
    case MYSQL_TYPE_SHORT:
      if (bind->is_unsigned)
        *(uint16_t *)&value->num= (uint16_t)PyLong_AsUnsignedLong(value->value);
      else
        *(int16_t *)&value->num= (int16_t)PyLong_AsLong(value->value);
      break;
    case MYSQL_TYPE_LONG:
      if (bind->is_unsigned)
        *(uint32_t *)&value->num= (uint32_t)PyLong_AsUnsignedLong(value->value);
      else
        *(int32_t *)&value->num= (int32_t)PyLong_AsLong(value->value);
      break;
    case MYSQL_TYPE_LONGLONG:
      if (bind->is_unsigned)
        *(uint64_t *)value->num= (uint64_t)PyLong_AsUnsignedLongLong(value->value);
      else
        *(int64_t *)value->num= (int64_t)PyLong_AsLongLong(value->value);
      break;
    case MYSQL_TYPE_DOUBLE:
      *(double *)value->num= (double)PyFloat_AsDouble(value->value);
      break;
    case MYSQL_TYPE_LONG_BLOB:
      bind->buffer_length= (unsigned long)PyBytes_GET_SIZE(value->value);
      bind->buffer= (void *) PyBytes_AS_STRING(value->value);
      break;
    case MYSQL_TYPE_DATE:
    case MYSQL_TYPE_TIME:
    case MYSQL_TYPE_DATETIME:
      bind->buffer= &value->tm;
      memset(&value->tm, 0, sizeof(MYSQL_TIME));
      if (bind->buffer_type == MYSQL_TYPE_TIME ||
          bind->buffer_type == MYSQL_TYPE_DATETIME)
      {
        uint8_t is_time= PyTime_CheckExact(value->value);
        value->tm.hour= is_time ? PyDateTime_TIME_GET_HOUR(value->value) :
                                  PyDateTime_DATE_GET_HOUR(value->value);
        value->tm.minute= is_time ? PyDateTime_TIME_GET_MINUTE(value->value) :
                                  PyDateTime_DATE_GET_MINUTE(value->value);
        value->tm.second= is_time ? PyDateTime_TIME_GET_SECOND(value->value) :
                                  PyDateTime_DATE_GET_SECOND(value->value);
        value->tm.second_part= is_time ? PyDateTime_TIME_GET_MICROSECOND(value->value) :
                                  PyDateTime_DATE_GET_MICROSECOND(value->value);
        if (bind->buffer_type == MYSQL_TYPE_TIME)
        {
          value->tm.time_type= MYSQL_TIMESTAMP_TIME;
          break;
        }
      }
      if (bind->buffer_type == MYSQL_TYPE_DATE ||
          bind->buffer_type == MYSQL_TYPE_DATETIME)
      {
        value->tm.year= PyDateTime_GET_YEAR(value->value);
        value->tm.month= PyDateTime_GET_MONTH(value->value);
        value->tm.day= PyDateTime_GET_DAY(value->value);
        if (bind->buffer_type == MYSQL_TYPE_DATE)
          value->tm.time_type= MYSQL_TIMESTAMP_DATE;
        else
          value->tm.time_type= MYSQL_TIMESTAMP_DATETIME;
      }
      break;
    case MYSQL_TYPE_VAR_STRING:
    {
      Py_ssize_t len;
      bind->buffer= (void *)PyUnicode_AsUTF8AndSize(value->value, &len);
      bind->buffer_length= (unsigned long)len;
      break;
    }
    case MYSQL_TYPE_NULL:
      break;
    default:
      return 1;
  }
  return 0;
}
/* }}} */

/* {{{  mariadb_param_update */
/**
  mariadb_param_update()
  @brief   Callback function which updates the bind structure's buffer and
           length with data from the specified row number. This callback function
           must be registered via api function mysql_stmt_attr_set
           with STMT_ATTR_PARAM_CALLBACK option

  @param   data[in]      A pointer to a Mariadb_Cursor object which was passed
                         via mysql_stmt_attr_set before
           data[in][out] An array of bind structures
           data[in]      row number

  @return  0 on success, otherwise error (=1)
*/
uint8_t mariadb_param_update(void *data, MYSQL_BIND *bind, uint32_t row_nr)
{
  Mariadb_Cursor *self= (Mariadb_Cursor *)data;
  uint32_t i;

  if (!self)
    return 1;

  for (i=0; i < self->param_count; i++)
  {
    if (mariadb_get_parameter(self, (self->array_size > 0), row_nr, i, &self->value[i]))
      return 1;
    if (self->value[i].indicator)
      bind->u.indicator= &self->value[i].indicator;
    if (self->value[i].indicator < 1)
    {
      if (mariadb_param_to_bind(&bind[i], &self->value[i]))
      {
        return 1;
      }
    }
  }
  return 0;
}
/* }}} */
