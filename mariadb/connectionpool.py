import mariadb, sys
import _thread, time

MAX_POOL_SIZE = 64
POOL_IDLE_TIMEOUT = 1800

class ConnectionPool(object):
    """
    Class defining a pool of database connections

    MariaDB Connector/Python supports simple connection pooling.
    A connection pool holds a number of open connections and handles
    thread safety when providing connections to threads.

    The size of a connection pool is configurable at creation time, 
    but cannot be changed afterwards. The maximum size of a connection
    pool is limited to 64 connections.
    """


    def __init__(self, *args, **kwargs):
        """
        Creates a connetion pool class

        :param str pool_name:
            Name of connection pool

        :param int pool_size:
            Size of pool. If not specified default value of 5 will be used.
            Maximum allowed number is 64.

        :param bool pool_reset_connection:
            Will reset the connection before returning it to the pool.
            Default value is True.
        """
        self._connections = []
        self._pool_args = {}
        self._conn_args = {}
        self._lock_pool = _thread.RLock()

        key_words= ["pool_name", "pool_size", "pool_reset_connection"]

        # check if pool_name was provided
        if kwargs and "pool_name" in kwargs:

            # check if pool_name already exists
            if kwargs["pool_name"] in mariadb._CONNECTION_POOLS:
                raise mariadb.ProgrammingError("Pool '%s' already exists" \
                                               % kwargs["pool_name"])
        else:
            raise mariadb.ProgrammingError("No pool name specified")

        # save pool keyword arguments
        self._pool_args["name"]= kwargs.get("pool_name")
        self._pool_args["size"]= kwargs.get("pool_size", 5);
        self._pool_args["reset_connection"]= \
            kwargs.get("pool_reset_connection", True)

        # validate pool size (must be in range between 1 and MAX_POOL_SIZE)
        if not (0 < self._pool_args["size"] <= MAX_POOL_SIZE):
            raise mariadb.ProgrammError("Pool size must be in range of "\
                                        "1 and %s" % MAX_POOL_SIZE)

        # store pool and connection arguments
        self._conn_args= kwargs.copy()
        for key in key_words:
            if key in self._conn_args:
                del self._conn_args[key]

        if len(self._conn_args) > 0:
            with self._lock_pool:
                # fill connection pool
                for i in range(0, self._pool_args["size"]):
                    try:
                        connection= mariadb.Connection(**self._conn_args)
                    except:
                        # if an error occured, close all connections and raise exception
                        for j in range(0, len(self._connections)):
                            try:
                                self._connections[j].close()
                            except:
                                # connect failed, so we are not interested in errors
                                # from close() method
                                pass
                            del self._connections[j]
                        raise
                    self.add_connection(connection)

        # store connection pool in _CONNECTION_POOLS 
        mariadb._CONNECTION_POOLS[self._pool_args["name"]]= self

    def add_connection(self, connection= None):
        """
        Adds a connection object to the connection pool.

        In case that the pool doesn’t have a free slot or is not configured
        a PoolError exception will be raised.
        """

        if not self._conn_args:
            raise mariadb.PoolError("Couldn't get configuration for pool %s" % \
                self._pool_args["name"])

        if connection is not None and \
            not isinstance(connection, mariadb.connections.Connection):
            raise TypeError("Passed parameter is not a connection object")

        if connection == None and len(self._conn_args) == 0:
            raise mariadb.PoolError("Can't get configuration for pool %s" % \
                self._pool_args["name"])

        if len(self._connections) >= self._pool_args["size"]:
            raise mariadb.PoolError("Can't add connection to pool %s: "
                "No free slot available (%s)." % (self._pool_args["name"], len(self._connections)))

        with self._lock_pool:
            if connection is None:
                connection= mariadb.Connection(**self._conn_args)
            
            connection._Connection__pool= self
            connection._Connection__in_use= 0
            connection._Connection__last_used= time.monotonic()
            self._connections.append(connection)
            

    def get_connection(self):
        """
        Returns a connection from the connection pool or raises a PoolError
        exception if a connection is not available.
        """
        
        now= time.monotonic()
        conn= None
        timediff= 0

        with self._lock_pool:
            for i in range(0, len(self._connections)):
                if not self._connections[i]._Connection__in_use:
                    try:
                        self._connections[i].ping()
                    except:
                        continue
                    t = now - self._connections[i]._Connection__last_used
                    if t > timediff:
                        conn= self._connections[i]
                        timediff = t

            if conn:
                conn._Connection__in_use= 1
        return conn

    def _close_connection(self, connection):
        """
        Returns connection to the pool. Internally used
        by connection object.
        """

        with self._lock_pool:
            if self.pool_args["reset_connection"]:
                connection.reset()
            connection._Connection__in_use= 0
            connection._Connection__last_used= time.monotonic()

    def set_config(self, **kwargs):
        """
        :param dict configuration
            configuration settings for pooled connection

        Sets the connection configuration for the connection pool.
        For valid connection arguments check the mariadb.connect() method.
        
        Note: This method doesn't create connections in the pool.
        To fill the pool one has to use add_connection() ḿethod.
        """

        self._conn_args= kwargs;

    def close(self):
        """Closes connection pool and all connections."""
        try:
            for c in self._connections:
                c._Connection__pool= None
                c.close()
        finally:
            self._connections= None
            del mariadb._CONNECTION_POOLS[self._pool_args["name"]]

    @property
    def pool_name(self):
        """Returns the name of the connection pool."""

        return self._pool_args["name"]

    @property
    def pool_size(self):
        """Returns the size of the connection pool."""

        return self._pool_args["size"]

    @property
    def max_size(self):
        "Returns the maximum size for connection pools."""

        return MAX_POOL_SIZE

    @property
    def connection_count(self):
        "Returns the number of connections in connection pool."""

        return self._connections

    @property
    def pool_reset_connection(self):
        """
        If set to true, the connection will be reset on both client and server side\n
        after .close() method was called
        """
        return self._pool_args["reset_connection"]

    @pool_reset_connection.setter
    def pool_reset_connection(self, reset):
        self._pool_args["reset_connection"]= reset
