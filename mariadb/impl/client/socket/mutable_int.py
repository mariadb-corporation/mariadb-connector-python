# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

class MutableInt:
    """
    Mutable integer wrapper for packet sequence tracking
    """
    
    def __init__(self, initial_value: int = 0):
        """Initialize mutable integer with initial value"""
        self._value = initial_value
    
    def get(self) -> int:
        """Get current value"""
        return self._value
    
    def set(self, value: int) -> None:
        """Set new value"""
        self._value = value
    
    def increment_and_get(self) -> int:
        """Increment value by 1 and return new value"""
        self._value = (self._value + 1) % 256
        return self._value
    
    def get_and_increment(self) -> int:
        """Increment value by 1 and return new value"""
        old_value = self._value
        self._value = (self._value + 1) % 256
        return old_value

    def add(self, delta: int) -> int:
        """Add delta to current value and return new value"""
        self._value = (self._value + delta) % 256
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
