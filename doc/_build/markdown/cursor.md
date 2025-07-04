# The cursor class

### *class* Cursor(connection, \*\*kwargs)

MariaDB Connector/Python Cursor Object

## Cursor methods

#### Cursor.callproc(sp: str, data: Sequence = ())

Executes a stored procedure sp. The data sequence must contain an
entry for each parameter the procedure expects.

Input/Output or Output parameters have to be retrieved by .fetch
methods, the .sp_outparams attribute indicates if the result set
contains output parameters.

Arguments:
: - sp: Name of stored procedure.
  - data: Optional sequence containing data for placeholder
    : substitution.

Example:

```python
>>>cursor.execute("CREATE PROCEDURE p1(IN i1 VAR  CHAR(20), OUT o2 VARCHAR(40))"
                  "BEGIN"
                  "  SELECT 'hello'"
                  "  o2:= 'test'"
                  "END")
>>>cursor.callproc('p1', ('foo', 0))
>>> cursor.sp_outparams
False
>>> cursor.fetchone()
('hello',)
>>> cursor.nextset()
True
>>> cursor.sp_outparams
True
>>> cursor.fetchone()
('test',)
```

#### Cursor.execute(statement: str, data: Sequence = (), buffered=None)

Prepare and execute a SQL statement.

Parameters may be provided as sequence or mapping and will be bound
to variables in the operation. Variables are specified as question
marks (paramstyle =’qmark’), however for compatibility reasons MariaDB
Connector/Python also supports the ‘format’ and ‘pyformat’ paramstyles
with the restriction, that different paramstyles can’t be mixed within
a statement.

A reference to the operation will be retained by the cursor.
If the cursor was created with attribute prepared =True the statement
string for following execute operations will be ignored.
This is most effective for algorithms where the same operation is used,
but different parameters are bound to it (many times).

By default execute() method generates an buffered result unless the
optional parameter buffered was set to False or the cursor was
generated as an unbuffered cursor.

#### Cursor.executemany(statement, parameters)

Prepare a database operation (INSERT,UPDATE,REPLACE or DELETE
statement) and execute it against all parameter found in sequence.

Exactly behaves like .execute() but accepts a list of tuples, where
each tuple represents data of a row within a table.
.executemany() only supports DML (insert, update, delete) statements.

If the SQL statement contains a RETURNING clause, executemany()
returns a result set containing the values for columns listed in the
RETURNING clause.

Example:

The following example will insert 3 rows:

```python
data= [
    (1, 'Michael', 'Widenius')
    (2, 'Diego', 'Dupin')
    (3, 'Lawrin', 'Novitsky')
]
cursor.executemany("INSERT INTO colleagues VALUES (?, ?, ?)", data)
```

To insert special values like NULL or a column default, you need to specify indicators:

- INDICATOR.NULL is used for NULL values
- INDICATOR.IGNORE is used to skip update of a column.
- INDICATOR.DEFAULT is used for a default value (insert/update)
- INDICATOR.ROW is used to skip update/insert of the entire row.

#### NOTE
- All values for a column must have the same data type.
- Indicators can only be used when connecting to a MariaDB Server 10.2 or newer. MySQL servers don’t support this feature.

#### Cursor.fetchall()

Fetch all remaining rows of a query result, returning them as a
sequence of sequences (e.g. a list of tuples).

An exception will be raised if the previous call to execute() didn’t
produce a result set or execute() wasn’t called before.

#### Cursor.fetchmany(size: int = 0)

Fetch the next set of rows of a query result, returning a sequence
of sequences (e.g. a list of tuples). An empty sequence is returned
when no more rows are available.

The number of rows to fetch per call is specified by the parameter.
If it is not given, the cursor’s arraysize determines the number
of rows to be fetched. The method should try to fetch as many rows
as indicated by the size parameter.
If this is not possible due to the specified number of rows not being
available, fewer rows may be returned.

An exception will be raised if the previous call to execute() didn’t
produce a result set or execute() wasn’t called before.

#### Cursor.fetchone()

Fetch the next row of a query result set, returning a single sequence,
or None if no more data is available.

An exception will be raised if the previous call to execute() didn’t
produce a result set or execute() wasn’t called before.

#### Cursor.next()

Return the next row from the currently executed SQL statement
using the same semantics as .fetchone().

#### Cursor.nextset()

