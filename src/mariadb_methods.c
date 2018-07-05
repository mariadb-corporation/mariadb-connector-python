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

PyObject *Mariadb_affected_rows(Mariadb_Connection *self)
{
  my_ulonglong rows= 0L;

  MARIADB_CHECK_CONNECTION(self);

  Py_BEGIN_ALLOW_THREADS
  rows= mysql_affected_rows(self->mysql);
  Py_END_ALLOW_THREADS

  /* We don't return -1 if last statement failed */
  if (rows == (my_ulonglong)-1)
    rows= 0;

  return PyLong_FromUnsignedLongLong(rows);
}

PyObject *Mariadb_commit(Mariadb_Connection *self)
{
  MARIADB_CHECK_CONNECTION(self);

  if (mysql_commit(self->mysql))
  {
    mariadb_throw_exception(self->mysql, Mariadb_InterfaceError, 0, NULL);
    return NULL;
  }
  Py_RETURN_NONE;
}

PyObject *Mariadb_rollback(Mariadb_Connection *self)
{
  MARIADB_CHECK_CONNECTION(self);

  if (mysql_rollback(self->mysql))
  {
    mariadb_throw_exception(self->mysql, Mariadb_InterfaceError, 0, NULL);
    return NULL;
  }
  Py_RETURN_NONE;
}


PyObject *Mariadb_autocommit(Mariadb_Connection *self,
                             PyObject *args)
{
  int autocommit;
  MARIADB_CHECK_CONNECTION(self);

  if (PyArg_ParseTuple(args, "p", &autocommit))
    return NULL;

  if (mysql_autocommit(self->mysql, autocommit))
  {
    mariadb_throw_exception(self->mysql, Mariadb_InterfaceError, 0, NULL);
    return NULL;
  }
  Py_RETURN_NONE;
}

/* DBAPIType methods */
PyObject *Mariadb_DBAPIType_Object(uint32_t type)
{
  PyObject *types= Py_BuildValue("(I)", (uint32_t)type);
  PyObject *number= PyObject_CallObject((PyObject *)&Mariadb_DBAPIType_Type,
                                        types);
  Py_DECREF(types);
  return number;
}
