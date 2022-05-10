/************************************************************************************
    Copyright (C) 2019 Georg Richter and MariaDB Corporation AB

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
*************************************************************************************/

PyDoc_STRVAR(
  cursor_description__doc__,
  "This read-only attribute is a sequence of 11-item sequences\n"
  "Each of these sequences contains information describing one result column:\n\n"
  "- name\n"
  "- type_code\n"
  "- display_size\n"
  "- internal_size\n"
  "- precision\n"
  "- scale\n"
  "- null_ok\n"
  "- field_flags\n"
  "- table_name\n"
  "- original_column_name\n"
  "- original_table_name\n\n"
  "This attribute will be None for operations that do not return rows or if the cursor has\n"
  "not had an operation invoked via the .execute*() method yet."
);

PyDoc_STRVAR(
  cursor_warnings__doc__,
  "Returns the number of warnings from the last executed statement, or zero\n"
  "if there are no warnings.\n\n"
);

PyDoc_STRVAR(
  cursor_closed__doc__,
  "Indicates if the cursor is closed and can't be reused"
);

PyDoc_STRVAR(
  cursor_buffered__doc__,
  "When True all result sets are immediately transferred and the connection\n"
  "between client and server is no longer blocked. Since version 1.1.0 default\n"
  "is True, for prior versions default was False."
);

PyDoc_STRVAR(
  cursor_close__doc__,
  "close()\n"
  "--\n"
  "\n"
  "Closes the cursor. If the cursor has pending or unread results, .close()\n"
  "will cancel them so that further operations using the same connection\n"
  "can be executed.\n\n"
  "The cursor will be unusable from this point forward; an Error (or subclass)\n"
  "exception will be raised if any operation is attempted with the cursor."
);

PyDoc_STRVAR(
  cursor_fetchone__doc__,
  "fetchone()\n"
  "--\n"
  "\n"
  "Fetches next row of a pending result set and returns a tuple.\n"
);

PyDoc_STRVAR(
  cursor_field_count__doc__,
  "field_count()\n"
  "--\n"
  "\n"
  "Returns the number of fields (columns) of a result set."
);

PyDoc_STRVAR(
  cursor_nextset__doc__,
  "nextset()\n"
  "--\n"
  "\n"
  "Will make the cursor skip to the next available result set,\n"
  "discarding any remaining rows from the current set."
);

PyDoc_STRVAR(
  cursor_next__doc__,
  "next()\n"
  "--\n"
  "\n"
  "Return the next row from the currently executed SQL statement\n"
  "using the same semantics as .fetchone()."
);

PyDoc_STRVAR(
  cursor_statement__doc__,
  "(read only)\n\n"
  "The last executed statement"
);

PyDoc_STRVAR(
  cursor_rownumber__doc__,
  "(read only)\n\n"
  "Current row number in result set"
);

PyDoc_STRVAR(
  cursor_arraysize__doc__,
  "(read/write)\n\n"
  "the number of rows to fetch"
);

PyDoc_STRVAR(
  cursor_paramcount__doc__,
  "(read)\n\n"
  "Returns the number of parameter markers present in the executed statement."
);
