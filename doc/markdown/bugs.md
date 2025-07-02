# Bug reports

If you think that you have found a bug in MariaDB Software, please report it at
[Jira issue tracker](https://jira.mariadb.org) and file it under Project CONPY (abbreviation for Connector/Python).

## How to report a bug?

### Search first

Always search the bug database first. Especially if you are using an older version of MariaDB Connector/Python it could
be reported already by someone else or it was already fixed in a more recent version.

### What?

We need to know what you did, what happened and what you wanted to happen. A report stating that method xyz() hangs, will
not allow us to provide you with an advice or fix, since we just don’t know what the method is doing.
Beside versions a good bug report contains a short script which reproduces the problem. Sometimes it is also necessary to
provide the definition (and data) of used tables.

### Versions of components

MariaDB Connector/Python interacts with two other components: The database server and MariaDB Connector/C. Latter one is responsible for client/server communication. An error does not necessarily have to exist in Connector / Python; it can also be an error in the database server or in Connector/C. In this case we will reclassify the bug (MDEV or CONC).

### Avoid screenshots!

Use copy and paste instead. Screenshots create a lot more data volume and are often difficult to
read on mobile devices. Typing program code from a screenshot is also an unnecessary effort.

### Keep it simple!

Scripts which are longer than 10 lines often contain code which is not relevant to the problem and increases
the time to figure out the real problem. So try to keep it simple and focus on the real problem.

The sane applies for database related components like tables, views and stored procedures. Avoid table definitions with
hundred of columns if the problem can be reproduced with only 4 columns,

### Only report one problem in one bug report

If you have encountered two or more bugs which are not related, please file an issue for each of them.

### Crashes

If your application crashes, please also provide if possible a backtrace and output of the exception.

### Report bugs in English only!
