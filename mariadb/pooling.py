#
# Copyright (C) 2020 Georg Richter and MariaDB Corporation AB

# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Library General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.

# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Library General Public License for more details.

# You should have received a copy of the GNU Library General Public
# License along with this library; if not see <http://www.gnu.org/licenses>
# or write to the Free Software Foundation, Inc.,
# 51 Franklin St., Fifth Floor, Boston, MA 02110, USA
"""MariaDB Connector/Python ConnectionPool class."""

import mariadb, sys
import time
import threading

MAX_POOL_SIZE = 32
"""Maximum number of connections per pool."""
MAX_POOL_NAME = 64
"""Maximum length of pool name"""
POOL_DEFAULT_SIZE = 5
"""Default size of Pool"""

class Pool(object):

    _queue = []
    _pool_name= None
    _pool_min_size= 0
    _pool_max_size= 0
    _reset_connection= True
    _LOCK_CONNECTION_POOL = threading.RLock()
    _confguration= None

    def __init__(self, pool_name= None, pool_min_size=2, pool_max_size = 5,
                 pool_size= 0, pool_reset_connection = True, **kwargs):
        """Initialization

        Initialize a new connection pool with maximum number of connections
        set to pool_nax_size value. pool_min_size specifies the number of
        connections which will be created automatically.
        Keywords arguments kwargs are configuration
        parameters for Connection class()."""


        # pool name is mandatory. We can't generate a pool name based
        # on connection parameters, since they could be empty = using
        # default values
        if not pool_name:
            raise mariadb.ProgrammingError("No pool name specified.")

        # check length of pool name
        if len(pool_name) > MAX_POOL_NAME:
            raise mariadb.ProgrammingError("The specified pool name " \
                "exceeds maximum length of %s characters" % MAX_POOL_NAME)

        # Check if a connection pool with the same name already exists
        if pool_name in mariadb._POOLS:
            raise mariadb.ProgrammingError("Connection pool '%s' " \
                "already exists." % pool_name)

        # MCP 1.0.X compatibility
        if pool_size:
            pool_max_size= pool_size
        if pool_min_size > pool_max_size:
            pool_min_size= pool_max_size

        # check if pool_size is valid
        if pool_max_size < 0 or pool_max_size > MAX_POOL_SIZE:
            raise mariadb.ProgrammingError(
                "Invalid pool size. Pool size must be higher than 0 " \
                "and lower than {0}".format(MAX_POOL_SIZE + 1))

        # save parameters
        self._reset_connection= pool_reset_connection
        self._pool_max_size= pool_max_size if pool_max_size else MAX_POOL_SIZE
        self._pool_name = pool_name
        self._pool_min_size= pool_min_size

        # check if we can establish a connection
        with self._LOCK_CONNECTION_POOL:
            # fill connection pool
            for i in range(0, self._pool_min_size):
                self._queue.append(mariadb.Connection(None, **kwargs))

        # connection parameters are ok, store configuration
        self._configuration = kwargs
        mariadb._CONNECTION_POOLS[self.__pool_args["name"]]= self

    def add_connection(self, connection):
        return

    def get_connection(self):
        """Return connection from pool."""

        now= time.monotonic()
        conn= None
        tdiff= 0

        with self._LOCK_CONNECTION_POOL:
           for c in self._queue:
               if not c._inuse:
                   t= now - c._lastused
                   if t > tdiff:
                       try:
                           # check if connection is alive
                           c.ping()
                       except:
                           # remove connection from pool
                           self.put_connection(self, c, True)
                           c= None
                       else:
                           conn= c
                           tdiff= t
           if not conn and len(self._queue) < self._pool_max_size:
               try:
                   conn= mariadb.Connection(None, self._configuration)
               except:
                   raise
               self._queue.append(conn)
           if conn:
               conn._inuse= 1
        return conn

    def put_connection(self, connection, close=False):

        with self._LOCK_CONNECTION_POOL:
            try:
                offset= self._queue.index(connection)
            except ValueError:
                raise mariadb.PoolError("Couldn't find connection in pool.")
            if not close and self._reset_connection:
                # try to reset the connection. If reset fails, we will close
                # the connection and remove it from pool
                try:
                    connection.reset()
                except:
                    close= True
            connection._inuse= 0
            if close:
                 self._queue.remove(connection)
                 connection.close()
        return None

    def close(self):
        with self._LOCK_CONNECTION_POOL:
            for conn in self._queue:
                conn._pool_name= None
                self._queue.remove(conn)
                conn.close()
            del mariadb._POOLS[self._pool_name]
        del self

    @property
    def pool_name(self):
        """Return the name of the pool."""
        return self._pool_name

    @property
    def pool_size(self):
        """Return the number of connections in pool"""
        return len(self._queue)
        
    @property
    def pool_max_size(self):
        """Return the number of connections in pool"""
        return MAX_POOL_SIZE
        
    @property
    def pool_reset_connection(self):
        """Return whether to reset a connection before reusing it."""
        return self._reset_connection
