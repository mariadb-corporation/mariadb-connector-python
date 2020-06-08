***********
Basic usage
***********

.. sectionauthor:: Georg Richter <georg@mariadb.com>

Connecting
##########

The basic usage of MariaDB Connector/Python is similiar to other database drivers which
implement |DBAPI|. 

Below is a simple example of a typical use of MariaDB Connector/Python

.. literalinclude:: ../examples/basic01.py
   :language: python
   :linenos:


Before MariaDB Connector/Python can be used, the MariaDB Connector/Python module must be 
imported (line #2)
Once the mariadb module is loaded, a connection to a database server will be established
using the method :func:`~mariadb.connect` (line #5).

In order to be able to communicate with the database server in the form of SQL statements, 
a cursor object must be created first (line #7). 

The method name cursor may be a little misleading: unlike a cursor in MariaDB that can only
read and return data, a cursor in Python can be used for all types of SQL statements.

After creating the table mytest, everything is ready to insert some data (line #16): Column values
that are to be inserted in the database are identified by place holders, the data is then passed in
the form of a tuple as a second parameter (line #16).

After creating and populating the table mytest the cursor will be used to retrieve the data (line #20 - line#23).

Passing parameters to SQL statements
####################################
As shown in previous example, passing parameters to SQL statements happens by using placeholders in the statement. By default
MariaDB Connector/Python uses a question mark as a placeholder, for compatibility reason also %s placeholders are supported. Passing
parameters is supported in methods :func:`~execute` and :func:`~executemany` of the cursor class.

Since |MCP| uses binary protocol, escaping strings or binary data like in other database drivers is not required.

.. code-block:: python
   :linenos:

   # update
   sql= "UPDATE books SET price=? WHERE book_name=?"
   data= (14.90, "Dream of the Red Chamber")
   cursor.execute(sql, data)
 
   # delete
   sql= "DELETE FROM books WHERE id=?"
   data= (4034,)   # Don't forget a comma at the end!
   cursor.execute(sql, data)
 
 
   # insert
   sql= "INSERT INTO books (book_name, author_name, price) VALUES (?, ?, ?)"
   data= ("The Lord of the Rings", "J.R.R. Tolkien", 18.99)

Often there is a requirement to update, delete or insert multiple records. This could be done be using :func:`~execute` in
a loop, but much more effective is using the :func:`executemany` method, especially when using a MariaDB database server 10.2 and above, which supports a special "bulk" protocol. The executemany() works similiar to execute(), but accepts data as a list of tuples:

.. code-block:: python
   :linenos:

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

.. code-block:: python
   :linenos:

   cursor.execute("CREATE TABLE cakes(id int, cake varchar(100), price decimal(10,2) default 1.99)")

   sql= "INSERT INTO cakes (id, cake, price) VALUES (?,?)"
   data= [(1, "Cherry Cake", 2.10), (2, "Apple Cake", mariadb.indicator_default)]
   cursor.executemany(sql, data)

Beside the default indicator which inserts the default value of 1.99, the following indicators are supported:
   * indicator_ignore: Ignores the value (only update commands)
   * indicator_null: Value is NULL
   * indicator_row: Don't update or insert row

.. note::
  * Mixing different parameter styles is not supported and will raise an exception
  * The Python string operator % must not be used. The :func:`~execute` method accepts a tuple or list as second parameter.
  * Placeholders between quotation marks are interpreted as a string.
  * Parameters for :func:`~execute` needs to be passed as a tuple. If only one parameter will be passed, tuple needs to contain a comma at the end.
  * Parameters for :func:`~executemany` need to be passed as a list of tuples.

Supported Data types
--------------------




