# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from abc import ABC, abstractmethod
from typing import Optional, Any, List, Dict, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from .result import Result


@dataclass
class Completion(ABC):
    """
    Query completion result
    """
    __slots__ = (
        'affected_rows',
        'insert_id',
        'warning_count',
        'result_set',
    )
    
    def __init__(
        self,
        affected_rows: int = 0,
        insert_id: int = 0,
        warning_count: int = 0,
    ):
        self.affected_rows = affected_rows
        self.insert_id = insert_id
        self.warning_count = warning_count
        self.result_set: Optional['Result'] = None
    
    def has_result_set(self) -> bool:
        """Check if completion has result set"""
        return self.result_set is not None
    
    def get_result_set(self) -> Optional[Any]:
        """Get result set"""
        return self.result_set
    
    @abstractmethod
    def is_output_parameters(self) -> bool:
        """Check if completion has output parameters"""
        ...

    def __str__(self) -> str:
        result_info = f", result_set={self.result_set}" if self.result_set else ""
        return (f"Completion(affected_rows={self.affected_rows}, "
                f"insert_id={self.insert_id}, "
                f"warning_count={self.warning_count}{result_info})")
    
    def __repr__(self) -> str:
        return self.__str__()
