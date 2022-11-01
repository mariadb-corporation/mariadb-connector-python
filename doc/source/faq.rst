.. _faq:

|MCP| FAQ
=========

This is a list of frequently asked questions about |MCP|. Feel free to suggest new
entries!

.. _installation_faq:

Installation
^^^^^^^^^^^^

.. collapse:: Error: "Python.h: No such file or directory"

   The header files and libraries of the Python development package weren't properly installed.
   Use your package manager to install them system-wide:
   
   .. collapse:: Alpine (using apk):
   
      .. code-block:: console
   
         sudo apk add python3-dev
   
   .. collapse:: Ubuntu/Debian (using apt):
   
      .. code-block:: console
   
         sudo apt-get install python3-dev
   
   .. collapse:: CentOS/RHEL (using yum):
   
      .. code-block:: console
   
         sudo yum install python3-devel
   
   .. collapse:: Fedora (using dnf):
   
      .. code-block:: console
   
         sudo dnf install python3-devel

   .. collapse:: MacOSX (using homebrew)

      .. code-block:: console

         brew install mariadb-connector-c
   
   .. collapse:: OpenSuse (using zypper):
   
      .. code-block:: console
   
         sudo zypper in python3-devel
   
   Note: The python3 development packages of your distribution might not cover all minor versions
   of python3. If you are using python3.10 you may need install python3.10-dev.


.. collapse:: ModuleNotFoundError: No module named 'packaging'

   With deprecation of distutils (see :PEP:`632`) version functions of distutils module were
   replaced in |MCP| 1.1.5 by packaging version functions.

   Before you can install |MCP| you have to install the packaging module:

      .. code-block:: console

         pip3 install packaging

.. collapse:: MariaDB Connector/Python requires MariaDB Connector/C >= 3.2.4, found version 3.1.2

   The previously installed version of |MCC| is too old and cannot be used for the |MCP| version
   you are trying to install.

   To determine the installed version of |MCC|, execute the command

   .. code-block:: console

      mariadb_config --cc_version

   - Check if your distribution can be upgraded to a more recent version of |MCC|, which fits the requirements.
   - If your distribution doesn't provide a recent version of |MCC|, check the |MCDP|, which provides
     latest versions for the major distributions.
   - If none of the above will work for you, build and install |MCC| from source.

.. collapse:: OSError: mariadb_config not found.

   The mariadb_config program is used to retrieve configuration information (such as the location of
   header files and libraries, installed version, ..) from |MCC|

   This error indicates that |MCC|, an important dependency for client/server communication that needs
   to be preinstalled, either was not installed or could not be found.

   * If |MCC| was previously installed, the installation script cannot detect the location of mariadb_config.
     Locate the directory where mariadb_config was installed and add this directory to your PATH.
  
     .. code-block:: console

        # locate mariadb_config
        sudo find / -name "mariadb_config"   

   * If |MCC| was not installed and the location of mariadb_config couldn't be detected, please install
     MariaDB Connector/C.

.. collapse:: Error: struct st_mariadb_methods’ has no member named ‘db_execute_generate_request’

   Even if the correct version of |MCC| was installed, there are multiple mysql.h include files installed 
   on your system, either from libmysql or an older |MCC| installation. This can be checked  by executing

   .. code-block:: console

      export CFLAGS="-V -E"
      pip3 install mariadb > output.txt

   Open output.txt in your favourite editor and search for "search starts here" where you can see the include
   files and paths used for the build.

.. collapse:: Q: My distribution doesn't provide a recent version of MariaDB Connector/C

   If you distribution doesn't provide a recent version of |MCC| (required version is |MCC_minversion| ) you either
   can download a version of |MCC| from the |MCDP| or build the package from source:

   .. code-block:: console

      mkdir bld
      cd bld
      cmake ..
      make
      make install


.. collapse:: Q: Does MariaDB Connector/Python provide pre-releases or snapshot builds which contain recent bug fixes?

   No. If an issue was fixed, the fix will be available in the next release via Python's package
   manager repository (pypi.org).

.. collapse:: Q: How can I build an actual version from github sources?

   To build |MCP| from github sources, checkout latest sources from github

   .. code-block:: console

      git clone https://github.com/mariadb-corporation/mariadb-conector-pyhon.git

   and build and install it with

   .. code-block:: console

      python3 setup.py build
      python3 -m pip install .


Connecting
^^^^^^^^^^

.. collapse:: mariadb.OperationalError: Can't connect to local server through socket '/tmp/mysql.sock'

   1. Check if MariaDB server has been started.

   2. Check if the MariaDB server was correctly configured and uses the right socket file:

      .. code-block:: console

         mysqld --help --verbose | grep socket

      If the socket is different and cannot be changed, you can specify the socket in your
      connection parameters.

         .. code-block:: python

            connection= mariab.connect(unix_socket="/path_socket/mysql.sock", ....)

      Another option is setting the environment variable MYSQL_UNIX_PORT.

         .. code-block:: console

            export MYSQL_UNIX_PORT=/path_to/mysql.sock

.. collapse:: Q: Which authentication methods are supported by MariaDB Connector/Python?

   |MCP| uses |MCC| for client-server communication. That means all authenticatoin plugins shipped
   together with |MCC| can be used for user authentication.


General:
^^^^^^^^

.. collapse:: Q: How do I execute multipe statements with cursor.execute() ?

   Since |MCP| uses binary protocol for client-server communication, this feature is not supported yet.

.. collapse:: Q: Does MariaDB Connector/Python works with Python 2.x ?

   Python versions which reached their end of life are not officially supported. While |MCP| might still work
   with older Python 3.x versions, it doesn't work with Python version 2.x.

.. collapse:: Q: How can I see a transformed statement? Is there a mogrify() method available?

   No, |MCP| Python uses binary protocol for client/server communication. Before a statement will be executed
   it will be parsed and parameter markers which are different than question marks will be replaced by question
   marks. Afterwards the statement will be sent together with data to the server. The transformed statement can
   be obtained by cursor.statement attribute

   Example:

   .. code-block:: python

      data = ("Future", 2000)
      statement = """SELECT DATE_FORMAT(creation_time, '%h:%m:%s') as time, topic, amount
                     FROM mytable WHERE topic=%s and id > %s"""
      cursor.execute(statement, data)
      print(cursor.statement)

   .. code-block:: console

      SELECT DATE_FORMAT(creation_time, '%h:%m:%s') as time, topic, amount FROM mytable WHERE topic=? and id > ?

   Please note, that there is no need to escape '%s' by '%%s' for the time conversion in DATE_FORMAT() function.

.. collapse:: Q: Does MariaDB Connector/Python supports paramstyle "pyformat" ?

   The default paramstyle (see :PEP:`249`) is **qmark** (question mark) for parameter markers. For compatibility
   with other drivers |MCP| also supports (and automatically recognizes) the **format** and **pyformat** parameter
   styles.

   Mixing different paramstyles within the same query is not supported and will raise an exception.



Transactions
^^^^^^^^^^^^

.. collapse:: Q: Previously inserted records disappeared after my program finished.

   Default for autocommit in |MCP| is off, which means every transaction must be committed.
   Uncommitted pending transactions are rolled back automatically when the connection is closed.

   .. code-block:: python

      cursor= connection.cursor()
      cursor.execute("CREATE TABLE t1 (id int, name varchar(20))")

      #insert
      data= [(1, "Andy"), (2, "George"), (3, "Betty")]
      cursor.executemany("INSERT INTO t1 VALUES (?,?)", data)

      #commit pending transactions
      connection.commit()

      #close handles
      cursor.close()
      connection.close()

  
