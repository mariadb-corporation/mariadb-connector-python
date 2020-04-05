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
 ****************************************************************************/
#include "mariadb_python.h"
#include <datetime.h>

/*
   converts a Python date/time/datetime object to MYSQL_TIME
 */
static void
mariadb_pydate_to_tm(enum enum_field_types type,
                     PyObject *obj,
                     MYSQL_TIME *tm)
{
    if (!PyDateTimeAPI)
    {
        PyDateTime_IMPORT;
    }
    memset(tm, 0, sizeof(MYSQL_TIME));
    if (type == MYSQL_TYPE_TIME ||
            type == MYSQL_TYPE_DATETIME)
    {
        uint8_t is_time= PyTime_CheckExact(obj);
        tm->hour= is_time ? PyDateTime_TIME_GET_HOUR(obj) :
            PyDateTime_DATE_GET_HOUR(obj);
        tm->minute= is_time ? PyDateTime_TIME_GET_MINUTE(obj) :
            PyDateTime_DATE_GET_MINUTE(obj);
        tm->second= is_time ? PyDateTime_TIME_GET_SECOND(obj) :
            PyDateTime_DATE_GET_SECOND(obj);
        tm->second_part= is_time ? PyDateTime_TIME_GET_MICROSECOND(obj) :
            PyDateTime_DATE_GET_MICROSECOND(obj);
        if (type == MYSQL_TYPE_TIME)
        {
            tm->time_type= MYSQL_TIMESTAMP_TIME;
            return;
        }
    }
    if (type == MYSQL_TYPE_DATE ||
            type == MYSQL_TYPE_DATETIME)
    {
        tm->year= PyDateTime_GET_YEAR(obj);
        tm->month= PyDateTime_GET_MONTH(obj);
        tm->day= PyDateTime_GET_DAY(obj);
        if (type == MYSQL_TYPE_DATE)
            tm->time_type= MYSQL_TIMESTAMP_DATE;
        else
            tm->time_type= MYSQL_TIMESTAMP_DATETIME;
    }
}

/*
   Checks if the blob is a serialized (pickled) Python Object

   conditions:
     - First two bytes must be 0x8003
     - Last Byte must be 0x2E
     - unpickle must return success
*/
static PyObject *
mariadb_get_pickled(unsigned char *data, size_t length)
{
    PyObject *obj= NULL;

    if (length < 3)
    {
        return NULL;
    }

    if (*data == 0x80 && *(data +1) <= 0x04 && *(data + length - 1) == 0x2E)
    {
        PyObject *byte= PyBytes_FromStringAndSize((char *)data, length);
        obj= PyObject_CallMethod(Mrdb_Pickle, "loads", "O", byte);

        if (PyErr_Occurred())
            PyErr_Clear();
        Py_DECREF(byte);
    }
    return obj;
}

static unsigned long long my_strtoull(const char *str, size_t len, const char **end, int *err)
{
  unsigned long long val = 0;
  const char *p = str;
  const char *end_str = p + len;

  for (; p < end_str; p++)
  {
    if (*p < '0' || *p > '9')
      break;

    if (val > ULONG_LONG_MAX /10 || val*10 > ULONG_LONG_MAX - (*p - '0'))
    {
      *err = ERANGE;
      break;
    }
    val = val * 10 + *p -'0';
  }

  if (p == str)
    /* Did not parse anything.*/
    *err = ERANGE;

  *end = p;
  return val;
}

/*
  strtoui() version, that works for non-null terminated strings
*/
static unsigned int my_strtoui(const char *str, size_t len, const char **end, int *err)
{
  unsigned long long ull = my_strtoull(str, len, end, err);
  if (ull > UINT_MAX)
    *err = ERANGE;
  return (unsigned int)ull;
}

/*
  Parse time, in MySQL format.

  the input string needs is in form "hour:minute:second[.fraction]"
  hour, minute and second can have leading zeroes or not,
  they are not necessarily 2 chars.

  Hour must be < 838, minute < 60, second < 60
  Only 6 places of fraction are considered, the value is truncated after 6 places.
*/
static const unsigned int frac_mul[] = { 1000000,100000,10000,1000,100,10 };

