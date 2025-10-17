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

"""
Prepared statement implementation for MariaDB Connector/Python
"""

from typing import List, Dict, Any, Optional


class PreparedStatement:
    """
    Represents a prepared statement with its metadata
    """
    
    def __init__(self, statement_id: int, sql: str, parameter_count: int, column_count: int):
        """
        Initialize prepared statement
        
        Args:
            statement_id: Server-assigned statement ID
            sql: Original SQL statement
            parameter_count: Number of parameters in the statement
            column_count: Number of columns in the result set
        """
        self.statement_id = statement_id
        self.sql = sql
        self.parameter_count = parameter_count
        self.column_count = column_count
        self.parameter_metadata: List[Dict[str, Any]] = []
        self.column_metadata: List[Dict[str, Any]] = []
        self.closed = False
    
    def add_parameter_metadata(self, metadata: Dict[str, Any]) -> None:
        """Add parameter metadata"""
        self.parameter_metadata.append(metadata)
    
    def add_column_metadata(self, metadata: Dict[str, Any]) -> None:
        """Add column metadata"""
        self.column_metadata.append(metadata)
    
    def close(self) -> None:
        """Mark statement as closed"""
        self.closed = True
    
    def is_closed(self) -> bool:
        """Check if statement is closed"""
        return self.closed
    
    def __str__(self) -> str:
        return f"PreparedStatement(id={self.statement_id}, params={self.parameter_count}, cols={self.column_count})"
