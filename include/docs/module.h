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
  module_binary__doc__,
  "Binary(string)\n"
  "--\n"
  "\n"
  "This function constructs an object capable of holding a binary (long)\n"
  "string value.\n"
);

PyDoc_STRVAR(
  module_connect__doc__,
  __connect__doc__
);

PyDoc_STRVAR(
  module_DateFromTicks__doc__,
  "DateFromTicks(ticks)\n"
  "--\n"
  "\n"
  "This function constructs an object holding a date value from the given\n"
  "ticks value (number of seconds since the epoch). For more information\n"
  "see the documentation of the standard Python time module"
);

PyDoc_STRVAR(
  module_TimeFromTicks__doc__,
  "TimeFromTicks(ticks)\n"
  "--\n"
  "\n"
  "This function constructs an object holding a time value from the given\n"
  "ticks value (number of seconds since the epoch). For more information\n"
  "see the documentation of the standard Python time module"
);

PyDoc_STRVAR(
  module_TimestampFromTicks__doc__,
  "TimestampFromTicks(ticks)\n"
  "--\n"
  "\n"
  "This function constructs an object holding a time stamp value from the given\n"
  "ticks value (number of seconds since the epoch). For more information\n"
  "see the documentation of the standard Python time module"
);

PyDoc_STRVAR(
  module_Date__doc__,
  "Date(year, month, day)\n"
  "--\n"
  "\n"
  "This function constructs an object holding a date value\n"
);

PyDoc_STRVAR(
  module_Time__doc__,
  "Time(hour, minute, second)\n"
  "--\n"
  "\n"
  "This function constructs an object holding a time value\n"
);

PyDoc_STRVAR(
  module_Timestamp__doc__,
  "Timestamp(year, month, day, hour, minute, second)\n"
  "--\n"
  "\n"
  "This function constructs an object holding a time stamp value\n"
);