static int parse_time(const char *str, size_t length, const char **end_ptr, MYSQL_TIME *tm)
{
  int err= 0;
  const char *p = str;
  const char *end = str + length;
  size_t frac_len;
  int ret=1;

  tm->hour = my_strtoui(p, end-p, &p, &err);
  if (err || tm->hour > 838 || p == end || *p != ':' )
    goto end;

  p++;
  tm->minute = my_strtoui(p, end-p, &p, &err);
  if (err || tm->minute > 59 || p == end || *p != ':')
    goto end;

  p++;
  tm->second = my_strtoui(p, end-p, &p, &err);
  if (err || tm->second > 59)
    goto end;

  ret = 0;
  tm->second_part = 0;

  if (p == end)
    goto end;

  /* Check for fractional part*/
  if (*p != '.')
    goto end;

  p++;
  frac_len = MIN(6,end-p);

  tm->second_part = my_strtoui(p, frac_len, &p, &err);
  if (err)
    goto end;

  if (frac_len < 6)
    tm->second_part *= frac_mul[frac_len];

  ret = 0;

  /* Consume whole fractional part, even after 6 digits.*/
  p += frac_len;
  while(p < *end_ptr)
  {
    if (*p < '0' || *p > '9')
      break;
    p++;
  }
end:
  *end_ptr = p;
  return ret;
}


/*
  Parse date, in MySQL format.

  The input string needs is in form "year-month-day"
  year, month and day can have leading zeroes or not,
  they do not have fixed length.

  Year must be < 10000, month < 12, day < 32

  Years with 2 digits, are coverted to values 1970-2069 according to 
  usual rules:

  00-69 is converted to 2000-2069.
  70-99 is converted to 1970-1999.
*/
static int parse_date(const char *str, size_t length, const char **end_ptr, MYSQL_TIME *tm)
{
  int err = 0;
  const char *p = str;
  const char *end = str + length;
  int ret = 1;

  tm->year = my_strtoui(p, end - p, &p, &err);
  if (err || tm->year > 9999 || p == end || *p != '-')
    goto end;

  if (p - str == 2) // 2-digit year
    tm->year += (tm->year >= 70) ? 1900 : 2000;

  p++;
  tm->month = my_strtoui(p,end -p, &p, &err);
  if (err || tm->month > 12 || p == end || *p != '-')
    goto end;

  p++;
  tm->day = my_strtoui(p, end -p , &p, &err);
  if (err || tm->day > 31)
    goto end;

  ret = 0;

end:
  *end_ptr = p;
  return ret;
}

int Py_str_to_TIME(const char *str, size_t length, MYSQL_TIME *tm)
{
  const char *p = str;
  const char *end = str + length;
  int is_time = 0;

  if (!p)
    goto error;

  while (p < end && isspace(*p))
    p++;
  while (p < end && isspace(end[-1]))
    end--;

  if (end -p < 5)
    goto error;

  if (*p == '-')
  {
    tm->neg = 1;
    /* Only TIME can't be negative.*/
    is_time = 1;
    p++;
  }
  else
  {
    int i;
    tm->neg = 0;
    /*
      Date parsing (in server) accepts leading zeroes, thus position of the delimiters
      is not fixed. Scan the string to find out what we need to parse.
    */
    for (i = 1; p + i < end; i++)
    {
      if(p[i] == '-' || p [i] == ':')
      {
        is_time = p[i] == ':';
        break;
      }
    }
  }

  if (is_time)
  {
    if (parse_time(p, end - p, &p, tm))
      goto error;
    
    tm->year = tm->month = tm->day = 0;
    tm->time_type = MYSQL_TIMESTAMP_TIME;
    return 0;
  }

  if (parse_date(p, end - p, &p, tm))
    goto error;

  if (p == end || p[0] != ' ')
  {
    tm->hour = tm->minute = tm->second = tm->second_part = 0;
    tm->time_type = MYSQL_TIMESTAMP_DATE;
    return 0;
  }

  /* Skip space. */
  p++;
  if (parse_time(p, end - p, &p, tm))
    goto error;

  /* In DATETIME, hours must be < 24.*/
  if (tm->hour > 23)
   goto error;

  tm->time_type = MYSQL_TIMESTAMP_DATETIME;
  return 0;

error:
  memset(tm, 0, sizeof(*tm));
  tm->time_type = MYSQL_TIMESTAMP_ERROR;
  return 1;
}
 