Will make the cursor skip to the next available result set,
discarding any remaining rows from the current set.

#### Cursor.scroll(value: int, mode='relative')

Scroll the cursor in the result set to a new position according to
mode.

If mode is “relative” (default), value is taken as offset to the
current position in the result set, if set to absolute, value states
an absolute target position.

#### Cursor.setinputsizes()

Required by PEP-249. Does nothing in MariaDB Connector/Python

#### Cursor.setoutputsize()

Required by PEP-249. Does nothing in MariaDB Connector/Python

## Cursor attributes

#### Cursor.arraysize

(read/write)

the number of rows to fetch

This read/write attribute specifies the number of rows to fetch at a time with .fetchmany(). It defaults to 1 meaning to fetch a single row at a time

#### Cursor.buffered

When True all result sets are immediately transferred and the connection
between client and server is no longer blocked. Since version 1.1.0 default
is True, for prior versions default was False.

#### Cursor.closed

Indicates if the cursor is closed and can’t be reused

#### Cursor.connection

Read-Only attribute which returns the reference to the connection
object on which the cursor was created.

#### Cursor.description

This read-only attribute is a sequence of 11-item sequences
Each of these sequences contains information describing one result column:

- name
- type_code
- display_size
- internal_size
- precision
- scale
- null_ok
- field_flags
- table_name
- original_column_name
- original_table_name

This attribute will be None for operations that do not return rows or if the cursor has
not had an operation invoked via the .execute\*() method yet.

#### NOTE
The 8th parameter ‘field_flags’ is an extension to the PEP-249 DB API standard.
In combination with the type element field, it can be determined for example,
whether a column is a BLOB or TEXT field:

#### Versionadded
Added in version 1.1.0: The parameter table_name, original_column_name and original_table_name are an   extension to the PEP-249 DB API standard.

```python
if cursor.description[0][1] == FIELD_TYPE.BLOB:
    if cursor.description[0][7] == FIELD_FLAG.BINARY:
        print("column is BLOB")
    else:
        print("column is TEXT")
```

#### Cursor.lastrowid

Returns the ID generated by a query on a table with a column having
the AUTO_INCREMENT attribute or the value for the last usage of
LAST_INSERT_ID().

If the last query wasn’t an INSERT or UPDATE
statement or if the modified table does not have a column with the
AUTO_INCREMENT attribute and LAST_INSERT_ID was not used, the returned
value will be None

#### Versionadded
Added in version 1.1.8.

#### Cursor.metadata

Similar to description property, this property returns a dictionary with complete metadata.

The dictionary contains the following keys:

- catalog:     catalog (always ‘def’)
- schema:      current schema
- field:       alias column name or if no alias was specified column name
- org_field:   original column name
- table:       alias table name or if no alias was specified table name
- org_table:   original table name
- type:        column type
- charset:     character set (utf8mb4 or binary)
- length:      The length of the column
- max length:  The maximum length of the column
- decimals:    The numer of decimals
- flags:       Flags (flags are defined in constants.FIELD_FLAG)
- ext_type:    Extended data type (types are defined in constants.EXT_FIELD_TYPE)

#### Cursor.sp_outparams

Indicates if the current result set contains in out or out parameter
from a previous executed stored procedure

#### Versionadded
Added in version 1.1.0.

#### Cursor.paramcount

(read)

Returns the number of parameter markers present in the executed statement.

#### Cursor.rowcount

This read-only attribute specifies the number of rows that the last        execute\*() produced (for DQL statements like SELECT) or affected
(for DML statements like UPDATE or INSERT).
The return value is -1 in case no .execute\*() has been performed
on the cursor or the rowcount of the last operation  cannot be
determined by the interface.

#### NOTE
For unbuffered cursors (default) the exact number of rows can only be
determined after all rows were fetched.

Example:

```python
>>> cursor=conn.cursor()
>>> cursor.execute("SELECT 1")
>>> cursor.rowcount
-1
>>> rows= cursor.fetchall()
>>> cursor.rowcount
1
>>> cursor=conn.cursor(buffered=True)
>>> cursor.execute("SELECT 1")
>>> cursor.rowcount
1
```

#### Cursor.statement

(read only)

The last executed statement

#### Cursor.warnings

Returns the number of warnings from the last executed statement, or zero
if there are no warnings.

#### NOTE
Warnings can be retrieved by the show_warnings() method of connection class.
