# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
SQLAlchemy Async Dialect for MariaDB Connector/Python

Provides async support for SQLAlchemy using mariadb-connector-python's
native AsyncConnection implementation.
"""

from sqlalchemy.dialects.mysql.mariadbconnector import MariaDBConnectorDialect
from sqlalchemy.pool import NullPool


class MariaDBConnectorDialect_async(MariaDBConnectorDialect):
    """
    Async dialect for MariaDB Connector/Python.
    
    Uses the native AsyncConnection implementation from mariadb-connector-python.
    
    Usage:
        from sqlalchemy.ext.asyncio import create_async_engine
        
        engine = create_async_engine(
            "mariadb+mariadbconnector-async://user:pass@host/db"
        )
    """
    
    driver = "mariadbconnector-async"
    supports_statement_cache = True
    is_async = True
    
    @classmethod
    def import_dbapi(cls):
        """Import the async DBAPI module"""
        import mariadb.asyncio
        return mariadb.asyncio
    
    @classmethod
    def get_pool_class(cls, url):
        """Use NullPool for async to avoid connection sharing issues"""
        return NullPool


# Alias for registration
dialect = MariaDBConnectorDialect_async
