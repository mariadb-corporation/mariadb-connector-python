***********
Basic usage
***********

.. sectionauthor:: Georg Richter <georg@mariadb.com>

Connecting
##########

The basic usage of MariaDB Connector/Python is similar to other database drivers which
implement |DBAPI|. 

Below is a simple example of a typical use of MariaDB Connector/Python

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

    # Create a database table
    cursor.execute("DROP TABLE IF EXISTS mytest")
    cursor.execute("CREATE TABLE mytest(id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,"
                   "first_name VARCHAR(100), last_name VARCHAR(100))")

    # Populate table with some data
    cursor.execute("INSERT INTO mytest(first_name, last_name) VALUES (?,?)",
                   ("Robert", "Redford"))

    # retrieve data
    cursor.execute("SELECT id, first_name, last_name FROM mytest")

    # print content
    row= cursor.fetchone()
    print(*row, sep=' ')

    # free resources
    cursor.close()
    connection.close()

*Output*:

.. testoutput::

    1 Robert Redford


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

    cursor.execute("DROP TABLE IF EXISTS books")
    cursor.execute("CREATE TABLE books(id int not null auto_increment primary key,\
                    book_name VARCHAR(100), author_name VARCHAR(50), price DECIMAL(10,2))")

    
    # insert multiple
    books= [("Dream of the Red Chamber", "Cao Xueqin", 13.90),  
            ("The Little Prince", "Antoine de Saint-Exupéry", 9.40)]
    sql= "INSERT INTO books (book_name, author_name, price) VALUES (?, ?, ?)"
    cursor.executemany(sql, books);

    # Since autocommit is off by default, we need to commit last transaction
    connection.commit()

    sql= "INSERT INTO books (book_name, author_name, price) VALUES (?, ?, ?)"
    data= ("The Lord of the Rings", "J.R.R. Tolkien", 18.99)
    cursor.execute(sql, data)

    # update
    sql= "UPDATE books SET price=? WHERE book_name=?"
    data= (14.90, "Dream of the Red Chamber")
    cursor.execute(sql, data)
  
    # delete
    sql= "DELETE FROM books WHERE id=?"
    data= (2,)   # Don't forget a comma at the end!
    cursor.execute(sql, data)

    # by default autocommit is off, so we need to commit
    # our transactions
    connection.commit()

    # free resources
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

    # update
    sql= "UPDATE books SET price=? WHERE book_name=?"
    data= [(14.90, "Dream of the Red Chamber"),
           (22.30, "The Master and Margarita"),
           (17.10, "And Then There Were None")]
    cursor.executemany(sql, data)
 
    # delete
    sql= "DELETE FROM books WHERE id=?"
    data= [(4034,),(12001,),(230,)]
    cursor.executemany(sql, data)
 
    #insert
    sql= "INSERT INTO books (book_name, author_name, price) VALUES (?, ?, ?)"
    data= [("The Lord of the Rings", "J.R.R. Tolkien", 18.99),
           ("Le Petit Prince", "Antoine de Saint-Exupéry", 22.40),
           ("Dream of the Red Chamber", "Cao Xueqin", 16.90),
           ("The Adventures of Pinocchio", "Carlo Collodi", 17.10)]
    cursor.executemany(sql, data)

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