void
field_fetch_fromtext(MrdbCursor *self, char *data, unsigned int column)
{
    MYSQL_TIME tm;
    unsigned long *length;

    if (!PyDateTimeAPI)
    {
        PyDateTime_IMPORT;
    }

    if (!data)
    {
        Py_INCREF(Py_None);
        self->values[column]= Py_None;
        return;
    }

    length= mysql_fetch_lengths(self->result);

    switch (self->fields[column].type)
    {
        case MYSQL_TYPE_NULL:
            Py_INCREF(Py_None);
            self->values[column]= Py_None;
            break;
        case MYSQL_TYPE_TINY:
        case MYSQL_TYPE_SHORT:
        case MYSQL_TYPE_YEAR:
        case MYSQL_TYPE_INT24:
        case MYSQL_TYPE_LONG:
        case MYSQL_TYPE_LONGLONG:
            self->values[column]= PyLong_FromString(data, NULL, 0);
            break;
        case MYSQL_TYPE_FLOAT:  
        case MYSQL_TYPE_DOUBLE: 
        {
            double d= atof(data);
            self->values[column]= PyFloat_FromDouble(d);
            break;
        }
        case MYSQL_TYPE_TIME:
        case MYSQL_TYPE_DATE:
        case MYSQL_TYPE_DATETIME:
        case MYSQL_TYPE_TIMESTAMP:
            memset(&tm, 0, sizeof(MYSQL_TIME));
            Py_str_to_TIME(data, strlen(data), &tm);
            if (self->fields[column].type == MYSQL_TYPE_TIME)
            {
              self->values[column]= PyTime_FromTime((int)tm.hour, (int)tm.minute, 
                                      (int)tm.second, (int)tm.second_part);
            } else if (self->fields[column].type == MYSQL_TYPE_DATE)
            {
              self->values[column]= PyDate_FromDate(tm.year, tm.month, tm.day);
            } else 
            {
              self->values[column]= PyDateTime_FromDateAndTime(tm.year, tm.month, 
                         tm.day, tm.hour, tm.minute, tm.second, tm.second_part);
            }
            break;
        case MYSQL_TYPE_TINY_BLOB:
        case MYSQL_TYPE_MEDIUM_BLOB:
        case MYSQL_TYPE_BLOB:
        case MYSQL_TYPE_LONG_BLOB:
        case MYSQL_TYPE_GEOMETRY:
            if (length[column] > self->fields[column].max_length)
            {
                self->fields[column].max_length= length[column];
            }
            if (self->fields[column].flags & BINARY_FLAG)
            {
                if (!(self->values[column]= 
                   mariadb_get_pickled((unsigned char *)data, 
                                       (size_t)length[column])))
                {
                    self->values[column]= 
                       PyBytes_FromStringAndSize((const char *)data,
                                                 (Py_ssize_t)length[column]);
                }
            }
            else {
                self->values[column]= 
                    PyUnicode_FromStringAndSize((const char *)data, 
                                                (Py_ssize_t)length[column]);
            }
            break;
        case MYSQL_TYPE_NEWDECIMAL:
        {
            PyObject *decimal;

            decimal= PyObject_CallFunction(decimal_type, "s", (const char *)data);
            self->values[column]= decimal;
            break;
        }
        case MYSQL_TYPE_STRING:
        case MYSQL_TYPE_VAR_STRING:
        case MYSQL_TYPE_JSON:
        case MYSQL_TYPE_VARCHAR:
        case MYSQL_TYPE_DECIMAL:
        case MYSQL_TYPE_SET:
        case MYSQL_TYPE_ENUM:
        {
            unsigned long utf8len;

            self->values[column]=
                PyUnicode_FromStringAndSize((const char *)data,
                                            (Py_ssize_t)length[column]);
            utf8len= (unsigned long)PyUnicode_GET_LENGTH(self->values[column]);
            if (utf8len > self->fields[column].max_length)
            {
                self->fields[column].max_length= utf8len;
            }
            break;
        }
        default:
            break;
    } 
}

/* field_fetch_callback
   This function was previously registered with mysql_stmt_attr_set and
   STMT_ATTR_FIELD_FETCH_CALLBACK parameter. Instead of filling a bind 
   buffer MariaDB Connector/C sends raw data in row for the specified column.
   In case of a NULL value row ptr will be NULL.

   The cursor handle was also previously registered with mysql_stmt_attr_set
   and STMT_ATTR_USER_DATA parameter and will be passed in data variable.
*/

