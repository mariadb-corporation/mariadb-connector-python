<a id="faq"></a>

# MariaDB Connector/Python FAQ

This is a list of frequently asked questions about MariaDB Connector/Python. Feel free to suggest new
entries!

<a id="installation-faq"></a>

## Installation

<details>
<summary>"Python.h: No such file or directory"</summary>

The header files and libraries of the Python development package weren’t properly installed.
Use your package manager to install them system-wide:

<details>
<summary>Alpine (using apk):</summary>
```console
sudo apk add python3-dev
```

</details>
<details>
<summary>Ubuntu/Debian (using apt):</summary>
```console
sudo apt-get install python3-dev
```

</details>
<details>
<summary>CentOS/RHEL (using yum):</summary>
```console
sudo yum install python3-devel
```

</details>
<details>
<summary>Fedora (using dnf)</summary>
```console
sudo dnf install python3-devel
```

</details>
<details>
<summary>MacOSX (using homebrew)</summary>
```console
brew install mariadb-connector-c
```

</details>
<details>
<summary>OpenSuse (using zypper):</summary>
```console
sudo zypper in python3-devel
```

</details>

#### NOTE
The python3 development packages of your distribution might not cover all minor versions
of python3. If you are using python3.10 you may need install python3.10-dev.

</details>
<details>
<summary>ModuleNotFoundError: No module named 'packaging'</summary>

With deprecation of distutils (see :PEP:`632`) version functions of distutils module were
replaced in MariaDB Connector/Python 1.1.5 by packaging version functions.

Before you can install MariaDB Connector/Python you have to install the packaging module:

```console
pip3 install packaging
```

</details>
<details>
<summary>MariaDB Connector/Python requires MariaDB Connector/C >= 3.3.1, found version 3.1.2</summary>

The previously installed version of MariaDB Connector/C is too old and cannot be used for the MariaDB Connector/Python version
you are trying to install.

To determine the installed version of MariaDB Connector/C, execute the command

```console
mariadb_config --cc_version
```

- Check if your distribution can be upgraded to a more recent version of MariaDB Connector/C, which fits the requirements.
- If your distribution doesn’t provide a recent version of MariaDB Connector/C, check the |MCDP|, which provides latest versions for the major distributions.
- If none of the above will work for you, build and install MariaDB Connector/C from source.

</details>
<details>
<summary>OSError: mariadb_config not found.</summary>

The mariadb_config program is used to retrieve configuration information (such as the location of header files and libraries, installed version, …) from MariaDB Connector/C.

This error indicates that MariaDB Connector/C, an important dependency for client/server communication that needs to be preinstalled, either was not installed or could not be found.

* If MariaDB Connector/C was previously installed, the installation script cannot detect the location of mariadb_config.  Locate the directory where mariadb_config was installed and add this directory to your PATH.

```console
# locate mariadb_config
sudo find / -name "mariadb_config"
```

* If MariaDB Connector/C was not installed and the location of mariadb_config couldn’t be detected, please install MariaDB Connector/C.

</details>
<details>
<summary>Error: struct st_mariadb_methods’ has no member named ‘db_execute_generate_request’</summary>

Even if the correct version of MariaDB Connector/C was installed, there are multiple mysql.h include files installed on your system, either from libmysql or an older MariaDB Connector/C installation. This can be checked  by executing

```console
export CFLAGS="-V -E"
pip3 install mariadb > output.txt
```

Open output.txt in your favourite editor and search for “search starts here” where you can see the include files and paths used for the build.

</details>
<details>
<summary>My distribution doesn't provide a recent version of MariaDB Connector/C</summary>

If you distribution doesn’t provide a recent version of MariaDB Connector/C (required version is |MCC_minversion| ) you either
can download a version of MariaDB Connector/C from the |MCDP| or build the package from source:

```console
mkdir bld
cd bld
cmake ..
make
make install
```

</details>
<details>
<summary>Does MariaDB Connector/Python provide pre-releases or snapshot builds which contain recent bug fixes?</summary>

No. If an issue was fixed, the fix will be available in the next release via Python’s package manager repository ([pypi.org](http://pypi.org)).

</details>
<details>
<summary>How can I build an actual version from github sources?</summary>

To build MariaDB Connector/Python from github sources, checkout latest sources from github

```console
git clone https://github.com/mariadb-corporation/mariadb-conector-pyhon.git
```

and build and install it with

```console
python3 -m pip install .
```

</details>

## Connecting

<details>
<summary>mariadb.OperationalError: Can't connect to local server through socket '/tmp/mysql.sock'</summary>
* Check if MariaDB server has been started.
* Check if the MariaDB server was correctly configured and uses the right socket file:

```console
mysqld --help --verbose | grep socket
```

If the socket is different and cannot be changed, you can specify the socket in your connection parameters.

```python
    connection= mariab.connect(unix_socket="/path_socket/mysql.sock", ....)
```

Another option is setting the environment variable MYSQL_UNIX_PORT.

```console
export MYSQL_UNIX_PORT=/path_to/mysql.sock
```

</details>
<details>
<summary>Which authentication methods are supported by MariaDB Connector/Python?</summary>

MariaDB Connector/Python uses MariaDB Connector/C for client-server communication. That means all authenticatoin plugins shipped together with MariaDB Connector/C can be used for user authentication.

</details>

## General:

<details>
<summary>How do I execute multipe statements with cursor.execute() ?</summary>

Since MariaDB Connector/Python uses binary protocol for client-server communication, this feature is not supported yet.

</details>
<details>
<summary>Does MariaDB Connector/Python works with Python 2.x ?</summary>

Python versions which reached their end of life are not officially supported. While MariaDB Connector/Python might still work with older Python 3.x versions, it doesn’t work with Python version 2.x.

</details>
<details>
<summary>How can I see a transformed statement? Is there a mogrify() method available?</summary>

No, MariaDB Connector/Python uses binary protocol for client/server communication. Before a statement will be executed it will be parsed and parameter markers which are different than question marks will be replaced by question marks. Afterwards the statement will be sent together with data to the server. The transformed statement can be obtained by cursor.statement attribute

Example:

```python
    data = ("Future", 2000)
    statement = """SELECT DATE_FORMAT(creation_time, '%h:%m:%s') as time, topic, amount
                   FROM mytable WHERE topic=%s and id > %s"""
    cursor.execute(statement, data)
    print(cursor.statement)
```

#### NOTE
There is no need to escape ‘%s’ by ‘%%s’ for the time conversion in DATE_FORMAT() function.

</details>
<details>
<summary>Does MariaDB Connector/Python supports paramstyle "pyformat" ?</summary>

The default paramstyle (see :PEP:`249`) is **qmark** (question mark) for parameter markers. For compatibility
with other drivers MariaDB Connector/Python also supports (and automatically recognizes) the **format** and **pyformat** parameter
styles.

#### NOTE
Mixing different paramstyles within the same statement is not supported and will raise an exception.

</details>

## Transactions

<details>
<summary>Previously inserted records disappeared after my program finished.</summary>

Default for autocommit in MariaDB Connector/Python is off, which means every transaction must be committed.
Uncommitted pending transactions are rolled back automatically when the connection is closed.

```python
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
```

</details>
