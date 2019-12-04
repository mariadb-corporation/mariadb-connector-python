/************************************************************************************
    Copyright (C) 2019 Georg Richter and MariaDB Corporation AB

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
PyDoc_STRVAR(
  pool_pool_name__doc__,
  "(read only)\n\n"
  "Returns the name of the connection pool"
);

PyDoc_STRVAR(
  connection_pool__doc__,
  "Class defining a pool of database connections"
);

PyDoc_STRVAR(
  pool_get_connection__doc__,
  "get_connection()\n"
  "--\n"
  "\n"
  "Returns a connection from the connection pool or raises a PoolError if\n"
  "a connection is not available"
);

PyDoc_STRVAR(
  pool_add_connection__doc__,
  "add_connection(connection)\n"
  "--\n"
  "\n"
  "Parameter:\n"
  "connection: mariadb connection object\n\n"
  "Adds a connection to the connection pool. In case the pool doesn't\n"
  "have a free slot or is not configured a PoolError exception will be raised."
);

PyDoc_STRVAR(
  pool_set_config__doc__,
  "set_config(configuration)\n"
  "--\n"
  "\n"
  "Parameter:\n"
  "configuration: dictionary\n\n"
  "Sets the connection configuration for the connection pool."
);

PyDoc_STRVAR(
  pool_pool_size__doc__,
  "(read only)\n\n"
  "Returns the size of the connection pool"
);

PyDoc_STRVAR(
  pool_max_size__doc__,
  "(read only)\n\n"
  "Returns the maximum allowed size of the connection pool"
);

PyDoc_STRVAR(
  pool_pool_reset_connection__doc__,
  "(read/write)\n\n"
  "If set to true, the connection will be resetted on both client and server side\n"
  "after .close() method was called"
);
