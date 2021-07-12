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

import mariadb, collections
from mariadb.codecs import *
from numbers import Number
from mariadb.constants import *

PARAMSTYLE_QMARK= 1
PARAMSTYLE_FORMAT= 2
PARAMSTYLE_PYFORMAT= 3

RESULT_TUPLE= 0
RESULT_NAMEDTUPLE= 1
RESULT_DICTIONARY= 2

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
        self._parsed= False
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

        super().__init__(connection, **kwargs)

                
    def _add_text_params(self):
        new_stmt= self.statement
        replace_diff= 0
        for i in range (0,len(self._paramlist)):
            if self._paramstyle == PARAMSTYLE_PYFORMAT:
                val= self._data[self._parseinfo["keys"][i]]
            else:
                val= self._data[i]
            if val is None:
                replace= "NULL";
            else:
                if isinstance(val, Number):
                    replace= val.__str__()
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

        print(self._paramlist)

        # check if number of place holders match the number of 
        # supplied elements in data tuple
        if (not self._data and len(self._paramlist) > 0) or \
           (len(self._data) != len(self._paramlist)):
            raise mariadb.DataError("Number of parameters in statement (%s)"\
                                    " doesn't match the number of data elements (%s)."\
                                     % (len(self._paramlist), len(self._data)))

    def _parse_execute(self, statement, data=()):
        """
        Simple SQL statement parsing:
        """

        if not statement:
            raise mariadb.ProgrammingError("empty statement")

        # parse statement
        print("statement: %s" % statement)
        print("prev statement: %s" % self._prev_stmt)
        if self._prev_stmt != statement:
            super()._parse(statement)
            self._prev_stmt= statement
            self._reprepare= True
            print("param_count: %s" % self.paramcount)
            print("parsed")
        else:
            self._reprepare= False
            print("not parsed")

        self._data= data

        self._check_execute_params()
       
        if self._text:
            # in text mode we need to substitute parameters
            # and store transformed statement
            if (self.paramcount > 0):
                 self._transformed_statement= self._add_text_params()
            else:
                 self._transformed_statement= self.statement

    def nextset(self):
        return super()._nextset()

    def execute(self, statement, data=(), buffered=False):
        """
        place holder for execute() description
        """

        if buffered:
            self.buffered= 1

        # parse statement and check param style
        if not self._parsed or not self._prepared:
            self._parse_execute(statement, (data))
            self._parsed= True
        self._description= None

        if (self._paramstyle ==  3 and not isinstance(data, dict)):
            raise TypeError("Argument 2 must be Dict")
        elif (not isinstance(data, (tuple, list))):
            raise TypeError("Argument 2 must be Tuple or List")

        if len(data):
            self._data= data
        else:
            self._data= None

        if self._force_binary:
           self._text= False

        if self._text:
            self._execute_text(self._transformed_statement)
            self._readresponse()
        else:
            self._data= data
            self._execute_binary()

        self._initresult()

    def executemany(self, statement, data=[]):
        """ Bulk operations """


        # If the server doesn't support bulk operations, we need to emulate
        # by looping
        if (self.connection.server_capabilities & (CLIENT.BULK_OPERATIONS >> 32)):
            for row in data:
               self.execute(statement, row)
        else:
            # parse statement 
            self._parse_execute(statement, (data))

    def _fetch_row(self):
        if not self.field_count:
            return()
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

    def fetchall(self):
        rows=[];
        for row in self:
            rows.append((row))
        return rows

    def close(self):
        super().close()

    def __enter__(self):
        """Returns a copy of the cursor."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Closes cursor."""
        self.close()

    @property
    def rowcount(self):
        if not self.statement:
            return -1;
        if not self.field_count:
            return 0;
        return super().rowcount

    @property
    def connection(self):
        """Read-Only attribute which returns the reference to the connection
           object on which the cursor was created."""
        return self._connection
