***********
Basic usage
***********

.. sectionauthor:: Georg Richter <georg@mariadb.com>

Connecting
##########

The basic usage of MariaDB Connector/Python is similar to other database drivers which
implement |DBAPI|. 

Below is a simple example of a typical use of MariaDB Connector/Python

.. testsetup::

    import mariadb

    # connection parameters
    conn_params= {
        "user" : "example_user",
        "password" : "GHbe_Su3B8",
        "host" : "localhost",
        "database" : "test"
    }

    # Establish a connection
    connection= mariadb.connect(**conn_params)

    cursor= connection.cursor()
    cursor.execute("CREATE OR REPLACE TABLE `countries` ("
                   "`id` int(10) unsigned NOT NULL AUTO_INCREMENT,"
                   "`name` varchar(50) NOT NULL,"
                   "`country_code` char(3) NOT NULL,"
                   "`capital` varchar(50) DEFAULT NULL,"
                   "PRIMARY KEY (`id`),"
                   "KEY `name` (`name`),"
                   "KEY `capital` (`capital`)"
                   ") ENGINE=InnoDB DEFAULT CHARSET=latin1")

    cursor.close()
    connection.close()

.. testcode::

    import mariadb

    # connection parameters
    conn_params= {
        "user" : "example_user",
        "password" : "GHbe_Su3B8",
        "host" : "localhost",
        "database" : "test"
    }

    # Establish a connection
    connection= mariadb.connect(**conn_params)

    cursor= connection.cursor()

    # Populate countries table  with some data
    cursor.execute("INSERT INTO countries(name, country_code, capital) VALUES (?,?,?)",
                   ("Germany", "GER", "Berlin"))

    # retrieve data
    cursor.execute("SELECT name, country_code, capital FROM countries")

    # print content
    row= cursor.fetchone()
    print(*row, sep=' ')

    # free resources
    cursor.close()
    connection.close()

*Output*:

.. testoutput::

    Germany GER Berlin


Before MariaDB Connector/Python can be used, the MariaDB Connector/Python module must be 
imported.
Once the mariadb module is loaded, a connection to a database server will be established
using the method :func:`~mariadb.connect`.

In order to be able to communicate with the database server in the form of SQL statements, 
a cursor object must be created first. 

The method name cursor may be a little misleading: unlike a cursor in MariaDB that can only
read and return data, a cursor in Python can be used for all types of SQL statements.

After creating the table mytest, everything is ready to insert some data: Column values
that are to be inserted in the database are identified by place holders, the data is then passed in
the form of a tuple as a second parameter.

After creating and populating the table mytest the cursor will be used to retrieve the data.

At the end we free resources and close cursor and connection.

Passing parameters to SQL statements
####################################
As shown in previous example, passing parameters to SQL statements happens by using placeholders in the statement. By default
MariaDB Connector/Python uses a question mark as a placeholder, for compatibility reason also %s placeholders are supported.
Passing parameters is supported in methods :func:`~execute` and :func:`~executemany` of the cursor class.

Since |MCP| uses binary protocol, escaping strings or binary data like in other database drivers is not required.

.. testcode::

    import mariadb

    # connection parameters
    conn_params= {
        "user" : "example_user",
        "password" : "GHbe_Su3B8",
        "host" : "localhost",
        "database" : "test"
    }

    # Establish a connection
    connection= mariadb.connect(**conn_params)

    cursor= connection.cursor()

    sql= "INSERT INTO countries (name, country_code, capital) VALUES (?,?,?)"
    data= ("Germany", "GER", "Berlin")
    cursor.execute(sql, data)

    connection.commit()

    # delete last entry
    sql= "DELETE FROM countries WHERE country_code=?"
    data= ("GER",)
    cursor.execute(sql, data)

    connection.commit()

    cursor.close()
    connection.close()


  

Often there is a requirement to update, delete or insert multiple records. This could be done be using :func:`~execute` in
a loop, but much more effective is using the :func:`executemany` method, especially when using a MariaDB database server 10.2 and above, which supports a special "bulk" protocol. The executemany() works similar to execute(), but accepts data as a list of tuples:

.. testcode:: python

    import mariadb

    # connection parameters
    conn_params= {
        "user" : "example_user",
        "password" : "GHbe_Su3B8",
        "host" : "localhost",
        "database" : "test"
    }

    # Establish a connection
    connection= mariadb.connect(**conn_params)

    cursor= connection.cursor()
    sql= "INSERT INTO countries (name, country_code, capital) VALUES (?,?,?)"

    data= [("Ireland", "IE", "Dublin"),
           ("Italy", "IT", "Rome"),
           ("Malaysia", "MY", "Kuala Lumpur"),
           ("France", "FR", "Paris"),
           ("Iceland", "IS", "Reykjavik"),
           ("Nepal", "NP", "Kathmandu")]
    
    # insert data
    cursor.executemany(sql, data)

    # Since autocommit is off by default, we need to commit last transaction
    connection.commit()

    # Instead of 3 letter country-code, we inserted 2 letter country code, so
    # let's fix this mistake by updating data
    sql= "UPDATE countries SET country_code=? WHERE name=?"
    data= [("Ireland", "IRL"),
           ("Italy", "ITA"),
           ("Malaysia", "MYS"),
           ("France", "FRA"),
           ("Iceland", "ISL"),
           ("Nepal", "NPL")]
    cursor.executemany(sql, data)
  
    # Now let's delete all non European countries
    sql= "DELETE FROM countries WHERE name=?"
    data= [("Malaysia",), ("Nepal",)]
    cursor.executemany(sql, data)

    # by default autocommit is off, so we need to commit
    # our transactions
    connection.commit()

    # free resources
    cursor.close()
    connection.close()

When using executemany(), there are a few restrictions:
- All tuples must have the same types as in first tuple. E.g. the parameter [(1),(1.0)] or [(1),(None)] are invalid.
- Special values like None or column default value needs to be indicated by an indicator.

Using indicators
****************

In certain situations, for example when inserting default values or NULL, special indicators must be used.

.. testcode::

    import mariadb
    from mariadb.constants import *

    import mariadb

    # connection parameters
    conn_params= {
        "user" : "example_user",
        "password" : "GHbe_Su3B8",
        "host" : "localhost",
        "database" : "test"
    }

    # Establish a connection
    connection= mariadb.connect(**conn_params)

    cursor= connection.cursor()

    cursor.execute("DROP TABLE IF EXISTS cakes")
    cursor.execute("CREATE TABLE cakes(id int, cake varchar(100), price decimal(10,2) default 1.99)")

    sql= "INSERT INTO cakes (id, cake, price) VALUES (?,?,?)"
    data= [(1, "Cherry Cake", 2.10), (2, "Apple Cake", INDICATOR.DEFAULT)]
    cursor.executemany(sql, data)

Beside the default indicator which inserts the default value of 1.99, the following indicators are supported:
   * INDICATOR.IGNORE: Ignores the value (only update commands)
   * INDICATOR.NULL: Value is NULL
   * INDICATOR.IGNORE_ROW: Don't update or insert row

.. note::
  * Mixing different parameter styles is not supported and will raise an exception
  * The Python string operator % must not be used. The :func:`~execute` method accepts a tuple or list as second parameter.
  * Placeholders between quotation marks are interpreted as a string.
  * Parameters for :func:`~execute` needs to be passed as a tuple. If only one parameter will be passed, tuple needs to contain a comma at the end.
  * Parameters for :func:`~executemany` need to be passed as a list of tuples.

Supported Data types
--------------------

Several standard python types are converted into SQL types and returned as Python objects when a statement is executed.

.. list-table:: Supported Data Types
    :align: left
    :header-rows: 1

    * - Python type
      - SQL type
    * - None
      - NULL
    * - Bool
      - TINYINT
    * - Float, Double
      - DOUBLE
    * - Decimal
      - DECIMAL
    * - Long
      - TINYINT, SMALLINT, INT, BIGINT
    * - String
      - VARCHAR, VARSTRING, TEXT
    * - ByteArray, Bytes
      - TINYBLOB, MEDIUMBLOB, BLOB, LONGBLOB
    * - DateTime
      - DATETIME
    * - Date
      - DATE
    * - Time
      - TIME
    * - Timestamp
      - TIMESTAMP