void
field_fetch_callback(void *data, unsigned int column, unsigned char **row)
{
    MrdbCursor *self= (MrdbCursor *)data;

    if (!PyDateTimeAPI)
    {
        PyDateTime_IMPORT;
    }

    if (!row)
    {
        Py_INCREF(Py_None);
        self->values[column]= Py_None;
        return;
    }
    switch(self->fields[column].type) {
        case MYSQL_TYPE_NULL:
            Py_INCREF(Py_None);
            self->values[column]= Py_None;
            break;
        case MYSQL_TYPE_TINY:
            self->values[column]= (self->fields[column].flags &
                 UNSIGNED_FLAG) ?
                PyLong_FromUnsignedLong((unsigned long)*row[0]) :
                PyLong_FromLong((long)*row[0]);
            *row+= 1;
            break;
        case MYSQL_TYPE_SHORT:
        case MYSQL_TYPE_YEAR:
            self->values[column]=
                (self->fields[column].flags & UNSIGNED_FLAG) ?
                PyLong_FromUnsignedLong((unsigned long)uint2korr(*row)) :
                PyLong_FromLong((long)sint2korr(*row));
            *row+= 2;
            break;
        case MYSQL_TYPE_INT24:
            self->values[column]= 
                (self->fields[column].flags & UNSIGNED_FLAG) ?
                PyLong_FromUnsignedLong((unsigned long)uint3korr(*row)) :
                PyLong_FromLong((long)sint3korr(*row));
            *row+= 4;
            break;
        case MYSQL_TYPE_LONG:
            self->values[column]=
                (self->fields[column].flags & UNSIGNED_FLAG) ?
                PyLong_FromUnsignedLong((unsigned long)uint4korr(*row)) :
                PyLong_FromLong((long)sint4korr(*row));
            *row+= 4;
            break;
        case MYSQL_TYPE_LONGLONG:
            {
                long long l= sint8korr(*row);
                self->values[column]=
                   (self->fields[column].flags & UNSIGNED_FLAG) ?
                    PyLong_FromUnsignedLongLong((unsigned long long)l) :
                    PyLong_FromLongLong(l);
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
                self->values[column]= PyDateTime_FromDateAndTime(year, month, 
                    day, hour, minute, second, second_part);
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
                self->values[column]= PyTime_FromTime(hour, minute, 
                                                      second, second_part);
                *row+= len;
                break;
            }
        case MYSQL_TYPE_TINY_BLOB:
        case MYSQL_TYPE_MEDIUM_BLOB:
        case MYSQL_TYPE_BLOB:
        case MYSQL_TYPE_LONG_BLOB:
            {
                unsigned long length= mysql_net_field_length(row);
                if (length > self->fields[column].max_length)
                    self->fields[column].max_length= length;
                if (self->fields[column].flags & BINARY_FLAG)
                {
                    if (!(self->values[column]= 
                        mariadb_get_pickled(*row, (size_t)length)))
                        self->values[column]= 
                            PyBytes_FromStringAndSize((const char *)*row, 
                                                       (Py_ssize_t)length);
                }
                else {
                    self->values[column]=
                        PyUnicode_FromStringAndSize((const char *)*row, 
                                                    (Py_ssize_t)length);
                }
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
                unsigned long utf8len;
                length= mysql_net_field_length(row);

                self->values[column]= 
                    PyUnicode_FromStringAndSize((const char *)*row,
                                                (Py_ssize_t)length);
                utf8len= 
                   (unsigned long)PyUnicode_GET_LENGTH(self->values[column]);
                if (utf8len > self->fields[column].max_length)
                    self->fields[column].max_length= utf8len;
                *row+= length;
            }
        default:
            break;
    }
}

/* 
   mariadb_get_column_info
   This function analyzes the Python object and calculates the corresponding
   MYSQL_TYPE, unsigned flag or NULL values and stores the information in
   MrdbParamInfo pointer.
 */
