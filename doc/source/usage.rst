.. _usage:

Basic module usage
==================

.. sectionauthor:: Georg Richter <georg@mariadb.com>

Connecting
----------

Connections to a MariaDB or compatible server are created using the :func:`~mariadb.connect` method.
This method returns an instance of the :class:`~mariadb.connection` class.

To connect to MariaDB Platform, use the connect() function with the relevant attributes.

Example:

.. code-block:: python 

  # Module Imports
  import mariadb
  import sys
  
  # Instantiate Connection
  try:
     conn = mariadb.connect(
        user="admin",
        password="admin_pwd",
        host="localhost",
        port=3306)
     except mariadb.Error as e:
        print(f"Error connecting to MariaDB Platform: {e}")
        sys.exit(1)

Here, the mariadb package is imported with the sys package (to handle the exit in the event that the connection fails). The connection attributes are passed as keyword arguments to the connect() function. The connect() function returns a connection object, assigned to the conn variable.

.. note:: Instantiating the connection class creates a single connection to MariaDB Platform. Applications that require multiple connections may benefit from pooling connections.

Closing Connections
-------------------
MariaDB Connector/Python closes the connection as part of the object destruction method when it leaves the scope, such as when the program exits or the current function returns a value other than the connection instance.

To explicitly close the connection to MariaDB Platform, call the close() method on the connection:

.. code-block:: python 

  # Close Connection
  conn.close()

Basic Operations
----------------

Instances of the connection class handle the connection between your Python application and MariaDB Platform. To interact with and manage databases on MariaDB Platform, you must instantiate a cursor in your code.

.. code-block:: python 

  # Instantiate Cursor
  cur = conn.cursor()

The cursor provides methods for interacting with data from Python code. The cursor provides two methods for executing SQL code:

- :func:`execute` -- Executes a single SQL statement.
- :func:`executemany` -- Executes the given SQL statement for each tuple in a list.

Adding Data
***********

MariaDB Connector/Python adds data to the database using the :func:`execute` or :func:`executemany` methods with INSERT statements.

.. code-block:: python

  # Adds contact
  def add_contact(cur, first_name, last_name, email):
     """Adds the given contact to the contacts table"""

  cur.execute("INSERT INTO users.contacts(first_name, last_name, email) VALUES (?, ?, ?)",
        (first_name, last_name, email))

Here, the execute() method is called on the cursor to add contacts to a user database. Note that the method passes in the values through a tuple, with a question mark ? marking each entry.

To add multiple rows together, you can use the :func:`executemany` method:

.. code-block:: python

  # Add Multiple Rows
  def add_multiple_contacts(cur, data):
     """Adds multiple contacts to database from given data"""

     cur.executemany("INSERT INTO users.contacts(first_name, last_name, email) VALUES (?, ?, ?)",
        data)

  # Initialize Data
  data = [
     ("Howard", "Lovecraft", "hp.lovecraft@example.net"),
     ("Flannery", "O'Connor", "flan.oconnor@example.com"),
     ("Walker", "Percy", "w.percy@example.edu")
  ]

  add_multiple_contacts(cur, data)

Here, for each tuple in the data list, the cursor executes an INSERT statement.

Retrieving Data
***************

MariaDB Connector/Python retrieves data using the :func:`execute` method with a SELECT statement. The cursor stores the results of queries internally and can be retrieve using a for loop, or fetchall() and related methods.

For instance, retrieving the contacts list from the database, this function formats the first name, last name, and email into a line and then prints the results to stdout:

.. code-block:: python

  # Print List of Contacts
  def print_contacts(cur):
     """Retrieves the list of contacts from the database and prints to stdout"""

     # Initialize Variables
     contacts = []

     # Retrieve Contacts
     cur.execute("SELECT first_name, last_name, email FROM users.contacts")

     # Prepare Contacts
     for (first_name, last_name, email) in cur:
        contacts.append(f"{first_name} {last_name} <{email}>")

     # List Contacts
     print("\n".join(contacts))

