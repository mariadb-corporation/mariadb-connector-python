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
Completion class for MariaDB query results

Equivalent to the Java Completion interface.
"""

from abc import ABC, abstractmethod
from typing import Optional, Any, List, Dict, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from .result import Result


@dataclass
class Completion(ABC):
    """
    Query completion result
    
    Equivalent to the Java Completion interface.
    """
    
    affected_rows: int = 0
    insert_id: int = 0
    warning_count: int = 0
    result_set: Optional['Result'] = None
    
    def has_result_set(self) -> bool:
        """Check if completion has result set"""
        return self.result_set is not None
    
    def get_result_set(self) -> Optional[Any]:
        """Get result set"""
        return self.result_set
    
    @abstractmethod
    def is_output_parameters(self) -> bool:
        """Check if completion has output parameters"""
        pass

    def __str__(self) -> str:
        return (f"Completion(affected_rows={self.affected_rows}, "
                f"insert_id={self.insert_id}, "
                f"warning_count={self.warning_count})")
    
    def __repr__(self) -> str:
        return self.__str__()
