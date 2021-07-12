#
# Copyright (C) 2021 Georg Richter and MariaDB Corporation AB

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

import mariadb
import socket
import time

from mariadb.constants import STATUS

_DEFAULT_CHARSET = "utf8mb4"
_DEFAULT_COLLATION = "utf8mb4_general_ci"

class AsyncConnection(mariadb._mariadb.connection):
    """MariaDB connection class"""

    def __init__(self, *args, **kwargs):
        self._socket= None
        self.__in_use= 0
        self.__pool = None
        self.__last_used = 0

        super().__init__(*args, **kwargs)

    async def _execute_command(self, command):
        print("comand: ")
        print(command)
        super().query(command)

    async def _read_response(self):
        super()._read_response()

    async def query(self, command):
        await self._execute_command(command)
        await self._read_response()

    def cursor(self, **kwargs):
        return mariadb.Cursor(self, **kwargs)


    def close(self):
        if self._Connection__pool:
            self._Connection__pool._close_connection(self)
        else:
            super().close()

    def __enter__(self):
        "Returns a copy of the connection."
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        "Closes connection."
        self.close()

    @property
    def character_set(self):
        """Client character set."""
        return _DEFAULT_CHARSET

    @property
    def collation(self):
        """Client character set collation"""
        return _DEFAULT_COLLATION

    @property
    def server_status(self):
        """Returns server status flags."""
        return super()._server_status

    @property
    def socket(self):
        """Returns the socket used for database connection"""

        fno= self.get_socket()
        if not self._socket:
            self._socket= socket.socket(fileno=fno)
        # in case of a possible reconnect, file descriptor has changed
        elif fno != self._socket.fileno():
            self._socket= socket.socket(fileno=fno)
        return self._socket