Here, the cursor executes a ``SELECT`` statement to retrieve data from MariaDB Platform. Once the query executes, it loops over the result-set, formatting each for printing.

Note that queries return a list of rows, where each row is a tuple.

Replacing Data
**************

MariaDB Connector/Python handles replacing rows in a table using the :func:`execute` or :func:`executemany` method with ``REPLACE`` statements.

For instance, this function replaces a row with the given Primary Key with new data:

.. code-block:: python

  # Replace Contact
  def replace_contact(cur, contact_id, first_name, last_name, email):
     """Replaces contact with the given `contact_id` with new values"""

     cur.execute("REPLACE INTO users.contacts VALUES (?, ?, ?, ?)",
        (contact_id, first_name, last_name, email))

Here, the function executes a ``REPLACE`` statement. If the given contact_id exists in the table, it replaces it with the new values.

Updating Data
*************

MariaDB Connector/Python handles updating rows in a table using the execute() or executemany() method with UPDATE statements.

For instance, this function updates the last name of the contact with the given email address:

.. code-block:: python

  # Update Last Name
  def update_last_name(cur, email, last_name):
     """Updates last name of a contact in the table"""

     cur.execute("UPDATE users.contacts SET last_name=? WHERE email=?",
        (last_name, email))

Removing Data
*************

MariaDB Connector/Python removes rows from a table using the execute() or executemany() method with DELETE statements.

For instance, this function removes contacts from the table:

.. code-block:: python

  # Remove Contact from Database
  def remove_contact(cur, email):
     """Removes contacts from the database"""

     cur.execute("DELETE FROM users.contacts WHERE email = ?", (email, ))

Here, the function removes all contacts that share the given email address.

To remove all data from a table, you can do so using the TRUNCATE statement.

.. code-block:: python

  # Truncate Contacts
  def truncate_contacts(cur):
     """Removes all data from contacts table"""

     cur.execute("TRUNCATE users.contacts")

Transactions
------------

By default, the connection class is configured to auto-commit SQL statements. In cases where you would like to manage transactions from your application, set the autocommit configuration value to False:

.. code-block:: python

  # Disable Auto-commit
  conn.autocommit = False

In addition to the transaction support available in MariaDB SQL (through ``BEGIN``, ``ROLLBACK``, and ``COMMIT`` statements), the connection class also provides methods for committing and rolling back transactions.

.. code-block:: python

  # Close Connection
  def close(conn):
     """Commit open transactions and close connections,
     if commit encounters conflicts, roll back transaction."""

     try:
        conn.commit()
     except Exception as e:
        print(f"Error commiting transaction: {e}")

        conn.rollback()

     # Close Connection
     conn.close()

Connection Pooling
------------------

Connection pools enable reuse of database connections to minimize the performance overhead of connecting to the database and the churn of opening and closing connections.

Connection pools hold connections open in a pool. When a process is done with the connection, it is returned to the pool rather than closed, allowing MariaDB Connector/Python to reacquire a connection as need.
Creating Connection Pools

Connection pools are created by instantiating the ConnectionPool class in your Python code.

Each pool is given a name, which MariaDB Connector/Python uses to identify the connections to MariaDB Platform as part of the pool.

The number of connections available in a pool is controlled by the pool_size attribute. You can set the size of the pool when you create it, but not after. Set it to the number of concurrent connections you expect your application to need.

Here, a connection pool is instantiated with twenty connections on the pool variable:

.. code-block:: python

  # Module Imports
  import mariadb

  # Create Connection Pool
  pool = mariadb.ConnectionPool(
     user="admin",
     password="admin_passwd",
     host="localhost",
     port=3306,
     pool_name="web-app",
     pool_size=20
  )

Getting Connections
*******************

When working with a connection pool, connections are retrieved from the pool rather than by creating a new instance of the connection class.

