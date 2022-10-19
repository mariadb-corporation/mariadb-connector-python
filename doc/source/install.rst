.. _installation:

Installation
============

.. sectionauthor:: Georg Richter <georg@mariadb.com>

Prerequisites
^^^^^^^^^^^^^

The current |MCP| implementation supports
* Python versions from 3.7 to 3.11
* MariaDB server versions from version 10.3 or MySQL server versions from version 5.7.
* MariaDB client library (MariaDB Connector/C) from version |MCC_minversion|.

Binary installation
^^^^^^^^^^^^^^^^^^^

Microsoft Windows
-----------------

To install |MCP| on Microsoft Windows, you first have to install a recent version of |MCC|. MSI installer for
both 32-bit and 64-bit operating systems are available from |MCDP|.

After installation of |MCC| download and install |MCP| with the following command:

.. code-block:: console

   pip3 install mariadb 

On success, you should see a message at the end "Successfully installed mariadb-x.y.z", where x.y.z is
the recent version of |MCP|.

.. code-block:: console

   Collecting mariadb
   Downloading mariadb-1.1.5-cp310-cp310-win_amd64.whl (190 kB)
   ---------------------------------------- 190.9/190.9 kB 2.9 MB/s eta 0:00:00
   Installing collected packages: mariadb
   Successfully installed mariadb-1.1.5

Installation from Source
^^^^^^^^^^^^^^^^^^^^^^^^

Build prerequisites
-------------------

The following build prerequisites are required to install or build MariaDB Connector/Python from source code, github or from
pypi.org.

To install |MCP| from sources you will need:

- C compiler
- Python development files (Usually they are installed with package **python3-dev**). The minimum supported version of Python is 3.7.
- |MCC| libraries and header files (Either from MariaDB server package or
  from  |MCC| package). Minimum required version for |MCP| < 1.1.0 is 3.1.5, for later versions 3.2.4.
  If your distribution doesn't provide a recent version of |MCC| you can either download binary packages from |MCDP| or build
  the package from source.
- The mariadb_config program from MariaDB Connector/C, which should be in your PATH directory.
- For Posix systems: TLS libraries, e.g. GnuTLS or OpenSSL (default)
- Since MariaDB Connector/Python 1.1.5: Python's "packaging" module.

On Posix systems make sure that the path environment variable contains the directory which
contains the mariadb_config utility.

Once everything is in place, run

.. code-block:: console

    pip3 install mariadb

or if you downloaded the source package

.. code-block:: console

    python3 setup.py build
    python3 -m pip install .

For troubleshooting please also check the chapter :ref:`installation_faq` from the FAQ page.

Test suite
^^^^^^^^^^

If you have installed the sources, after successful build you can run the test suite
from the source directory.

.. code-block:: console

    cd testing
    python3 -m unittest discover -v

You can configure the connection parameters by using the following environment variables

* TEST_DB_USER (default root)
* TEST_DB_PASSWORD
* TEST_DB_DATABASE (default 'testp')
* TEST_DB_HOST (default 'localhost')
* TEST_DB_PORT (default 3306)