static uint8_t 
mariadb_get_column_info(PyObject *obj, MrdbParamInfo *paraminfo)
{
    if (!PyDateTimeAPI)
    {
        PyDateTime_IMPORT;
    }

    if (obj == NULL)
    {
        paraminfo->type= MYSQL_TYPE_BLOB;
        return 0;
    }

    if (Py_TYPE(obj) == &PyLong_Type)
    {
        size_t b= _PyLong_NumBits(obj);
        if (b > paraminfo->bits)
            paraminfo->bits= b;
        if (_PyLong_Sign(obj) < 0)
            paraminfo->is_negative= 1;
        paraminfo->type= MYSQL_TYPE_LONGLONG;
        return 0;
    } else if (Py_TYPE(obj) == &PyBool_Type) {
        paraminfo->type= MYSQL_TYPE_TINY;
        return 0;
    } else if (Py_TYPE(obj) == &PyFloat_Type) {
        paraminfo->type= MYSQL_TYPE_DOUBLE;
        return 0;
    } else if (Py_TYPE(obj) == &PyBytes_Type) {
        paraminfo->type= MYSQL_TYPE_LONG_BLOB;
        return 0;
    } else if (PyDate_CheckExact(obj)) {
        paraminfo->type= MYSQL_TYPE_DATE;
        return 0;
    } else if (PyTime_CheckExact(obj)) {
        paraminfo->type= MYSQL_TYPE_TIME;
        return 0;
    } else if (PyDateTime_CheckExact(obj)) {
        paraminfo->type= MYSQL_TYPE_DATETIME;
        return 0;
   } else if (Py_TYPE(obj) == &PyUnicode_Type) {
        paraminfo->type= MYSQL_TYPE_VAR_STRING;
        return 0;
    } else if (obj == Py_None) {
        paraminfo->type= MYSQL_TYPE_NULL;
        return 0;
    } else if (!strcmp(Py_TYPE(obj)->tp_name, "decimal.Decimal")) {
        /* CINPY-49: C-API has no correspondent data type for DECUMAL column type,
           so we need to convert decimal.Decimal Object to string during callback */
        paraminfo->type= MYSQL_TYPE_NEWDECIMAL;
        return 0;
    }
    else {
        /* no corresponding object, return error  */
        return 2;
    }

    return 1;
}

static PyObject *ListOrTuple_GetItem(PyObject *obj, Py_ssize_t index)
{
    if (Py_TYPE(obj) == &PyList_Type)
    {
        return PyList_GetItem(obj, index);
    } else if (Py_TYPE(obj) == &PyTuple_Type)
    {
        return PyTuple_GetItem(obj, index);
    }
    /* this should never happen, since the type was checked before */
    return NULL;
}

/* 

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
static uint8_t 
mariadb_get_parameter(MrdbCursor *self,
                      uint8_t is_bulk,
                      uint32_t row_nr,
                      uint32_t column_nr,
                      MrdbParamValue *param)
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
                    "Can't access data at row %d, column %d",
                     row_nr + 1, column_nr + 1);
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

    if (self->parser->paramstyle != PYFORMAT)
    {
        if (!(column= ListOrTuple_GetItem(row, column_nr)))
        {
            mariadb_throw_exception(self->stmt, Mariadb_DataError, 0,
                    "Can't access column number %d at row %d",
                     column_nr + 1, row_nr + 1);
            return 1;
        }
    } else
    {
        PyObject *key= PyUnicode_FromString(self->parser->keys[column_nr].str);
        if (!PyDict_Contains(row, key))
        {
            mariadb_throw_exception(self->stmt, Mariadb_DataError, 0,
                    "Can't find key '%s' in parameter data", 
                    self->parser->keys[column_nr]);
            return 1;
        }
        column= PyDict_GetItem(row, key);
    }

    /* check if an indicator was passed */
    if (MrdbIndicator_Check(column))
    {
        if (!MARIADB_FEATURE_SUPPORTED(self->stmt->mysql, 100206))
        {
            mariadb_throw_exception(NULL, Mariadb_DataError, 0,
                    "MariaDB %s doesn't support indicator variables. "\
                    "Required version is 10.2.6 or newer",
                    mysql_get_server_info(self->stmt->mysql));
            return 1;
        }
        param->indicator= (char)MrdbIndicator_AsLong(column);
        param->value= NULL; /* you can't have both indicator and value */
    } else if (column == Py_None) {
        if (MARIADB_FEATURE_SUPPORTED(self->stmt->mysql, 100206))
        {
            param->indicator= STMT_INDICATOR_NULL;
            param->value= NULL;
        }
    } 
    else {
        param->value= column;
        param->indicator= STMT_INDICATOR_NONE;
    }
    return 0;
}