To establish a connection from the pool, use the get_connection() method:

.. code-block:: python

  # Establish Pool Connection
  try:
      pconn = pool.get_connection()

  except mariadb.PoolError as e:

     # Report Error
     print(f"Error opening connection from pool: {e}")

     # Create New Connection as Alternate
     pconn = mariadb.connection(
        user="admin",
        password="admin_passwd",
        host="localhost",
        port=3306)

Here, the method returns a connection instance from the pool, which is assigned to the pconn variable.

When the connection pool has reached the maximum pool size, the get_connection() method raises a PoolError exception. In the example, when this exception is raised the application instead creates a new connection to MariaDB Platform.

Once you have a connection instance from the connection pool, you can retrieve the cursor using the cursor() method:

.. code-block:: python

  # Get Cursor
  cur = pconn.cursor()

  cur.execute("SELECT first_name, last_name, email FROM users.contacts")

  for (first_name, last_name, email) in cur:
     print(f"{first_name} {last_name} <{email}>")

Closing Connections
*******************

Closing connections from a connection pool returns the connection to the pool where it becomes available to other threads.

Connections retrieved from a connection pool can be closed using the close() method:

.. code-block:: python

  # Return Connection to Pool
  pconn.close()

Unlike normal connections, closing a connection from a connection pool does not close it altogether. Instead the connection is returned to the pool, where it becomes available to other threads.

Adding Connections
******************

In cases where you configure the connection pool using set_config(), you need to add connections to the pool through the :func:`add_connection` method.

.. code-block:: python

  # Module Import
  import mariadb

  # Create Connection Pool
  def create_connection_pool():
     """Creates and returns a Connection Pool"""
     pool = mariadb.ConnectionPool(pool_name="web-app")

     # Configure Connection Pool
     pool.set_config(
        user="admin",
        password="admin_passwd",
        host="localhost",
        port=3306,
        pool_size=20
     )

     # Return Connection Pool
     return pool

  # Add Connection to Pool
  def add_connection(pool):
     """Adds a connection to the connection pool"""
     conn = None

     try:
        pool.add_connection()
     except mariadb.PoolError as e:
        pass

     try:
        conn = pool.get_connection()
     except mariadb.PoolError as e:
        print(f"No pool connection available: {e}")

        # Create Fallback Connection
        conn = mariadb.connection(
           user="admin",
           password="admin_passwd",
           host="localhost"
        )

     # Return Connection
     return conn

When the connection pool has reached the maximum pool size, the :func:`add_connection` method raises a PoolError exception.

Field Information
-----------------

MariaDB Connector/Python provides the fieldinfo class for retrieving data type and flag information on table columns in the database.

For instance, to print the field information on each table in the database, you could loop over the SHOW TABLES statement and then loop over the description from a SELECT statement run against each table:

.. code-block:: python

  # Module Imports
  import mariadb

  # Initialize Variables
  database_info = []
  field_info = mariadb.fieldinfo()

  # Get Table List
  cur.execute("SHOW TABLES")

  for (table,) in cur.fetchall():

     # Fetch Table Information
     cur.execute(f"SELECT * FROM {table} LIMIT 1")

     table_info = [f"{conn.database}.{table}"]

     # Retrieve Column Information
     for column in cur.description:
        column_name = column[0]
        column_type = field_info.type(column)
        column_flags = field_info.flag(column)

        table_info.append("f{column_name}: {column_type} {column_flags}")

     # Log Table Info
     database_info.append("\n - ".join(table_info))

  # Report
  print("\n".join(database_info))

Here, the cursor runs SHOW TABLES to retrieve the table names in the current database. The first loop calls the fetchall() method retrieving all rows from the cursor to make room for the subsequent queries.

For each table in the database, the cursor executes a SELECT statement with a LIMIT clause to retrieve the column information. It then uses the fieldinfo methods to get the data type and flags from each column and constructs a block of text for the table. Lastly, it prints the data to stdout.
