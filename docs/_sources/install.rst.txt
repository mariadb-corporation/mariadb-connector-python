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

Build prerequisites
^^^^^^^^^^^^^^^^^^^
The following build prerequisites are required to install or build MariaDB Connector/Python from source code, github or from
pypi.org.

For Windows operating platforms the pypi.org download page provides binary versions.

To install |MCP| from sources you will need:

- C compiler
- Python development files (Usually they are installed with package **python3-dev**). The minimum supported version of Python is 3.7.
- MariaDB Connector/C libraries and header files (Either from MariaDB server package or
  from MariaDB Connector/C package). Minimum required version for |MCP| < 1.1.0 is 3.1.5, for later versions 3.2.4.
- The mariadb_config program from MariaDB Connector/C, which should be in your PATH directory.
- For Posix systems: TLS libraries, e.g. GnuTLS or OpenSSL (default)
- Since MariaDB Connector/Python 1.1.5: Python's "packaging" module.

On Posix systems make sure that the path environment variable contains the directory which
contains the mariadb_config utility.

Once everything is in place, run

.. code-block:: console

    $ pip3 install mariadb

or if you downloaded the source package

.. code-block:: console

    $ python3 setup.py build
    $ python3 -m pip install .


Binary installation
-------------------

MariaDB Connector/Python is also available from PyPi as wheel packages for Windows.
Please note that dynamic MariaDB plugins (e.g. authentication plugins) are not part
of the package and must be installed separately by installing MariaDB Connector/C or
MariaDB Server package.

Make sure you have an up-to-date version of pip and install |MCP| with

.. code-block:: console

    $ pip3 install mariadb

Test suite
----------
If you have installed the sources, after successful build you can run the test suite
from the source directory.

.. code-block:: console

    $ python3 -m unittest discover -v

You can configure the connection parameters by using the following environment variables

* TEST_DB_USER (default root)
* TEST_DB_PASSWORD
* TEST_DB_DATABASE (default 'testp')
* TEST_DB_HOST (default 'localhost')
* TEST_DB_PORT (default 3306)
