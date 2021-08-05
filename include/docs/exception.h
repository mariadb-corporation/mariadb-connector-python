/*****************************************************************************
   Copyright (C) 2020 Georg Richter and MariaDB Corporation AB

   This library is free software; you can redistribute it and/or
   modify it under the terms of the GNU Library General Public
   License as published by the Free Software Foundation; either
   version 2 of the License, or (at your option) any later version.

   This library is distributed in the hope that it will be useful,
   but WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
   Library General Public License for more details.

   You should have received a copy of the GNU Library General Public
   License along with this library; if not see <http://www.gnu.org/licenses>
   or write to the Free Software Foundation, Inc.,
   51 Franklin St., Fifth Floor, Boston, MA 02110, USA
******************************************************************************/

PyDoc_STRVAR(
    exception_interface__doc__,
    "Exception raised for errors that are related to the database interface "\
    "rather than the database itself"
);

PyDoc_STRVAR(
    exception_warning__doc__,
    "Exception raised for important warnings like data truncations "\
    "while inserting, etc"
);

PyDoc_STRVAR(
    exception_database__doc__,
   "Exception raised for errors that are related to the database"
);

PyDoc_STRVAR(
    exception_data__doc__,
    "Exception raised for errors that are due to problems with the "\
    "processed data like division by zero, numeric value out of range, etc."
);

PyDoc_STRVAR(
    exception_pool__doc__,
    "Exception raised for errors related to ConnectionPool class."
);

PyDoc_STRVAR(
    exception_operational__doc__,
    "Exception raised for errors that are related to the database's "\
    "operation and not necessarily under the control of the programmer."
);

PyDoc_STRVAR(
    exception_integrity__doc__,
    "Exception raised when the relational integrity of the database "\
    "is affected, e.g. a foreign key check fails"
);

PyDoc_STRVAR(
    exception_internal__doc__,
    "Exception raised when the database encounters an internal error, "\
    "e.g. the cursor is not valid anymore";
);

PyDoc_STRVAR(
    exception_programming__doc__,
    "Exception raised for programming errors, e.g. table not found or "\
    "already exists, syntax error in the SQL statement"
);

PyDoc_STRVAR(
    exception_notsupported__doc__,
    "Exception raised in case a method or database API was used which is "\
    "not supported by the database"
);
