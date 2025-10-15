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
Mutable Integer for MariaDB packet sequence tracking

Equivalent to the Java AtomicInteger or mutable integer wrapper.
"""


class MutableInt:
    """
    Mutable integer wrapper for packet sequence tracking
    
    This class provides a thread-safe way to track and increment
    packet sequence numbers in the MariaDB protocol.
    """
    
    def __init__(self, initial_value: int = 0):
        """
        Initialize mutable integer
        
        Args:
            initial_value: Initial value for the integer
        """
        self._value = initial_value
    
    def get(self) -> int:
        """
        Get current value
        
        Returns:
            Current integer value
        """
        return self._value
    
    def set(self, value: int) -> None:
        """
        Set new value
        
        Args:
            value: New integer value
        """
        self._value = value
    
    def increment(self) -> int:
        """
        Increment value by 1 and return new value
        
        Returns:
            New value after increment
        """
        self._value += 1
        return self._value
    
    def increment_and_get(self) -> int:
        """
        Increment value by 1 and return new value
        
        Returns:
            New value after increment
        """
        return self.increment()
    
    def get_and_increment(self) -> int:
        """
        Get current value and then increment by 1
        
        Returns:
            Value before increment
        """
        old_value = self._value
        self._value += 1
        return old_value
    
    def add(self, delta: int) -> int:
        """
        Add delta to current value and return new value
        
        Args:
            delta: Value to add
            
        Returns:
            New value after addition
        """
        self._value += delta
        return self._value
    
    def reset(self) -> None:
        """Reset value to 0"""
        self._value = 0
    
    def __str__(self) -> str:
        """String representation"""
        return str(self._value)
    
    def __repr__(self) -> str:
        """String representation for debugging"""
        return f"MutableInt({self._value})"
    
    def __int__(self) -> int:
        """Convert to int"""
        return self._value
    
    def __eq__(self, other) -> bool:
        """Equality comparison"""
        if isinstance(other, MutableInt):
            return self._value == other._value
        elif isinstance(other, int):
            return self._value == other
        return False
    
    def __lt__(self, other) -> bool:
        """Less than comparison"""
        if isinstance(other, MutableInt):
            return self._value < other._value
        elif isinstance(other, int):
            return self._value < other
        return NotImplemented
    
    def __le__(self, other) -> bool:
        """Less than or equal comparison"""
        if isinstance(other, MutableInt):
            return self._value <= other._value
        elif isinstance(other, int):
            return self._value <= other
        return NotImplemented
