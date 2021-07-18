#
# Copyright (C) 2020-2021 Georg Richter and MariaDB Corporation AB

# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Library General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.

# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Library General Public License for more details.

# You should have received a copy of the GNU Library General Public
# License along with this library; if not see <http://www.gnu.org/licenses>
# or write to the Free Software Foundation, Inc.,
# 51 Franklin St., Fifth Floor, Boston, MA 02110, USA
#

import mariadb, collections, logging
from mariadb.codecs import *
from numbers import Number
from mariadb.constants import *

PARAMSTYLE_QMARK= 1
PARAMSTYLE_FORMAT= 2
PARAMSTYLE_PYFORMAT= 3

RESULT_TUPLE= 0
RESULT_NAMEDTUPLE= 1
RESULT_DICTIONARY= 2

# Command types
SQL_NONE= 0,
SQL_INSERT= 1
SQL_UPDATE= 2
SQL_REPLACE= 3
SQL_DELETE= 4
SQL_CALL= 5
SQL_DO= 6
SQL_SELECT=7
SQL_OTHER=255


class Cursor(mariadb._mariadb.cursor):
    """Returns a MariaDB cursor object"""

    def __init__(self, connection, **kwargs):

        self._dictionary= False
        self._named_tuple= False
        self._connection= connection
        self._resulttype= RESULT_TUPLE
        self._description= None
        self._transformed_statement= None
        self._prepared= False
        self._prev_stmt= None
        self._force_binary= None

        self._parseinfo= None
        self._data= None

        if not connection:
            raise mariadb.ProgrammingError("Invalid or no connection provided")

        if kwargs:
             rtype= kwargs.pop("named_tuple", False)
             if rtype:
                 self._resulttype= RESULT_NAMEDTUPLE
             else:
                 rtype= kwargs.pop("dictionary", False)
                 if rtype:
                     self._resulttype= RESULT_DICTIONARY
             buffered= kwargs.pop("buffered", False)
             self.buffered= buffered
             self._prepared= kwargs.pop("prepared", False)
             self._force_binary= kwargs.pop("binary", False)
             self._cursor_type= kwargs.pop("cursor_type", 0)

        super().__init__(connection, **kwargs)

                
    def _add_text_params(self):
        new_stmt= self.statement
        replace_diff= 0
        for i in range (0,len(self._paramlist)):
            if self._paramstyle == PARAMSTYLE_PYFORMAT:
                val= self._data[self._keys[i]]
            else:
                val= self._data[i]
            if val is None:
                replace= "NULL";
            else:
                if isinstance(val, INDICATOR.MrdbIndicator):
                    if val == INDICATOR.NULL:
                       replace= "NULL"
                    if val == INDICATOR.DEFAULT:
                       replace= "DEFAULT"   
                elif isinstance(val, Number):
                    replace= val.__str__()
                else:
                    if isinstance(val, (bytes, bytearray)):
                        replace= "\"%s\"" % self.connection.escape_string(val.decode(encoding='latin1'))
                    else:
                        replace= "\"%s\"" % self.connection.escape_string(val.__str__())
            start= self._paramlist[i] + replace_diff
            end= self._paramlist[i] + replace_diff + 1
            
            new_stmt= new_stmt[:start] + replace.__str__() + new_stmt[end:]
            replace_diff+= len(replace) - 1
        return new_stmt

    def _check_execute_params(self):
        # check data format
        if self._paramstyle == PARAMSTYLE_QMARK or \
           self._paramstyle == PARAMSTYLE_FORMAT:
            if not isinstance(self._data, (tuple,list)):
                raise mariadb.ProgrammingError("Data arguent nust be Tuple or List")

        if self._paramstyle == PARAMSTYLE_PYFORMAT and\
               not isinstance(self._data, dict):
            raise mariadb.ProgrammingError("Data arguent nust be Dictionary")

        # check if number of place holders matches the number of 
        # supplied elements in data tuple
        if (not self._data and len(self._paramlist) > 0) or \
           (len(self._data) != len(self._paramlist)):
            raise mariadb.DataError("Number of parameters in statement (%s)"\
                                    " doesn't match the number of data elements (%s)."\
                                     % (len(self._paramlist), len(self._data)))

    def callproc(self, sp, data=()):
        """
        Executes a stored procedure. The args sequence must contain an entry for
        each parameter the procedure expects.
        Input/Output or Output parameters have to be retrieved by .fetch methods,
        """
        logging.debug("callproc()")

        statement= "CALL %s(" % sp
        first= 0
        for param in data:
            if first:
                statement+= ","
            statement+= "?"
            first+= 1
        statement+= ")"
        self.execute(statement, data)
        logging.debug(statement, data)

    def _parse_execute(self, statement, data=()):
        """
        Simple SQL statement parsing:
        """

        logging.debug("parse_execute: %s" % statement)

        if not statement:
            raise mariadb.ProgrammingError("empty statement")

        # parse statement
        if self.statement != statement:
            super()._parse(statement)
            self._prev_stmt= statement
            self._reprepare= True
        else:
            self._reprepare= False

        self._transformed_statement= self.statement

        if self._cursor_type == CURSOR.READ_ONLY:
            self._text= False

        self._data= data

        self._check_execute_params()
       

    def nextset(self):
        return super()._nextset()

    def execute(self, statement, data=(), buffered=False):
        """
        place holder for execute() description
        """

        # Parse statement
        do_parse= True

        if buffered:
            self.buffered= True

        if self.field_count:
            logging.debug("clearing result set")
            self._clear_result()

        # if we have a prepared cursor, we have to set statement
        # to previous statement and don't need to parse
        if self._prepared and self.statement:
            statement= self.statement
            do_parse= False

        # Avoid reparsing of same statement
        if statement == self.statement:
           do_parse= True

        # parse statement and check param style
        if do_parse:
            self._parse_execute(statement, (data))
        self._description= None

        # check if data parameters are passed in correct format
        if (self._paramstyle == 3 and not isinstance(data, dict)):
            raise TypeError("Argument 2 must be Dict")
        elif self._paramstyle < 3 and (not isinstance(data, (tuple, list))):
            raise TypeError("Argument 2 must be Tuple or List")

        if len(data):
            self._data= data
        else:
            self._data= None
            # If statement doesn't contain parameters we force to run in text
            # mode, unless a server side cursor or stored procedure will be
            # executed.
            if self._command != SQL_CALL and self._cursor_type == 0:
                self._text= True

        if self._force_binary:
           self._text= False

        if self._text:
            # in text mode we need to substitute parameters
            # and store transformed statement
            if (self.paramcount > 0):
                 self._transformed_statement= self._add_text_params()
            else:
                 self._transformed_statement= self.statement

            self._execute_text(self._transformed_statement)
            self._readresponse()
        else:
            logging.debug("binary mode")
            self._data= data
            self._execute_binary()

        self._initresult()

    def executemany(self, statement, parameters=[]):
        """ 
        Prepare a database operation (INSERT,UPDATE,REPLACE or DELETE statement) and
        execute it against all parameter found in sequence.
        """
        logging.debug("bulk %s" % statement)

        if not len(parameters):
            raise TypeError("No data provided")

        if self.field_count:
            logging.debug("clearing result")
            self._clear_result()

        # If the server doesn't support bulk operations, we need to emulate
        # by looping
        if not (self.connection.server_capabilities & (CLIENT.BULK_OPERATIONS >> 32)):
            for row in parameters:
                self.execute(statement, row)
            #todo: rowcount ?!
        else:
            # parse statement 
            self._parse_execute(statement, parameters[0])
            self._data= parameters
            self.is_text= False

        self._execute_bulk()

    def _fetch_row(self):

        # if there is no result set, PEP-249 requires to raise an
        # exception
        if not self.field_count:
             raise mariadb.ProgrammingError("Cursor doesn't have a result set")
        row= super().fetchone()
        if self._connection._converter:
            l= list(row)
            if not self._description:
                self._description= super().description
            for i,v in enumerate(row):
                type= self.description[i][1]
                if type in self._connection._converter:
                    func= self._connection._converter[type]
                    l[i]= func(v)
                else:
                    l[i]= v
            row= tuple(l)
        return row

    def close(self):
        super().close()

    def fetchone(self):
        row= self._fetch_row()
        if not row:
            return row
        if self._resulttype == RESULT_DICTIONARY:
            ret= dict(zip(list(d[0] for d in self.description),row))
        elif self._resulttype == RESULT_NAMEDTUPLE:
            ret= collections.namedtuple('Row1', list(d[0] for d in self.description));
            ret= ret._make(row)
        else:
            ret= row
        return ret

    def fetchmany(self, size=0):
        rows=[]
        if size == 0:
            size= self.arraysize
        for count in range(0, size):
            row= self.fetchone()
            if row:
                rows.append(row)
        return rows

    def fetchall(self):
        rows=[];
        for row in self:
            rows.append((row))
        return rows

    def scroll(self, value, mode="relative"):
        """
        Scroll the cursor in the result set to a new position according to mode.

        If mode is "relative" (default), value is taken as offset to the current
        position in the result set, if set to absolute, value states an absolute
        target position.
        """

        if self.field_count == 0:
            raise mariadb.ProgrammingError("Cursor doesn't have a result set")

        if not self.buffered:
            raise mariadb.ProgrammingError("This method is available only for cursors "\
                                           "with a buffered result set.")

        if mode != "absolute" and mode != "relative":
            raise mariadb.DataError("Invalid or unknown scroll mode specified.")

        if value == 0 and mode != "absolute":
            raise mariadb.DataError("Invalid position value 0.")

        if mode == "relative":
            if self.rownumber + value < 0 or \
               self.rownumber + value > self.rowcount:
                raise mariadb.DataError("Position value is out of range.")
            new_pos= self.rownumber + value
        else:
            if value < 0 or value >= self.rowcount:
                raise mariadb.DataError("Position value is out of range.")
            new_pos= value

        self._seek(new_pos);
        self._rownumber= new_pos;


    def __enter__(self):
        """Returns a copy of the cursor."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Closes cursor."""
        self.close()

    def __del__(self):
        self.close()

    @property
    def lastrowid(self):
        id= self.insert_id
        if id > 0:
            return id
        return None

    @property
    def connection(self):
        """Read-Only attribute which returns the reference to the connection
           object on which the cursor was created."""
        return self._connection