/* 
   mariadb_get_parameter_info
   mariadb_get_parameter_info fills the MYSQL_BIND structure
   with correct field_types for the Python objects.

   In case of a bulk operation (executemany()) we will also optimize
   the field type (e.g. by checking maxbit size for a PyLong).
   If the types in this column differ we will return an error.
*/
static uint8_t 
mariadb_get_parameter_info(MrdbCursor *self,
                           MYSQL_BIND *param,
                           uint32_t column_nr)
{
    uint32_t i, bits= 0;
    MrdbParamValue paramvalue;
    MrdbParamInfo pinfo;

    /* Assume unsigned */
    param->is_unsigned= 1;

    if (!self->array_size)
    {
        uint8_t rc;
        memset(&pinfo, 0, sizeof(MrdbParamInfo));
        if (mariadb_get_parameter(self, 0, 0, column_nr, &paramvalue))
            return 1;
        if ((rc= mariadb_get_column_info(paramvalue.value, &pinfo)))
        {
            if (rc == 1)
            {
                mariadb_throw_exception(NULL, Mariadb_DataError, 0,
                    "Can't retrieve column information for parameter %d",
                     column_nr);
            }
            if (rc == 2)
            {
                mariadb_throw_exception(NULL, Mariadb_DataError, 0,
                    "Data type '%s' in column %d not supported in MariaDB Connector/Python",
                     Py_TYPE(paramvalue.value)->tp_name, column_nr);
            }
       
            return 1;
        }
        param->buffer_type= pinfo.type;
        bits= (uint32_t)pinfo.bits;
    }

    for (i=0; i < self->array_size; i++)
    {
        if (mariadb_get_parameter(self, 1, i, column_nr, &paramvalue))
            return 1;
        memset(&pinfo, 0, sizeof(MrdbParamInfo));
        if (mariadb_get_column_info(paramvalue.value, &pinfo))
        {
            mariadb_throw_exception(NULL, Mariadb_DataError, 1,
                    "Invalid parameter type at row %d, column %d",
                    i+1, column_nr + 1);
            return 1;
        }

        if (pinfo.is_negative)
            param->is_unsigned= 0;

        if (pinfo.type == MYSQL_TYPE_LONGLONG)
        {
            if (pinfo.bits > bits)
            {
                bits= (uint32_t)pinfo.bits;
            }
        }


        if (!param->buffer_type ||
                param->buffer_type == MYSQL_TYPE_NULL)
        {
            param->buffer_type= pinfo.type;
        }
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
                        "Invalid parameter type at row %d, column %d",
                        i+1, column_nr + 1);
                return 1;
            }
        }
    }
    /* check the bit size for long types and set the appropiate
       field type */
    if (param->buffer_type == MYSQL_TYPE_LONGLONG)
    {
        if (bits <= 8)
        {
            param->buffer_type= MYSQL_TYPE_TINY;
        }
        else if (bits <= 16) {
            param->buffer_type= MYSQL_TYPE_SHORT;
        }
        else if (bits <= 32) {
            param->buffer_type= MYSQL_TYPE_LONG;
        }
        else if (bits <= 64) {
            param->buffer_type= MYSQL_TYPE_LONGLONG;
        }
        else {
            param->buffer_type= MYSQL_TYPE_VAR_STRING;
        }
    }
    return 0;
}

static Py_ssize_t ListOrTuple_Size(PyObject *obj)
{
    if (Py_TYPE(obj) == &PyList_Type)
    {
        return PyList_Size(obj);
    } else if (Py_TYPE(obj) == &PyTuple_Type) 
    {
        return PyTuple_Size(obj);
    }
    /* this should never happen, since the type was checked before */
    return 0;
}

/* mariadb_check_bulk_parameters
   This function validates the specified bulk parameters and
   translates the field types to MYSQL_TYPE_*.
 */
