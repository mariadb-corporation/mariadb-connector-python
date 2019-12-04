.. _installation:

Installation
============

.. sectionauthor:: Georg Richter <georg@mariadb.com>

Prerequisits
------------

- Python 3 (minimum supported version is 3.6)
- MariaDB Server 10.x or MySQL Server
- MariaDB Connector/C 3.1.5 or newer

:: _build-prerequisits:

Build prerequisits
^^^^^^^^^^^^^^^^^^

The build prerequisits are required if you MariaDB Connector/C will be
installed from source distribution package or github.

- C compiler
- Python development files (Usually they are installed with package **python-dev**).
- MariaDB Connector/C libraries and header files (Either from MariaDB server package or
  from MariaDB Connector/C package).
- For Posix systems: TLS libraries, e.g. GnuTLS or OpenSSL (default)


Binary installation
-------------------
MariaDB Connector/C is also available from PyPi as wheel packages for Linux, Windows and MacOS.
These binary packages are not intended for production use, since there might be several limitations
and bottlenecks, e.g.:

- Binaries for Posix systems come with their own version of libraries which will be used regardless
  of other libraries installed on the system. This might lead to unexpected results, e.g. when using
  different OpenSSL libraries.

- Dynamic MariaDB plugins (e.g. authentication plugins) are not part of the package and must
  be installed separetly by installing MariaDB Connector/C or MariaDB Server package.

Make sure you have an up to date version of pip and install it with

.. code-block:: console

    $ pip install mariadb-binary



