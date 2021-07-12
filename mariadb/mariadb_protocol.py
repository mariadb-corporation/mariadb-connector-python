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

import struct

PROT_CMD_SLEEP= 0
PROT_CMD_QUIT= 1
PROT_CMD_INIT_DB= 2
PROT_CMD_QUERY= 3
PROT_CMD_FIELD_LIST= 4
PROT_CMD_CREATE_DB= 5
PROT_CMD_DROP_DB= 6
PROT_CMD_REFRESH= 7
PROT_CMD_SHUTDOWN= 8
PROT_CMD_STATISTICS= 9
PROT_CMD_PROCESS_INFO= 10
PROT_CMD_CONNECT= 11
PROT_CMD_PROCESS_KILL= 12
PROT_CMD_DEBUG= 13
PROT_CMD_PING= 14
PROT_CMD_TIME= 15,
PROT_CMD_DELAYED_INSERT= 16
PROT_CMD_CHANGE_USER= 17
PROT_CMD_BINLOG_DUMP= 18
PROT_CMD_TABLE_DUMP= 19
PROT_CMD_CONNECT_OUT = 20
PROT_CMD_REGISTER_SLAVE= 21
PROT_CMD_STMT_PREPARE= 22
PROT_CMD_STMT_EXECUTE= 23
PROT_CMD_STMT_SEND_LONG_DATA = 24
PROT_CMD_STMT_CLOSE= 25
PROT_CMD_STMT_RESET= 26
PROT_CMD_SET_OPTION= 27
PROT_CMD_STMT_FETCH= 28
PROT_CMD_DAEMON= 29
PROT_CMD_UNSUPPORTED= 30
PROT_CMD_RESET_CONNECTION= 31
PROT_CMD_STMT_BULK_EXECUTE= 250

def prot_length(buffer_size):

def send_command(socket, command, buffer):