uint8_t 
mariadb_check_bulk_parameters(MrdbCursor *self,
                              PyObject *data)
{
    uint32_t i;

    if (!(self->array_size= (uint32_t)PyList_Size(data)))
    {
        mariadb_throw_exception(self->stmt, Mariadb_InterfaceError, 1, 
                "Empty parameter list. At least one row must be specified");
        return 1;
    }

    for (i=0; i < self->array_size; i++)
    {
        PyObject *obj= PyList_GetItem(data, i);
        if (self->parser->paramstyle != PYFORMAT &&
                (Py_TYPE(obj) != &PyTuple_Type &&
                 Py_TYPE(obj) != &PyList_Type))
        {
            mariadb_throw_exception(NULL, Mariadb_DataError, 0,
                    "Invalid parameter type in row %d. "\
                    " (Row data must be provided as tuple(s))", i+1);
            return 1;
        }
        if (self->parser->paramstyle == PYFORMAT &&
                Py_TYPE(obj) != &PyDict_Type)
        {
            mariadb_throw_exception(NULL, Mariadb_DataError, 0,
                    "Invalid parameter type in row %d. "\
                    " (Row data must be provided as dict)", i+1);
            return 1;
        }

        if (!self->param_count && !self->is_prepared)
            self->param_count= self->parser->param_count;

        if (!self->param_count ||
                (self->parser->paramstyle != PYFORMAT && 
                 self->param_count != ListOrTuple_Size(obj)))
        {
            mariadb_throw_exception(self->stmt, Mariadb_DataError, 1, 
                    "Invalid number of parameters in row %d", i+1);
            return 1;
        }
    }

    if (!self->is_prepared &&
            !(self->params= PyMem_RawCalloc(self->param_count,
                                            sizeof(MYSQL_BIND))))
    {
        mariadb_throw_exception(NULL, Mariadb_InterfaceError, 0,
                "Not enough memory (tried to allocated %lld bytes)",
                self->param_count * sizeof(MYSQL_BIND));
        goto error;
    }

    if (!(self->value= PyMem_RawCalloc(self->param_count, 
                                       sizeof(MrdbParamValue))))
    {
        mariadb_throw_exception(NULL, Mariadb_InterfaceError, 0,
                "Not enough memory (tried to allocated %lld bytes)",
                self->param_count * sizeof(MrdbParamValue));
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

uint8_t
mariadb_check_execute_parameters(MrdbCursor *self,
                                 PyObject *data)
{
    uint32_t i;
    if (!self->param_count)
    {
        self->param_count= self->parser->param_count;
    }

    if (!self->param_count)
    {
        mariadb_throw_exception(NULL, Mariadb_DataError, 0,
                "Invalid number of parameters");
        return 1;
    }

    if (!self->params &&
            !(self->params= PyMem_RawCalloc(self->param_count, sizeof(MYSQL_BIND))))
    {
        mariadb_throw_exception(NULL, Mariadb_InterfaceError, 0,
                "Not enough memory (tried to allocated %lld bytes)",
                self->param_count * sizeof(MYSQL_BIND));
        goto error;
    }

    if (!(self->value= PyMem_RawCalloc(self->param_count, sizeof(MrdbParamValue))))
    {
        mariadb_throw_exception(NULL, Mariadb_InterfaceError, 0,
                "Not enough memory (tried to allocated %lld bytes)",
                self->param_count * sizeof(MrdbParamValue));
        goto error;
    }

    for (i=0; i < self->param_count; i++)
    {
        if (mariadb_get_parameter_info(self, &self->params[i], i))
        {
            goto error;
        }
    }
    return 0;
error:
    MARIADB_FREE_MEM(self->paraminfo);
    MARIADB_FREE_MEM(self->value);
    return 1;
}

/* 
  mariadb_param_to_bind()

  @brief Set the current value for the specified bind buffer

  @param bind[in]   bind structure
  @param value[in]  current column value

  @return 0 on succes, otherwise error
 */
static uint8_t 
mariadb_param_to_bind(MYSQL_BIND *bind,
                      MrdbParamValue *value)
{
    if (value->indicator > 0)
    {
        bind->u.indicator[0]= value->indicator;
        return 0;
    }

    if (IS_NUM(bind->buffer_type))
        bind->buffer= value->num;

    switch(bind->buffer_type)
    {
        case MYSQL_TYPE_TINY:
            if (bind->is_unsigned)
            {
                value->num[0]= (uint8_t)PyLong_AsUnsignedLong(value->value);
            }
            else {
                value->num[0]= (int8_t)PyLong_AsLong(value->value);
            }
            break;
        case MYSQL_TYPE_SHORT:
            if (bind->is_unsigned)
            {
                *(uint16_t *)&value->num= (uint16_t)PyLong_AsUnsignedLong(value->value);
            }
            else {
                *(int16_t *)&value->num= (int16_t)PyLong_AsLong(value->value);
            }
            break;
        case MYSQL_TYPE_LONG:
            if (bind->is_unsigned)
            {
                *(uint32_t *)&value->num= (uint32_t)PyLong_AsUnsignedLong(value->value);
            }
            else {
                *(int32_t *)&value->num= (int32_t)PyLong_AsLong(value->value);
            }
            break;
        case MYSQL_TYPE_LONGLONG:
            if (bind->is_unsigned)
            {
                *(uint64_t *)value->num= (uint64_t)PyLong_AsUnsignedLongLong(value->value);
            }
            else {
                *(int64_t *)value->num= (int64_t)PyLong_AsLongLong(value->value);
            }
            break;
        case MYSQL_TYPE_DOUBLE:
            *(double *)value->num= (double)PyFloat_AsDouble(value->value);
            break;
        case MYSQL_TYPE_LONG_BLOB:
            if (Py_TYPE(value->value) != &PyBytes_Type)
            {
                PyObject *dump= NULL;
                dump= PyObject_CallMethod(Mrdb_Pickle, "dumps", "O", value->value);
                bind->buffer_length= (unsigned long)PyBytes_GET_SIZE(dump);
                bind->buffer= (void *) PyBytes_AS_STRING(dump);
            } else {
                bind->buffer_length= (unsigned long)PyBytes_GET_SIZE(value->value);
                bind->buffer= (void *) PyBytes_AS_STRING(value->value);
            }
            break;
        case MYSQL_TYPE_DATE:
        case MYSQL_TYPE_TIME:
        case MYSQL_TYPE_DATETIME:
            bind->buffer= &value->tm;
            mariadb_pydate_to_tm(bind->buffer_type, value->value, &value->tm);
            break;
        case MYSQL_TYPE_NEWDECIMAL:
            {
                Py_ssize_t len;
                PyObject *obj= PyObject_Str(value->value);
                bind->buffer= (void *)PyUnicode_AsUTF8AndSize(obj, &len);
                bind->buffer_length= (unsigned long)len;
                Py_DECREF(obj);
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

/* 
  mariadb_param_update()
  @brief   Callback function which updates the bind structure's buffer and
  length with data from the specified row number. This callback function
  must be registered via api function mysql_stmt_attr_set
  with STMT_ATTR_PARAM_CALLBACK option

  @param   data[in]      A pointer to a MrdbCursor object which was passed
  via mysql_stmt_attr_set before
  data[in][out] An array of bind structures
  data[in]      row number

  @return  0 on success, otherwise error (=1)
*/
uint8_t
mariadb_param_update(void *data, MYSQL_BIND *bind, uint32_t row_nr)
{
    MrdbCursor *self= (MrdbCursor *)data;
    uint32_t i;

    if (!self)
    {
        return 1;
    }

    for (i=0; i < self->param_count; i++)
    {
        if (mariadb_get_parameter(self, (self->array_size > 0), 
                                 row_nr, i, &self->value[i]))
        {
            return 1;
        }
        if (self->value[i].indicator)
        {
            bind[i].u.indicator= &self->value[i].indicator;
        }
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

#ifdef _WIN32

/* windows equivalent for clock_gettime.
   Code based on https://stackoverflow.com/questions/5404277/porting-clock-gettime-to-windows
 */

static uint8_t g_first_time = 1;
static LARGE_INTEGER g_counts_per_sec;

int clock_gettime(int dummy, struct timespec *ct)
{
    LARGE_INTEGER count;

    if (g_first_time)
    {
        g_first_time = 0;

        if (0 == QueryPerformanceFrequency(&g_counts_per_sec))
        {
            g_counts_per_sec.QuadPart = 0;
        }
    }

    if ((NULL == ct) || (g_counts_per_sec.QuadPart <= 0) ||
            (0 == QueryPerformanceCounter(&count)))
    {
        return -1;
    }

    ct->tv_sec = count.QuadPart / g_counts_per_sec.QuadPart;
    ct->tv_nsec = ((count.QuadPart % g_counts_per_sec.QuadPart) * 1E09) / g_counts_per_sec.QuadPart;

    return 0;
}

#endif
