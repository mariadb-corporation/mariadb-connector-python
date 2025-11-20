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
    
    def __repr__(self) -> str:
        """String representation for debugging"""
        return f"MutableInt({self._value})"
