# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

from typing import Optional
from dataclasses import dataclass


@dataclass
class HostAddress:
    """
    Host address information for MariaDB connections
    """
    
    host: str = 'localhost'
    port: int = 3306
    
    def __repr__(self) -> str:
        return f"{self.host}:{self.port}"
    
