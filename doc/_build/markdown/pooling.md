# Connection pooling

A connection pool is a cache of connections to a database server where connections can be reused for future requests.
Since establishing a connection is resource-expensive and time-consuming, especially when used inside a middle tier
environment which maintains multiple connections and requires connections to be immediately available on the fly.

Especially for server-side web applications, a connection pool is the standard way to maintain a pool of database connections
which are reused across requests.

## Configuring and using a connection pool

The typical way for creating and using a connection pool is

1. Create (and configure) a connection pool
2. Obtain a connection from connection pool
3. Perform database operation(s)
4. Close the connection instance and return it to the connection pool.

### Creating a connection pool

When creating a connection pool, the following parameters have to be provided:

1. Connection pool specific parameters

- pool_name: The name of the pool, if not specified MariaDB Connector/Python will raise an exception.
- pool_size: The size of the pool, if not specified a default of 5 will be set.
- pool_reset_session: If set to True, the connection will be resetted before returned to the pool

#### Versionadded
Added in version 1.1.0.

- pool_invalidation_interval: specifies the validation interval in milliseconds after which the status of a connection requested from the pool is checked. The default values is 500 milliseconds, a value of 0 means that the status will always be checked.

1. Connection parameters

- In addition to the connection pool specific parameters initialization method of ConnectionPool Class accepts the same parameters as the connect() method of mariadb module.

*Example*:

```python
import mariadb

# connection parameters
conn_params= {
  "user" : "example_user",
  "password" : "GHbe_Su3B8",
  "database" : "test"
}

# create new pool
pool= mariadb.ConnectionPool(pool_name="myfirstpool", pool_size=5, **conn_params)
print("Pool size of '%s': %s" % (pool.pool_name, pool.pool_size))

# get a connection from pool
conn= pool.get_connection()

# print the default database for connection
print("Current database: %s" % conn.database)

# close connection and return it to pool
conn.close()
```

*Output*:

```none
Pool size of 'myfirstpool': 5
Current database: test
```
