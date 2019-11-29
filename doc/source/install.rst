.. _installation:

Installation
============

.. sectionauthor:: Georg Richter <georg@mariadb.com>

Prerequisits
------------

- Python 3 (minimum supported version is 3.6)
- MariaDB Server 10.x or MySQL Server
- MariaDB Connector/C 3.1.3 or newer

:: _build-prerequisits:

Build prerequisits
^^^^^^^^^^^^^^^^^^

The build prerequisits are required if you MariaDB Connector/C will be
installed from source distribution package or github.

- C compiler
- Python development files (Usually they are installed with package **python-dev**).
- MariaDB Connector/C libraries and header files (Either from MariaDB server package or
  from MariaDB Connector/C package).

Binary installation
-------------------
MariaDB Connector/C is also available from PyPi as wheel packages for Linux, Windows and MacOS.

Make sure you have an up to date version of pip and install it with

.. code-block:: console

    $ pip install mariadb



